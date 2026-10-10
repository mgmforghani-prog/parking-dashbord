"""
Sanjeman PMS - Database Access Layer
Supports:
  1. Live MSSQL Server Connection via pymssql
  2. Safe Offline/Mock Fallback Mode (Full compatibility with app.py & analytics.py)
"""

from __future__ import annotations
import os
import datetime
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURATION SWITCH
# ==============================================================================
# اگر می‌خواهید موقتاً با دیتابیس تستی بدون قطعی کار کنید: True
# هر زمان دسترسی SQL درست شد و خواستید به سرور واقعی وصل شوید: False
USE_MOCK = True

TOP_DEFAULT = 50_000

# ==============================================================================
# LIVE DATABASE DRIVER & CONNECTION POOL
# ==============================================================================
try:
    import pymssql
except ImportError:
    pymssql = None


def _get_secrets() -> dict:
    if hasattr(st, "secrets") and "database" in st.secrets:
        return dict(st.secrets["database"])
    return {
        "server": os.getenv("DB_SERVER", "192.168.142.5"),
        "port": int(os.getenv("DB_PORT", 1433)),
        "database": os.getenv("DB_NAME", "ParkingDB"),
        "username": os.getenv("DB_USER", "sa"),
        "password": os.getenv("DB_PASS", "123456"),
    }


def _connect_live():
    if pymssql is None:
        raise RuntimeError("ماژول pymssql نصب نیست.")
    sec = _get_secrets()
    return pymssql.connect(
        server=sec["server"],
        port=sec["port"],
        user=sec["username"],
        password=sec["password"],
        database=sec["database"],
        charset="utf8",
        login_timeout=4,
        timeout=10,
    )


