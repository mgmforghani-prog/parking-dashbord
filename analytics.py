"""
Analytics and Feature Engineering Engine for Sanjeman PMS Dashboard.
Provides data preparation, risk rules, anomaly detection, and ANPR diagnostics.
"""

import numpy as np
import pandas as pd

# ثوابت مورد انتظار داشبورد
LOW_CONF = 0.60

WD_ORDER = [
    "شنبه",
    "یک‌شنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
]

# تعاریف قوانین و وزن‌دهی به ریسک‌های مالی
# قالب: (نام فارسی قانون, وزن ریسک, معادل مستندات, منطق اعتبارسنجی)
RULES = {
    "F_FreeExit": ("خروج رایگان مشکوک", 3.0, "R01", "FinalPrice == 0 & TotalPrice > 0"),
    "F_Refund": ("تراکنش دارای بازپرداخت", 2.5, "R02", "Refund > 0"),
    "F_PosNoDetail": ("کارتخوان فاقد شناسه تراکنش", 2.0, "R03", "Pos > 0 & PosDetailID is null"),
    "F_PayMismatch": ("مغایرت دریافتی با مبلغ نهایی", 2.0, "R04", "Cash + Pos != FinalPrice"),
    "F_Lost": ("کارت اعلام مفقودی شده", 1.5, "R05", "IsLost == 1"),
}

FA_WEEKDAYS = {
    "Saturday": "شنبه",
    "Sunday": "یک‌شنبه",
    "Monday": "دوشنبه",
    "Tuesday": "سه‌شنبه",
    "Wednesday": "چهارشنبه",
    "Thursday": "پنج‌شنبه",
    "Friday": "جمعه",
}

def _calc_shift(dt_series: pd.Series) -> pd.Series:
    """محاسبه شیفت بر اساس ساعت (صبح: ۶ تا ۱۴، عصر: ۱۴ تا ۲۲، شب: ۲۲ تا ۶)"""
    hours = dt_series.dt.hour
    shifts = pd.Series("شب", index=dt_series.index)
    shifts[(hours >= 6) & (hours < 14)] = "صبح"
    shifts[(hours >= 14) & (hours < 22)] = "عصر"
    return shifts


def prepare_taradods(df: pd.DataFrame) -> pd.DataFrame:
    """آماده‌سازی تراکنش‌ها و ارزیابی قوانین ریسک و تخلفات مالی"""
    if df.empty:
        return df

    tx = df.copy()

    # تبدیل تاریخ‌ها
    tx["EnrtyDateTime"] = pd.to_datetime(tx.get("EnrtyDateTime"), errors="coerce")
    tx["ExitDateTime"] = pd.to_datetime(tx.get("ExitDateTime"), errors="coerce")

    # زمان رویداد و شاخص خروج
    tx["Event_Time"] = tx["ExitDateTime"].fillna(tx["EnrtyDateTime"])
    tx["Exited"] = tx["ExitDateTime"].notna()

    # تقویم و شیفت
    tx["Shift"] = _calc_shift(tx["Event_Time"])
    tx["Date"] = tx["Event_Time"].dt.date
    tx["Hour"] = tx["Event_Time"].dt.hour
    tx["Weekday"] = tx["Event_Time"].dt.day_name().map(FA_WEEKDAYS).fillna("شنبه")

    # مدت زمان پارک (به دقیقه)
    delta = (tx["ExitDateTime"] - tx["EnrtyDateTime"]).dt.total_seconds() / 60.0
    tx["Dur_Min"] = delta.fillna(0).clip(lower=0)

    # اعداد مالی
    for col in ["FinalPrice", "TotalPrice", "Cash", "Pos", "Refund"]:
        if col not in tx.columns:
            tx[col] = 0.0
        tx[col] = pd.to_numeric(tx[col], errors="coerce").fillna(0.0)

    # قوانین ناهنجاری (Flags)
    tx["F_FreeExit"] = (tx["FinalPrice"] == 0) & (tx["TotalPrice"] > 0)
    tx["F_Refund"] = tx["Refund"] > 0
    if "PosDetailID" in tx.columns:
        tx["F_PosNoDetail"] = (tx["Pos"] > 0) & (tx["PosDetailID"].isna() | (tx["PosDetailID"] == 0))
    else:
        tx["F_PosNoDetail"] = False

    tx["F_PayMismatch"] = (tx["Exited"]) & ((tx["Cash"] + tx["Pos"]) != tx["FinalPrice"])
    tx["F_Lost"] = tx.get("IsLost", 0).fillna(0).astype(bool)

    # شاخص‌های ریسک ترکیبی
    flag_cols = list(RULES.keys())
    tx["NFlags"] = tx[flag_cols].sum(axis=1)

    # محاسبه امتیاز وزنی ریسک
    weights = {k: v[1] for k, v in RULES.items()}
    score = sum(tx[f].astype(int) * weights[f] for f in flag_cols)
    tx["Risk_Score"] = score

    # محاسبه برآورد ضرر مالی
    tx["Loss"] = np.where(tx["F_FreeExit"], tx["TotalPrice"], 0.0) + tx["Refund"]

    # سطح ریسک
    conditions = [tx["Risk_Score"] >= 5, tx["Risk_Score"] >= 2]
    choices = ["بالا", "متوسط"]
    tx["Risk_Level"] = np.select(conditions, choices, default="پایین")

    return tx


