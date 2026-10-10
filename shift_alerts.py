"""هشدار لحظه‌ای شیفت (Shift Alerts) با پیامک — بر پایه‌ی داده‌ی واقعی ParkingDB
قوانین فقط از ستون‌های موجود در دیتابیس ساخته شده‌اند (ابطال فیش، لوپ و راهبند خارج از شیفت در اسکیما نیست و پیاده نشده است).

اجرا (خارج از Streamlit؛ اطلاعات اتصال از .streamlit/secrets.toml خوانده می‌شود):
  python shift_alerts.py --day 2026-09-25 --shift عصر            # فقط نمایش
  python shift_alerts.py --day 2026-09-25 --shift عصر --send     # ارسال واقعی
  python shift_alerts.py --watch --interval 300 --send            # شیفت جاری، هر ۵ دقیقه
"""
import argparse
import json
import os
import re
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

import analytics as an

SEV_ORDER = {"فوری": 0, "مهم": 1, "پایش": 2}
ROLE_FA = {"shift_manager": "مدیر شیفت", "security": "حراست", "site_manager": "مدیر پارکینگ", "ceo": "مدیرعامل"}
ROUTING = {"فوری": ["shift_manager", "security", "site_manager"], "مهم": ["shift_manager"], "پایش": []}
TH = dict(anpr_noise_burst=10)  # حداقل تعداد خوانش نویزی یک گیت در شیفت برای هشدار (قابل تنظیم)

# (کد، پرچم، شدت، عنوان، قالب پیام)
FLAG_RULES = [
    ("A1", "F_PosNoDetail", "فوری", "پرداخت کارتخوان بدون ثبت پوز", "کارتخوان بدون ثبت پوز: {n} مورد · کاربر خروج {u} · مبلغ {amt} تومان · {t}"),
    ("A2", "F_Refund", "فوری", "بازپرداخت ثبت‌شده", "بازپرداخت: {n} مورد · کاربر خروج {u} · مجموع {amt} تومان · {t}"),
    ("A3", "F_PayMismatch", "مهم", "ناهمخوانی پرداخت با مبلغ نهایی", "ناهمخوانی نقد+کارتخوان با مبلغ نهایی: {n} مورد · کاربر خروج {u} · {t}"),
    ("A4", "F_FreeExit", "مهم", "خروج با مبلغ نهایی صفر", "خروج با مبلغ صفر: {n} مورد · کاربر خروج {u} · {t}"),
    ("A5", "F_Lost", "مهم", "فیش مفقودی", "فیش مفقودی: {n} مورد · کاربر خروج {u} · {t}"),
]


def shift_window(day, shift):
    d0 = pd.Timestamp(day).normalize()
    a, b = an.SHIFTS[shift]
    return d0 + pd.Timedelta(hours=a), d0 + pd.Timedelta(hours=b)


def current_shift(now):
    now = pd.Timestamp(now)
    h = now.hour
    if 6 <= h < 14:
        return now.normalize(), "صبح"
    if 14 <= h < 22:
        return now.normalize(), "عصر"
    return (now.normalize() if h >= 22 else now.normalize() - pd.Timedelta(days=1)), "شب"