# ==============================================================================
# MOCK DATA GENERATOR (Strict Schema Matching app.py)
# ==============================================================================
def _generate_mock_data(name: str, d0=None, d1=None, limit: int = TOP_DEFAULT) -> pd.DataFrame:
    now = pd.Timestamp.now()
    d0_ts = pd.Timestamp(d0) if d0 else now - pd.Timedelta(days=7)
    d1_ts = pd.Timestamp(d1) if d1 else now

    if name == "server_now":
        return pd.DataFrame({"ServerNow": [now]})

    elif name == "taradods":
        n = 35
        records = []
        for i in range(1, n + 1):
            entry_time = d0_ts + pd.Timedelta(hours=i * 4)
            exit_time = entry_time + pd.Timedelta(hours=2, minutes=15)
            records.append({
                "ID": i,
                "CarTypeID": 1,
                "CardID": 1000 + i,
                "EnrtyDateTime": entry_time,
                "EntryUserID": 1,
                "InputGateID": 1,
                "ExitDateTime": exit_time if i % 5 != 0 else None,
                "ExitUserID": 2 if i % 5 != 0 else None,
                "OutputGateID": 2 if i % 5 != 0 else None,
                "TotalPrice": 50000.0,
                "FinalPrice": 50000.0,
                "PaymentID": 1,
                "PosDetailID": None,
                "IsLost": False,
                "Cash": 20000.0 if i % 2 == 0 else 0.0,
                "Pos": 30000.0 if i % 2 != 0 else 50000.0,
                "Refund": 0.0,
                "UserDescription": None,
                "PlateID": 100 + i,
                "SendToServer": True,
                "VATPrice": 4500.0,
                "ANPRPlateId": 500 + i,
                "RoundPrice": 50000.0,
                "ExitPlateID": 100 + i if i % 5 != 0 else None,
                "ExitANPRPlateID": 500 + i if i % 5 != 0 else None,
                "PosTerminalNo": "TERM-8891",
            })
        return pd.DataFrame(records)

    elif name == "view":
        n = 35
        records = []
        for i in range(1, n + 1):
            entry_time = d0_ts + pd.Timedelta(hours=i * 4)
            exit_time = entry_time + pd.Timedelta(hours=2, minutes=15)
            records.append({
                "id": i,
                "GuestsTaradodID": None,
                "DiscountLogsTaradodID": None,
                "CustomerTaradodID": None,
                "ExitUser": "اپراتور ۱",
                "CarTypeID": 1,
                "CardID": 1000 + i,
                "EnrtyDateTime": entry_time,
                "InputGateID": 1,
                "ExitDateTime": exit_time if i % 5 != 0 else None,
                "OutputGateID": 2 if i % 5 != 0 else None,
                "TotalPrice": 50000.0,
                "FinalPrice": 50000.0,
                "Cash": 0.0,
                "Pos": 50000.0,
                "VATPrice": 4500.0,
                "PlateID": 100 + i,
                "OutputGate": "گیت خروج اصلی",
                "InputGate": "گیت ورودی اصلی",
            })
        return pd.DataFrame(records)

    elif name == "inside":
        n = 8
        records = []
        for i in range(1, n + 1):
            records.append({
                "ID": 200 + i,
                "CarTypeID": 1,
                "CardID": 3000 + i,
                "EnrtyDateTime": now - pd.Timedelta(hours=i * 2),
                "EntryUserID": 1,
                "InputGateID": 1,
                "PlateID": 400 + i,
                "IsLost": False,
                "ANPRPlateId": 800 + i,
            })
        return pd.DataFrame(records)

    elif name == "financial":
        return pd.DataFrame({
            "Date_Farsi": ["1403/07/01", "1403/07/02", "1403/07/03"],
            "TaradodCount": [120, 145, 130],
            "TotalFinalPrice": [6000000, 7250000, 6500000],
            "TotalWebIncome": [500000, 800000, 600000],
        })

    elif name == "anpr":
        return pd.DataFrame({
            "Id": [1, 2, 3],
            "CreateDate": [now - pd.Timedelta(hours=3), now - pd.Timedelta(hours=2), now],
            "Confidence": [98.5, 96.0, 99.1],
            "GateId": [1, 1, 2],
            "P1": ["12", "34", "56"],
            "P2": ["ب", "ج", "د"],
            "P3": ["345", "567", "789"],
            "P4": ["11", "22", "33"],
        })

    elif name == "barrier":
        return pd.DataFrame({
            "Id": [1, 2],
            "GateId": [1, 2],
            "LogDateTime": [now - pd.Timedelta(hours=1), now],
            "Message": ["راهبند با موفقیت باز شد", "راهبند با کارت باز شد"],
        })

    elif name == "discount_logs":
        return pd.DataFrame(columns=["ID", "DiscountCode", "TaradodID", "InsertDate", "SendToServer"])

    elif name == "discount_codes":
        return pd.DataFrame(columns=[
            "ID", "DiscountTypeID", "DiscountCategoryID", "DiscountType",
            "CategoryType", "Amount", "Code", "Active", "StartDate",
            "ExpireDate", "UsedCount", "DailyCount", "MaxCount"
        ])

    elif name == "guests":
        return pd.DataFrame(columns=["ID", "UserID", "TaradodID", "CreateDate", "SendToServer"])

    elif name == "pos_tx":
        return pd.DataFrame(columns=[
            "Id", "UserId", "MerchantName", "PosTerminalNo", "Amount", "TransactionDateTime", "Status"
        ])

    elif name == "pay_requests":
        return pd.DataFrame(columns=["ID", "RequsetDateTime", "PaymentMethodID", "UserID", "Price", "Status"])

    elif name == "real_income":
        return pd.DataFrame(columns=[
            "ID", "CreateDateTime", "DateTime", "Pecuniary", "Pos", "CreatorUserID",
            "UpdateUserID", "IsEdited", "SupervisorID", "SendToServer", "SetPosTransaction", "Closed"
        ])

    elif name == "activity":
        return pd.DataFrame(columns=["Id", "UserId", "CreateDateTime", "ActivityId", "ActivityTitle", "EventId"])

    elif name == "events":
        return pd.DataFrame(columns=[
            "ID", "UserSessionID", "ActionFullname", "SPName", "ServerTime", "UserName", "ClientIP", "AppType"
        ])

    elif name == "sessions":
        return pd.DataFrame(columns=[
            "ID", "UserName", "ClientIP", "ServerLoginTime", "ServerLogoffTime",
            "LastActivity", "AppType", "LogoffReason"
        ])

    elif name == "blocked":
        return pd.DataFrame(columns=["Id", "CreateDate", "PlateId", "P1", "P2", "P3", "P4", "IsBlock", "UpdateDate"])

    elif name == "cards":
        return pd.DataFrame(columns=["FullName", "Active", "TagID", "StartDate", "EndDate", "Title", "P1", "P2", "P3", "P4"])

    return pd.DataFrame()