def prepare_view(df: pd.DataFrame) -> pd.DataFrame:
    """آماده‌سازی ویوی تجمیعی PBI و گیت‌ها"""
    if df.empty:
        return df

    vw = df.copy()
    time_col = "ExitDateTime" if "ExitDateTime" in vw.columns else "EnrtyDateTime"
    vw["Event_Time"] = pd.to_datetime(vw.get(time_col), errors="coerce")
    vw["Exited"] = vw["Event_Time"].notna()
    vw["Shift"] = _calc_shift(vw["Event_Time"])

    if "FinalPrice" in vw.columns:
        vw["FinalPrice"] = pd.to_numeric(vw["FinalPrice"], errors="coerce").fillna(0.0)

    return vw


def prepare_inside(df: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """بررسی خودروهای مقیم در پارکینگ و کشف کارت‌ها و پلاک‌های تکراری یا طولانی‌مدت"""
    if df.empty:
        return df

    ins = df.copy()
    ins["EnrtyDateTime"] = pd.to_datetime(ins.get("EnrtyDateTime"), errors="coerce")

    # سن حضور بر حسب ساعت
    ins["Age_H"] = ((now - ins["EnrtyDateTime"]).dt.total_seconds() / 3600.0).fillna(0).clip(lower=0)
    ins["LongStay"] = ins["Age_H"] > 24  # حضور بالای ۲۴ ساعت

    # پلاک یا کارت تکراری درون پارکینگ
    if "CardID" in ins.columns:
        ins["DupCard"] = ins.duplicated(subset=["CardID"], keep=False) & ins["CardID"].notna()
    else:
        ins["DupCard"] = False

    if "PlateID" in ins.columns:
        ins["DupPlate"] = ins.duplicated(subset=["PlateID"], keep=False) & ins["PlateID"].notna()
    else:
        ins["DupPlate"] = False

    return ins


def discount_reuse(df: pd.DataFrame) -> pd.DataFrame:
    """شناسایی کدهای تخفیف با استفاده‌های مشکوک مکرر"""
    if df.empty or "DiscountCodeID" not in df.columns:
        return pd.DataFrame()
    counts = df.groupby("DiscountCodeID").size()
    suspicious_ids = counts[counts > 5].index
    return df[df["DiscountCodeID"].isin(suspicious_ids)]


def over_limit_codes(df: pd.DataFrame) -> pd.DataFrame:
    """شناسایی کدهای تخفیفی که بیش از حد مجاز اعمال شده‌اند"""
    if df.empty:
        return pd.DataFrame()
    limit_df = df.copy()
    if "UsedCount" in limit_df.columns and "MaxCount" in limit_df.columns:
        limit_df = limit_df[limit_df["UsedCount"] > limit_df["MaxCount"]]
    return limit_df


def operator_profile(vw: pd.DataFrame):
    """تحلیل آماری رفتار اپراتورها و محاسبه امتیاز Z-Score برای انحراف عملکرد"""
    if vw.empty or "ExitOperator" not in vw.columns:
        empty_prof = pd.DataFrame(columns=["Z ترکیبی", "تعداد خروج", "درآمد"])
        return empty_prof, 0, []

    grouped = vw.groupby("ExitOperator").agg(
        تعداد_خروج=("id", "count"),
        درآمد=("FinalPrice", "sum")
    ).rename(columns={"تعداد_خروج": "تعداد خروج"})

    # محاسبه امتیاز Z برای تشخیص ناهنجاری
    std = grouped["تعداد خروج"].std()
    mean = grouped["تعداد خروج"].mean()
    if std and std > 0:
        grouped["Z ترکیبی"] = (grouped["تعداد خروج"] - mean) / std
    else:
        grouped["Z ترکیبی"] = 0.0

    hit = grouped[grouped["Z ترکیبی"].abs() > 2.0].index.tolist()
    return grouped, 0, hit


def anpr_summary(df: pd.DataFrame) -> pd.DataFrame:
    """خلاصه کیفیت خوانش دوربین‌های پلاک‌خوان بر اساس گیت"""
    if df.empty:
        return pd.DataFrame(columns=["GateId", "تعداد خوانش", "نویز (<0.60)", "میانگین اطمینان"])

    anpr = df.copy()
    anpr["Confidence"] = pd.to_numeric(anpr.get("Confidence"), errors="coerce").fillna(0.0)

    summary = anpr.groupby("GateId").agg(
        تعداد_خوانش=("Id", "count") if "Id" in anpr.columns else ("Confidence", "count"),
        نویز_کم=("Confidence", lambda s: (s < LOW_CONF).sum()),
        میانگین_اطمینان=("Confidence", "mean")
    ).rename(columns={
        "تعداد_خوانش": "تعداد خوانش",
        "نویز_کم": "نویز (<0.60)",
        "میانگین_اطمینان": "میانگین اطمینان"
    }).reset_index()

    return summary


def anpr_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """تشخیص گپ‌های زمانی غیرعادی در ثبت پلاک دوربین‌ها (خرابی یا قطعی ارتباط)"""
    if df.empty or "CreateDate" not in df.columns or "GateId" not in df.columns:
        return pd.DataFrame(columns=["GateId", "بیشترین فاصله (دقیقه)"])

    anpr = df.copy()
    anpr["CreateDate"] = pd.to_datetime(anpr["CreateDate"], errors="coerce")
    anpr = anpr.sort_values(["GateId", "CreateDate"])

    anpr["Diff_Min"] = anpr.groupby("GateId")["CreateDate"].diff().dt.total_seconds() / 60.0

    gaps = anpr.groupby("GateId")["Diff_Min"].max().reset_index()
    gaps.columns = ["GateId", "بیشترین فاصله (دقیقه)"]
    gaps["بیشترین فاصله (دقیقه)"] = gaps["بیشترین فاصله (دقیقه)"].fillna(0).round(1)
    return gaps.sort_values(by="بیشترین فاصله (دقیقه)", ascending=False)


def id_profile(tx: pd.DataFrame) -> pd.DataFrame:
    """پروفایل مالی و تخلفات بر اساس کاربر خروج"""
    if tx.empty or "OutputGateID" not in tx.columns:
        return pd.DataFrame(columns=["مبلغ بازپرداخت", "تعداد تخلف"])

    prof = tx.groupby("OutputGateID").agg(
        مبلغ_بازپرداخت=("Refund", "sum"),
        تعداد_تخلف=("NFlags", "sum")
    ).rename(columns={
        "مبلغ_بازپرداخت": "مبلغ بازپرداخت",
        "تعداد_تخلف": "تعداد تخلف"
    }).reset_index()

    return prof