def evaluate(tx, view, inside, anpr, disc_logs, day, shift):
    """ورودی‌ها: DataFrameهای آماده‌شده با analytics.prepare_*؛ خروجی: جدول هشدارها"""
    day = pd.Timestamp(day).normalize()
    t0, t1 = shift_window(day, shift)
    out = []

    def add(rule, sev, title, entity, n, t, text):
        out.append(dict(rule=rule, severity=sev, title=title, entity=str(entity), count=int(n), time=t, shift=shift,
                        message=f"[{sev}] {text} | شیفت {shift}", key=f"{rule}|{entity}|{day:%Y%m%d}|{shift}", roles=ROUTING[sev]))

    w = tx[(tx.Event_Time >= t0) & (tx.Event_Time < t1)]
    for rule, col, sev, title, tmpl in FLAG_RULES:
        for u, g in w[w[col] == 1].groupby("ExitUserID"):
            amt = g.Loss.sum()
            add(rule, sev, title, u, len(g), g.Event_Time.max(), tmpl.format(n=len(g), u=int(u) if pd.notna(u) else "-", amt=f"{amt:,.0f}", t=g.Event_Time.max().strftime("%H:%M")))
    # کدهای تخفیف تکراری در بازه‌ی شیفت (DiscountLogs)
    if not disc_logs.empty:
        dl = disc_logs[(pd.to_datetime(disc_logs.InsertDate) >= t0) & (pd.to_datetime(disc_logs.InsertDate) < t1)]
        for code, g in dl.groupby("DiscountCode"):
            if len(g) > 1:
                add("A6", "فوری", "کد تخفیف تکراری", code, len(g), pd.to_datetime(g.InsertDate).max(), f"کد تخفیف {code} در این شیفت {len(g)} بار استفاده شد")
    # نویز ANPR: انبوه خوانش با اطمینان کم در یک گیت (نشانه‌ی خرابی دوربین یا نور)
    if not anpr.empty:
        a = anpr.assign(CreateDate=pd.to_datetime(anpr.CreateDate), Confidence=pd.to_numeric(anpr.Confidence, errors="coerce"))
        a = a[(a.CreateDate >= t0) & (a.CreateDate < t1) & (a.Confidence < an.LOW_CONF)]
        for gid, g in a.groupby("GateId"):
            if len(g) >= TH["anpr_noise_burst"]:
                add("A7", "مهم", "کیفیت پلاک‌خوان", gid, len(g), g.CreateDate.max(), f"گیت {gid}: {len(g)} خوانش با اطمینان زیر {an.LOW_CONF} (بررسی دوربین/نور)")
    # خودروهای داخل: توقف طولانی و ورود تکراری (وضعیت لحظه‌ای؛ فقط در شیفت جاری معنا دارد)
    if not inside.empty:
        n_long, n_card, n_plate = int(inside.LongStay.sum()), int(inside.DupCard.sum()), int(inside.DupPlate.sum())
        if n_long:
            add("A8", "پایش", "خودروی بیش از ۴۸ ساعت", "inside", n_long, t1, f"{n_long} خودرو بیش از {an.LONG_STAY_H} ساعت داخل پارکینگ است")
        if n_card or n_plate:
            add("A9", "مهم", "ورود باز تکراری", "inside", n_card + n_plate, t1, f"ورود باز تکراری: {n_card} ردیف با کارت مشترک و {n_plate} ردیف با پلاک مشترک")
    # پروتکل Z-Score (سند): نسبت نقد و خروج رایگان همزمان بالای ۲.۵
    if not view.empty:
        _, _, hit = an.operator_profile(view[(view.Event_Time < t1)])
        for u in hit:
            add("A10", "فوری", "بازرسی سرزده (Z-Score)", u, 1, t1, f"بازرسی سرزده: Z نسبت نقد و Z خروج رایگان صندوقدار {u} از {an.Z_PROTOCOL} گذشت")
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["_o"] = df.severity.map(SEV_ORDER)
    return df.sort_values(["_o", "time"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)


# ----------------------------------------------------------------------------- پیامک
def norm_phone(p):
    p = re.sub(r"\D", "", str(p))
    p = re.sub(r"^(98|0098)", "0", p)
    return p if re.fullmatch(r"09\d{9}", p) else None


def sms_segments(text):
    """پیامک یونیکد: ۷۰ نویسه برای یک بخش، ۶۷ نویسه برای هر بخش در پیامک چندبخشی"""
    n = len(text)
    return 1 if n <= 70 else -(-n // 67)


class SMSGateway:
    def __init__(self, provider=None, api_key=None, sender=None, dry_run=True):
        self.provider = (provider or os.getenv("SMS_PROVIDER", "console")).lower()
        self.key, self.sender = api_key or os.getenv("SMS_API_KEY"), sender or os.getenv("SMS_SENDER")
        self.dry = dry_run or self.provider == "console" or not self.key

    def send(self, phone, text):
        ph = norm_phone(phone)
        if not ph:
            return dict(phone=str(phone), ok=False, info="شماره نامعتبر")
        if self.dry:
            return dict(phone=ph, ok=True, info="DRY-RUN (ارسال نشد)", segments=sms_segments(text))
        try:
            if self.provider == "kavenegar":
                req = urllib.request.Request(f"https://api.kavenegar.com/v1/{self.key}/sms/send.json",
                                             urllib.parse.urlencode({"receptor": ph, "sender": self.sender, "message": text}).encode())
            elif self.provider == "smsir":
                req = urllib.request.Request("https://api.sms.ir/v1/send/bulk", json.dumps({"lineNumber": int(self.sender), "messageText": text, "mobiles": [ph]}).encode(),
                                             {"X-API-KEY": self.key, "Content-Type": "application/json"})
            else:
                return dict(phone=ph, ok=False, info=f"سرویس‌دهنده ناشناخته: {self.provider}")
            with urllib.request.urlopen(req, timeout=15) as r:
                return dict(phone=ph, ok=200 <= r.status < 300, info=f"HTTP {r.status}", segments=sms_segments(text))
        except Exception as e:  # noqa: BLE001
            return dict(phone=ph, ok=False, info=str(e)[:120])


class AlertStore:
    """جلوگیری از ارسال تکراری (Dedupe)"""
    def __init__(self, path=".alert_state.json"):
        self.p = Path(path)
        self.d = json.loads(self.p.read_text(encoding="utf-8")) if self.p.exists() else {}

    def seen(self, key):
        return key in self.d

    def mark(self, key):
        self.d[key] = pd.Timestamp.now().isoformat()
        self.p.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")


def dispatch(alerts, gateway, recipients, store=None, min_severity="مهم"):
    res = []
    for _, a in alerts.iterrows():
        if SEV_ORDER[a.severity] > SEV_ORDER[min_severity]:
            continue
        if store and store.seen(a.key):
            res.append(dict(key=a.key, phone="-", ok=True, info="قبلاً ارسال شده"))
            continue
        phones = {p for r_ in a.roles for p in recipients.get(r_, [])}
        if not phones:
            res.append(dict(key=a.key, phone="-", ok=False, info="گیرنده‌ای تعریف نشده"))
            continue
        ok_any = False
        for p in sorted(phones):
            r = gateway.send(p, a.message)
            r["key"] = a.key
            ok_any |= r["ok"]
            res.append(r)
        if store and ok_any and not gateway.dry:
            store.mark(a.key)
    return res


# ----------------------------------------------------------------------------- CLI
def _load(day0, day1):
    import db
    now = pd.Timestamp(db.fetch("server_now").iloc[0, 0])
    g = lambda n: db.fetch(n, day0, day1)
    return (an.prepare_taradods(g("taradods")), an.prepare_view(g("view")), an.prepare_inside(db.fetch("inside"), now), g("anpr"), g("discount_logs"), now)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--secrets", default=".streamlit/secrets.toml")
    ap.add_argument("--day"), ap.add_argument("--shift", choices=list(an.SHIFTS))
    ap.add_argument("--send", action="store_true"), ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=300), ap.add_argument("--min-severity", default="مهم", choices=list(SEV_ORDER))
    a = ap.parse_args()
    sec = tomllib.loads(Path(a.secrets).read_text(encoding="utf-8"))
    import db
    db.configure(sec["connections"]["mssql"])
    sms = sec.get("sms", {})
    rec = sms.get("recipients", {})
    while True:
        now = pd.Timestamp(db.fetch("server_now").iloc[0, 0])
        day, shift = (pd.Timestamp(a.day), a.shift) if a.day and a.shift else current_shift(now)
        tx, vw, ins, anp, dl, now = _load(day - pd.Timedelta(days=30), day + pd.Timedelta(days=2))
        al = evaluate(tx, vw, ins, anp, dl, day, shift)
        print(f"شیفت {shift} {day:%Y-%m-%d}: {len(al)} هشدار")
        for _, x in al.iterrows():
            print(f"- {x.message}  (بخش پیامک: {sms_segments(x.message)})")
        if a.send:
            gw = SMSGateway(sms.get("provider"), sms.get("api_key"), sms.get("sender"), dry_run=False)
            for r in dispatch(al, gw, rec, AlertStore(), a.min_severity):
                print("  SMS", r)
        if not a.watch:
            break
        time.sleep(a.interval)