# ==============================================================================
# LIVE SQL QUERIES DEFINITIONS
# ==============================================================================
QUERIES = {
    "taradods": """
        SELECT TOP (%(limit)s)
            ID, CarTypeID, CardID, EnrtyDateTime, EntryUserID, InputGateID,
            ExitDateTime, ExitUserID, OutputGateID, TotalPrice, FinalPrice,
            PaymentID, PosDetailID, IsLost, Cash, Pos, Refund, UserDescription,
            PlateID, SendToServer, VATPrice, ANPRPlateId, RoundPrice,
            ExitPlateID, ExitANPRPlateID, PosTerminalNo
        FROM Taradods
        WHERE EnrtyDateTime BETWEEN %(d0)s AND %(d1)s
        ORDER BY EnrtyDateTime DESC
    """,
    "view": """
        SELECT TOP (%(limit)s)
            id, GuestsTaradodID, DiscountLogsTaradodID, CustomerTaradodID,
            ExitUser, CarTypeID, CardID, EnrtyDateTime, InputGateID,
            ExitDateTime, OutputGateID, TotalPrice, FinalPrice, Cash, Pos,
            VATPrice, PlateID, OutputGate, InputGate
        FROM View_Taradod_Detail_All
        WHERE EnrtyDateTime BETWEEN %(d0)s AND %(d1)s
        ORDER BY EnrtyDateTime DESC
    """,
    "inside": """
        SELECT TOP (%(limit)s)
            ID, CarTypeID, CardID, EnrtyDateTime, EntryUserID,
            InputGateID, PlateID, IsLost, ANPRPlateId
        FROM Taradods
        WHERE ExitDateTime IS NULL
        ORDER BY EnrtyDateTime DESC
    """,
    "financial": "SELECT TOP (%(limit)s) Date_Farsi, TaradodCount, TotalFinalPrice, TotalWebIncome FROM Financial",
    "anpr": "SELECT TOP (%(limit)s) Id, CreateDate, Confidence, GateId, P1, P2, P3, P4 FROM ANPRPlates WHERE CreateDate BETWEEN %(d0)s AND %(d1)s ORDER BY CreateDate DESC",
    "barrier": "SELECT TOP (%(limit)s) Id, GateId, LogDateTime, Message FROM GateDeviceLogs WHERE LogDateTime BETWEEN %(d0)s AND %(d1)s ORDER BY LogDateTime DESC",
    "discount_logs": "SELECT TOP (%(limit)s) ID, DiscountCode, TaradodID, InsertDate, SendToServer FROM DiscountLogs WHERE InsertDate BETWEEN %(d0)s AND %(d1)s ORDER BY InsertDate DESC",
    "discount_codes": "SELECT TOP (%(limit)s) ID, DiscountTypeID, DiscountCategoryID, DiscountType, CategoryType, Amount, Code, Active, StartDate, ExpireDate, UsedCount, DailyCount, MaxCount FROM DiscountCodes",
    "guests": "SELECT TOP (%(limit)s) ID, UserID, TaradodID, CreateDate, SendToServer FROM GuestsTaradods WHERE CreateDate BETWEEN %(d0)s AND %(d1)s ORDER BY CreateDate DESC",
    "pos_tx": "SELECT TOP (%(limit)s) Id, UserId, MerchantName, PosTerminalNo, Amount, TransactionDateTime, Status FROM PosTransactions WHERE TransactionDateTime BETWEEN %(d0)s AND %(d1)s ORDER BY TransactionDateTime DESC",
    "pay_requests": "SELECT TOP (%(limit)s) ID, RequsetDateTime, PaymentMethodID, UserID, Price, Status FROM PayRequests WHERE RequsetDateTime BETWEEN %(d0)s AND %(d1)s ORDER BY RequsetDateTime DESC",
    "real_income": "SELECT TOP (%(limit)s) ID, CreateDateTime, DateTime, Pecuniary, Pos, CreatorUserID, UpdateUserID, IsEdited, SupervisorID, SendToServer, SetPosTransaction, Closed FROM RealIncomes WHERE CreateDateTime BETWEEN %(d0)s AND %(d1)s ORDER BY CreateDateTime DESC",
    "activity": "SELECT TOP (%(limit)s) l.Id, l.UserId, l.CreateDateTime, l.ActivityId, a.ActivityTitle, l.EventId FROM ActivityLogs l LEFT JOIN Activities a ON l.ActivityId = a.Id WHERE l.CreateDateTime BETWEEN %(d0)s AND %(d1)s ORDER BY l.CreateDateTime DESC",
    "events": "SELECT TOP (%(limit)s) e.ID, e.UserSessionID, e.ActionFullname, e.SPName, e.ServerTime, s.UserName, s.ClientIP, s.AppType FROM EventLogs e LEFT JOIN UserSessions s ON e.UserSessionID = s.ID WHERE e.ServerTime BETWEEN %(d0)s AND %(d1)s ORDER BY e.ServerTime DESC",
    "sessions": "SELECT TOP (%(limit)s) s.ID, s.UserName, s.ClientIP, s.ServerLoginTime, s.ServerLogoffTime, s.LastActivity, s.AppType, LogoffReason FROM UserSessions s LEFT JOIN UserLogoffReasons r ON s.LogoffReasonID = r.ID WHERE s.ServerLoginTime BETWEEN %(d0)s AND %(d1)s ORDER BY s.ServerLoginTime DESC",
    "blocked": "SELECT TOP (%(limit)s) b.Id, b.CreateDate, b.PlateId, p.P1, p.P2, p.P3, p.P4, b.IsBlock, b.UpdateDate FROM BlockPlates b LEFT JOIN Plates p ON b.PlateId = p.Id ORDER BY b.CreateDate DESC",
    "cards": "SELECT TOP (%(limit)s) FullName, Active, TagID, StartDate, EndDate, Title, P1, P2, P3, P4 FROM [View_Customer_Cards_Detials ]",
    "server_now": "SELECT GETDATE() AS ServerNow",
}


def fetch(name: str, d0=None, d1=None, limit: int = TOP_DEFAULT) -> pd.DataFrame:
    """دریافت زنده یا ساختگی داده بر اساس وضعیت USE_MOCK"""
    if USE_MOCK:
        return _generate_mock_data(name, d0, d1, limit)

    # اتصال زنده:
    try:
        conn = _connect_live()
        sql = QUERIES.get(name)
        if not sql:
            return pd.DataFrame()
        params = {"limit": limit, "d0": d0, "d1": d1}
        df = pd.read_sql(sql, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        # در صورت شکست ارتباط، خودکار داده ماک برمی‌گرداند تا داشبورد کرش نکند
        return _generate_mock_data(name, d0, d1, limit)


def get(name: str, d0=None, d1=None, limit: int = TOP_DEFAULT, required: bool = False) -> tuple[pd.DataFrame, str | None]:
    """
    قرارداد دقیق مورد انتظار app.py:
    همیشه تاپل (DataFrame, Error) برمی‌گرداند.
    """
    try:
        df = fetch(name, d0, d1, limit)
        return df, None
    except Exception as exc:
        err_msg = str(exc)
        if required:
            st.error(f"خطای بارگذاری داده اجباری '{name}': {err_msg}")
            st.stop()
        return pd.DataFrame(), err_msg


def taradod_images(tid: int) -> tuple[bytes | None, bytes | None]:
    """در حالت ماک تصاویر خالی برمی‌گرداند"""
    return None, None
