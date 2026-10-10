"""سنجمان · داشبورد ممیزی و کشف تقلب پارکینگ — اتصال مستقیم و فقط‌خواندنی به SQL Server (ParkingDB)
اجرا: streamlit run app.py     (اتصال: .streamlit/secrets.toml → [connections.mssql])

ساختار جدید رابط کاربری:
  • صفحه‌ی اصلی: فقط دو کارت اصلی (درآمد و زیان مشکوک) + آیکون‌های داشبوردها
  • با کلیک روی هر آیکون، داشبورد مخصوص همان بخش باز می‌شود (بدون کارت‌های بالای صفحه)
  • همه‌ی داشبوردها طوری چیده شده‌اند که در یک صفحه جا شوند (بدون اسکرول)؛ اندازه‌ی نمودارها از «اندازه‌ی صفحه نمایش» در سایدبار تنظیم می‌شود
منطق داده (db.py / analytics.py / shift_alerts.py) دست‌نخورده است.
"""
import re
from pathlib import Path
from urllib.parse import quote

import numpy as np  # noqa: F401
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="سنجمان | پایش پارکینگ", page_icon="▦", layout="wide")

# ------------------------------------------------------------ پالت (استخراج‌شده از لوگو)
SLATE, DEEP, SURF = "#455E62", "#2C4144", "#365054"
YEL, MINT, TEAL, GRN, CORAL = "#FFE08A", "#88CFC0", "#4FC0A8", "#1BB08E", "#FF8A7A"
TXT, SUB = "#F1F7F5", "#B5CCC8"
STATE_C = {"ok": GRN, "warn": YEL, "bad": CORAL}
FONT_PL = "BNazanin, 'B Nazanin', Vazirmatn, sans-serif"
PCOL = {"فوری": CORAL, "مهم": YEL, "پایش": MINT}
PALETTE = [YEL, MINT, TEAL, GRN, CORAL]

# ------------------------------------------------------------ اعداد فارسی
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(s):
    """ارقام لاتین را به فارسی تبدیل می‌کند (فقط برای متن؛ نه برای رشته‌های حاوی رنگ/استایل)"""
    return re.sub(r"\d+(?:[,.]\d+)*", lambda m: m.group().translate(_FA).replace(",", "٬").replace(".", "٫"), str(s))


def num(v, d=0):
    return fa(f"{v:,.{d}f}")


CSS = """
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');
@font-face{font-family:'BNazanin';src:local('B Nazanin'),local('BNazanin'),url('app/static/BNazanin.ttf') format('truetype');font-display:swap}
@font-face{font-family:'BNazanin';font-weight:700;src:local('B Nazanin Bold'),local('BNazanin-Bold'),url('app/static/BNazanin-Bold.ttf') format('truetype');font-display:swap}
html{font-size:100%}
html,body,.stApp,button,input,textarea,select,[data-testid="stSidebar"]{font-family:'BNazanin','B Nazanin','Vazirmatn',Tahoma,sans-serif!important}
.stApp,.block-container,[data-testid="stSidebar"]{direction:rtl;text-align:right}
.stApp{background:@DEEP@;color:@TXT@}
header[data-testid="stHeader"],footer,#MainMenu{display:none}
.block-container{padding:.5rem 1rem 0!important;max-width:100%!important}
[data-testid="stVerticalBlock"]{gap:.45rem}
[data-testid="stSidebar"]{background:@SLATE@;border-left:1px solid rgba(255,255,255,.08)}
[data-testid="stVerticalBlockBorderWrapper"]{background:@SURF@;border:1px solid rgba(255,255,255,.08)!important;border-radius:18px!important}
/* --- سرتیتر داشبورد (فشرده) --- */
.ban{--ac:@YEL@;display:flex;align-items:center;gap:18px;background:linear-gradient(120deg,@SLATE@,@SURF@);border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:8px 20px;position:relative;overflow:hidden;min-height:54px}
.ban::before{content:'';position:absolute;inset:0 auto 0 0;width:7px;background:var(--ac)}
.ban h1{font-size:1.25rem;margin:0;font-weight:800;white-space:nowrap;color:var(--ac)}
.ban .vd p{margin:0;font-size:.88rem;line-height:1.55;color:@TXT@;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ban .vd p b{color:var(--ac)}
/* --- کارت‌های اصلی صفحه‌ی اصلی: اعداد با فونت فارسی بی‌نازنین --- */
.kpi{--ac:@TEAL@;background:@SURF@;border:1px solid rgba(255,255,255,.08);border-radius:22px;padding:14px 18px;height:100%}
.kpi .kl{color:@SUB@;font-size:.95rem;display:block}
.kpi b{font-family:'BNazanin','B Nazanin',serif!important;font-size:1.9rem;font-weight:700;display:block;margin:4px 0;white-space:nowrap;direction:rtl}
.kpi b small{font-size:.45em;font-weight:600;color:@SUB@}
.kpi .kh{font-size:.85rem;color:@SUB@;display:inline-flex;align-items:center;gap:6px}
.kpi .kh::before{content:'';width:8px;height:8px;border-radius:50%;background:var(--sc,@GRN@)}
.kpi.hero{background:linear-gradient(135deg,@SLATE@,@SURF@);border:2px solid var(--ac);box-shadow:0 0 0 4px rgba(255,255,255,.03);padding:18px 26px}
.kpi.hero .kl{color:var(--ac);font-weight:700;font-size:1.1rem}
.kpi.hero b{font-size:3.4rem;font-weight:800;color:@TXT@;line-height:1.25}
.kpi.hero .kh{font-size:.95rem}
/* --- اقدام/هشدار (فشرده) --- */
.acard{--pc:@YEL@;background:@SURF@;border:1px solid rgba(255,255,255,.1);border-right:7px solid var(--pc);border-radius:16px;padding:8px 14px;margin-bottom:8px}
.acard .ah{display:flex;gap:8px;align-items:center;margin-bottom:3px}.acard .ah b{font-size:.98rem}
.pill{background:var(--pc);color:@DEEP@;border-radius:999px;padding:1px 10px;font-weight:800;font-size:.75rem}
.acard .ae{color:@SUB@;font-size:.82rem;margin-bottom:3px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.acard .as{font-size:.8rem;line-height:1.6;margin-bottom:4px}
.acard .am span{display:inline-block;background:rgba(255,255,255,.08);border-radius:999px;padding:1px 10px;margin-left:6px;font-size:.74rem}.acard .am b{color:var(--pc)}
.sumrow span{display:inline-block;background:rgba(255,255,255,.08);border-radius:999px;padding:3px 12px;margin:0 0 6px 8px;font-size:.82rem}.sumrow b{color:@YEL@}
.ct{font-weight:700;font-size:.98rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ct .cs{color:@SUB@;font-size:.76rem;font-weight:400}
.hometitle{font-size:1.5rem;font-weight:800;margin:2px 0 0}.homesub{color:@SUB@;font-size:.9rem;margin:0 0 4px}
/* --- تب‌ها --- */
div[data-baseweb="tab-list"]{gap:6px;flex-wrap:wrap;border:0;margin:2px 0 6px}
button[data-baseweb="tab"]{background:@SURF@;border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:5px 18px;height:auto}
button[data-baseweb="tab"] p{color:@TXT@!important;font-size:.9rem;font-weight:600}
button[data-baseweb="tab"][aria-selected="true"]{background:@YEL@;border-color:@YEL@}
button[data-baseweb="tab"][aria-selected="true"] p{color:@DEEP@!important;font-weight:800}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none}
[data-testid="stSidebar"] *{color:@TXT@}
[data-testid="stSidebar"] [data-baseweb="select"]>div,[data-testid="stSidebar"] input,[data-baseweb="popover"] ul{background:@SURF@!important;color:@TXT@!important;border-color:rgba(255,255,255,.18)!important}
span[data-baseweb="tag"]{background:@TEAL@!important}span[data-baseweb="tag"] *{color:@DEEP@!important}
[data-testid="stAlert"] *{color:@TXT@!important}
[data-testid="stBaseButton-secondary"]{background:@SURF@!important;border:1px solid rgba(255,255,255,.2)!important}[data-testid="stBaseButton-secondary"] *{color:@TXT@!important}
[data-testid="stBaseButton-primary"]{background:@YEL@!important;border:0!important}[data-testid="stBaseButton-primary"] *{color:@DEEP@!important}
[data-testid="stPopoverBody"]{background:@SURF@!important}[data-testid="stPopoverBody"] *{color:@TXT@}
pre,code{background:#1F3134!important;color:@TXT@!important}
"""
for _k, _v in dict(SLATE=SLATE, DEEP=DEEP, SURF=SURF, YEL=YEL, MINT=MINT, TEAL=TEAL, GRN=GRN, CORAL=CORAL, TXT=TXT, SUB=SUB).items():
    CSS = CSS.replace(f"@{_k}@", _v)
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# ------------------------------------------------------------ ابزارهای نمایش
def money(v):
    return f"{num(v)} تومان"


def mh(v):
    return f"{num(v)}<small> تومان</small>"


def kpi(col, label, value, hint, state="ok", hero=False, ac=TEAL):
    col.markdown(f'<div class="kpi {"hero" if hero else ""}" style="--ac:{ac};--sc:{STATE_C[state]}"><span class="kl">{fa(label)}</span>'
                 f'<b>{fa(value)}</b><span class="kh">{fa(hint)}</span></div>', unsafe_allow_html=True)


def head(t, s=""):
    st.markdown(f'<div class="ct">{t}' + (f'<span class="cs"> · {s}</span>' if s else "") + "</div>", unsafe_allow_html=True)


def show(fig, h=300):
    fig.update_layout(height=h, margin=dict(l=6, r=6, t=22, b=6), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family=FONT_PL, size=13, color=TXT),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None),
                      colorway=[TEAL, YEL, MINT, GRN, CORAL])
    fig.update_xaxes(gridcolor="rgba(255,255,255,.08)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.08)", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "displayModeBar": False})


def gauge_row(specs, h=150):
    """specs: (عنوان، مقدار، حداکثر، آستانه، واحد، بالاتر=بهتر)"""
    cols = st.columns(len(specs))
    for col, (title, v, mx, thr, unit, high) in zip(cols, specs):
        lo = thr * .82
        steps = ([dict(range=[0, lo], color=CORAL), dict(range=[lo, thr], color=YEL), dict(range=[thr, mx], color=GRN)] if high else
                 [dict(range=[0, thr], color=GRN), dict(range=[thr, thr * 1.5], color=YEL), dict(range=[thr * 1.5, mx], color=CORAL)])
        f = go.Figure(go.Indicator(mode="gauge+number", value=float(v), number=dict(suffix=unit, valueformat=".1f" if mx <= 20 else ".0f", font=dict(size=24, color=TXT)),
                                   title=dict(text=title, font=dict(size=14, color=SUB)),
                                   gauge=dict(axis=dict(range=[0, mx], tickcolor=SUB, tickfont=dict(color=SUB, size=10)), bar=dict(color=DEEP, thickness=.3), bgcolor="rgba(0,0,0,0)",
                                              borderwidth=0, steps=steps, threshold=dict(line=dict(color=TXT, width=3), thickness=.85, value=thr))))
        f.update_layout(height=h, margin=dict(l=18, r=18, t=34, b=2), paper_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT_PL))
        with col:
            st.plotly_chart(f, use_container_width=True, config={"displaylogo": False, "displayModeBar": False})


def P(p, title, ev, steps, owner, due, impact):
    return dict(p=p, title=title, ev=ev, steps=steps, owner=owner, due=due, impact=float(impact))


import analytics as an  # noqa: E402
import db  # noqa: E402
import shift_alerts as SA  # noqa: E402

HERE = Path(__file__).parent
NIGHT = (22, 6)  # ساعات شب برای تحلیل فعالیت (۲۲ تا ۰۶)


def empty(msg="داده‌ای برای نمایش نیست."):
    st.info(msg)


def opt(name, *a, **k):
    """واکشی اختیاری: خطا فقط یک هشدار کوچک می‌دهد و ویجت‌های وابسته خالی می‌مانند"""
    df, err = db.get(name, *a, **k)
    if err:
        st.warning(f"خواندن «{name}» ممکن نشد: {err}", icon="⚠️")
    return df


def rule_loss(tx, k):
    f = tx[tx[k] == 1]
    if k == "F_PosNoDetail": return float(f.Pos.fillna(0).sum())
    if k == "F_PayMismatch": return float((f.Cash.fillna(0) + f.Pos.fillna(0) - f.FinalPrice.fillna(0)).abs().sum())
    if k == "F_FreeExit": return float(f.TotalPrice.fillna(0).sum())
    if k == "F_Refund": return float(f.Refund.fillna(0).sum())
    return 0.0


# ============================================================ ناوبری
def go_to(k):
    st.session_state["dash"] = k
    if k:
        st.query_params["d"] = k
    else:
        st.query_params.pop("d", None)


@st.dialog("تصویر تردد", width="large")
def img_dialog(ids, with_exit=True):
    tid = st.selectbox("شناسه تردد", ids)
    if st.button("نمایش تصویر", type="primary"):
        try:
            en, exi = db.taradod_images(int(tid))
            pairs = [(en, "ورود")] + ([(exi, "خروج")] if with_exit else [])
            for col, (im, tt) in zip(st.columns(len(pairs)), pairs):
                col.markdown(f"**{tt}**")
                col.image(im) if im else col.caption("تصویری ثبت نشده")
        except Exception as e:  # noqa: BLE001
            st.warning(f"نمایش تصویر ممکن نشد: {str(e)[:200]}")


# ============================================================ بارگذاری
NOW = pd.Timestamp(db.get("server_now", required=True)[0].iloc[0, 0])
if "dash" not in st.session_state:
    st.session_state["dash"] = st.query_params.get("d")

VH_OPT = {"لپ‌تاپ کوچک (ارتفاع ≈ ۶۵۰)": 650, "لپ‌تاپ / فول‌اچ‌دی (≈ ۸۵۰)": 850, "مانیتور بزرگ (≈ ۱۰۵۰)": 1050, "۲K / ۴K (≈ ۱۳۰۰)": 1300}
with st.sidebar:
    if (HERE / "logo.jpg").exists():
        st.image(str(HERE / "logo.jpg"), use_container_width=True)
    if st.session_state.get("dash"):
        st.button("🏠 بازگشت به صفحه اصلی", key="side_home", on_click=go_to, args=(None,), use_container_width=True)
    st.markdown("#### بازه زمانی")
    preset = st.radio("بازه", ["۷ روز اخیر", "۳۰ روز اخیر", "۹۰ روز اخیر", "انتخاب دلخواه"], index=1, label_visibility="collapsed")
    if preset == "انتخاب دلخواه":
        v = st.date_input("از تاریخ تا تاریخ", (NOW.date() - pd.Timedelta(days=30), NOW.date()))
        a_, b_ = (v if len(v) == 2 else (v[0], v[0]))
        D0, D1 = pd.Timestamp(a_), pd.Timestamp(b_) + pd.Timedelta(days=1)
    else:
        n_days = {"۷ روز اخیر": 7, "۳۰ روز اخیر": 30, "۹۰ روز اخیر": 90}[preset]
        D1 = NOW.normalize() + pd.Timedelta(days=1)
        D0 = D1 - pd.Timedelta(days=n_days)
    D0, D1 = D0.to_pydatetime(), D1.to_pydatetime()
    if st.button("🔄 رفرش دستی داده", use_container_width=True, help="کش دیتابیس را پاک می‌کند"):
        st.cache_data.clear()
        st.rerun()
    vh_label = st.selectbox("اندازه‌ی صفحه نمایش", list(VH_OPT), index=1, key="vh", help="ارتفاع نمودارها را طوری تنظیم می‌کند که صفحه اسکرول نداشته باشد. اگر صفحه‌ی شما اسکرول داشت، یک گزینه‌ی کوچک‌تر انتخاب کنید.")
    VH = VH_OPT[vh_label]
    st.caption(f"زمان سرور: {fa(f'{NOW:%Y-%m-%d %H:%M:%S}')} · کش ۶۰ ثانیه")
    st.divider()


def R(n, extra=0):
    """ارتفاع نمودار برای n ردیف کارت در یک صفحه‌ی بدون اسکرول (extra = فضای اشغال‌شده‌ی دیگر)"""
    return max(150, int((VH - 150 - extra) / n - 84))


TX0 = an.prepare_taradods(db.get("taradods", D0, D1, required=True)[0])
VW0 = an.prepare_view(db.get("view", D0, D1, required=True)[0])
INS = an.prepare_inside(db.get("inside", required=True)[0], NOW)
TX0, VW0 = TX0[(TX0.Event_Time >= D0) & (TX0.Event_Time < D1)], VW0[(VW0.Event_Time >= D0) & (VW0.Event_Time < D1)]
TX, VW = TX0, VW0


# ============================================================ قطعات مشترک داشبوردها
def top(verdict):
    """نوار فشرده‌ی بالای هر داشبورد: دکمه‌ی بازگشت + عنوان + خلاصه‌ی «در یک نگاه»"""
    c1, c2 = st.columns([1.1, 9])
    c1.button("🏠 اصلی", key="home_btn", on_click=go_to, args=(None,), use_container_width=True)
    c2.markdown(f'<div class="ban" style="--ac:{CUR["ac"]}"><h1>{CUR["t"]}</h1><div class="vd"><p>{fa(verdict)}</p></div></div>', unsafe_allow_html=True)


def plan(items, ac):
    """هیئت اقدام فشرده: نمودار اثر مالی + کارت‌های اقدام (بدون کارت‌های KPI)"""
    items = sorted(items, key=lambda i: ({"فوری": 0, "مهم": 1, "پایش": 2}[i["p"]], -i["impact"]))
    cn = pd.Series([i["p"] for i in items]).value_counts()
    left, right = st.columns([2, 3])
    with left.container(border=True):
        head("اثر مالی هر اقدام", "هرچه میله بلندتر، اولویت اجرا بالاتر")
        bd = pd.DataFrame({"اقدام": [i["title"] for i in items], "اثر (تومان)": [i["impact"] for i in items], "اولویت": [i["p"] for i in items]})
        show(px.bar(bd.iloc[::-1], x="اثر (تومان)", y="اقدام", color="اولویت", orientation="h", color_discrete_map=PCOL), R(1, 30))
    with right:
        st.markdown(f'<div class="sumrow"><span>اقدام فوری: <b>{fa(cn.get("فوری", 0))}</b></span><span>مهم: <b>{fa(cn.get("مهم", 0))}</b></span>'
                    f'<span>پایشی: <b>{fa(cn.get("پایش", 0))}</b></span><span>اثر مالی قابل بازیابی: <b>{money(sum(i["impact"] for i in items))}</b></span></div>', unsafe_allow_html=True)
        k1, k2 = st.columns(2)
        for n_, i in enumerate(items):
            steps = " · ".join(fa(x) for x in i["steps"])
            (k1 if n_ % 2 == 0 else k2).markdown(
                f'<div class="acard" style="--pc:{PCOL[i["p"]]}"><div class="ah"><span class="pill">{i["p"]}</span><b>{i["title"]}</b></div>'
                f'<div class="ae">{fa(i["ev"])}</div><div class="as">{steps}</div><div class="am"><span>مسئول: <b>{i["owner"]}</b></span><span>مهلت: <b>{fa(i["due"])}</b></span>'
                f'<span>اثر: <b>{money(i["impact"])}</b></span></div></div>', unsafe_allow_html=True)


# ============================================================ ۱ · مدیریتی
def page1():
    ex, ve = TX[TX.Exited], VW[VW.Exited]
    flagged = float((ex.NFlags > 0).mean()) if len(ex) else 0.0
    loss, rev = float(ex.Loss.sum()), ex.FinalPrice.sum()
    top(f"در این بازه <b>{len(ex):,} خروج</b> با درآمد <b>{money(rev)}</b> ثبت شده؛ <b>{flagged * 100:.1f}٪</b> ترددها حداقل یک پرچم دارند و زیان مشکوک <b>{money(loss)}</b> است. "
        f"هم‌اکنون <b>{len(INS):,}</b> خودرو داخل پارکینگ است (بیش از ۴۸ ساعت: {int(INS.LongStay.sum())}).")
    T = st.tabs(["نمای کلی", "گیت‌ها و ترافیک", "درآمد", "اقدامات پیشنهادی"])
    with T[0]:
        pc = lambda s: s.mean() * 100 if len(ex) else 0  # noqa: E731
        gauge_row([("خروج با مبلغ صفر", pc(ex.F_FreeExit), 20, 5, "٪", False), ("بازپرداخت", pc(ex.F_Refund), 10, 2, "٪", False),
                   ("کارتخوان بدون ثبت پوز", pc(ex.F_PosNoDetail), 5, 1, "٪", False), ("ناهمخوانی پرداخت", pc(ex.F_PayMismatch), 10, 1.5, "٪", False)])
        a1, a2 = st.columns([3, 2])
        h = R(1, 170)
        with a1.container(border=True):
            head("روند روزانه ورود و خروج")
            dd = pd.DataFrame({"ورود": TX.groupby(TX.EnrtyDateTime.dt.normalize()).size(), "خروج": ex.groupby("Date").size()}).fillna(0)
            dd.index.name = "تاریخ"
            show(px.line(dd, markers=True, color_discrete_sequence=[TEAL, YEL]), h) if len(dd) else empty()
        with a2.container(border=True):
            head("نقشه حرارتی خروج", "روز هفته × ساعت")
            hm = ex.pivot_table(index="Weekday", columns="Hour", values="ID", aggfunc="count").reindex(index=an.WD_ORDER, columns=range(24)).fillna(0)
            show(px.imshow(hm, aspect="auto", color_continuous_scale=[DEEP, TEAL, YEL], labels=dict(x="ساعت", y="", color="خروج")), h)
    with T[1]:
        b1, b2, b3 = st.columns(3)
        h = R(1)
        with b1.container(border=True):
            head("درآمد و خروج هر گیت خروج")
            g = ve.dropna(subset=["OutputGate"]).groupby("OutputGate").agg(درآمد=("FinalPrice", "sum"), خروج=("id", "size")).reset_index()
            show(px.bar(g, x="OutputGate", y="درآمد", color="خروج", color_continuous_scale=[MINT, YEL]), h) if len(g) else empty()
        with b2.container(border=True):
            head("ورود به تفکیک گیت ورودی")
            g = VW.dropna(subset=["InputGate"]).groupby("InputGate").size().reset_index(name="ورود")
            show(px.pie(g, names="InputGate", values="ورود", hole=.55, color_discrete_sequence=PALETTE), h) if len(g) else empty()
        with b3.container(border=True):
            head("نوع خودرو (CarTypeID)")
            g = TX.groupby("CarTypeID").size().reset_index(name="تعداد")
            show(px.bar(g, x="CarTypeID", y="تعداد", color_discrete_sequence=[MINT]), h) if len(g) else empty()
    with T[2]:
        c1, c2, c3 = st.columns(3)
        h = R(1)
        with c1.container(border=True):
            head("درآمد روزانه: نقد و کارتخوان")
            r = ex.groupby("Date").agg(نقد=("Cash", "sum"), کارتخوان=("Pos", "sum")).reset_index()
            show(px.bar(r.melt("Date"), x="Date", y="value", color="variable", color_discrete_sequence=[YEL, TEAL]), h) if len(r) else empty()
        with c2.container(border=True):
            head("اختلاف FinalPrice و TotalPrice", "منفی = تخفیف/معافیت")
            dif = (ex.FinalPrice - ex.TotalPrice).dropna()
            show(px.histogram(dif[dif != 0], nbins=40, color_discrete_sequence=[CORAL]).update_layout(xaxis_title="تومان", showlegend=False), h) if (dif != 0).any() else empty("اختلافی نیست.")
        with c3.container(border=True):
            head("گزارش مالی روزانه", "View_FinancialReports")
            fin = opt("financial", limit=60)
            if len(fin):
                f = fin.sort_values("Date_Farsi")
                show(px.line(f.melt("Date_Farsi", ["TotalFinalPrice", "TotalWebIncome"]), x="Date_Farsi", y="value", color="variable", markers=True, color_discrete_sequence=[TEAL, YEL]), h)
            else:
                empty()
    with T[3]:
        top_k = max(an.RULES, key=lambda k: rule_loss(ex, k))
        plan([
            P("فوری" if ex.F_PosNoDetail.sum() else "پایش", "کارتخوان بدون ثبت پوز", f"{int(ex.F_PosNoDetail.sum())} تردد با Pos>0 و بدون PosDetailID · {money(rule_loss(ex, 'F_PosNoDetail'))}",
              ["بازبینی تراکنش بانکی هر مورد", "الزام ثبت PosDetailID هنگام خروج", "پیگیری با شرکت PSP"], "حسابداری", "۷ روز", rule_loss(ex, "F_PosNoDetail")),
            P("فوری" if ex.F_Refund.sum() else "پایش", "کنترل بازپرداخت‌ها", f"{int(ex.F_Refund.sum())} تردد با Refund>0 · {money(rule_loss(ex, 'F_Refund'))}",
              ["تایید کتبی سرپرست برای هر بازپرداخت", "بررسی کاربران تکرارکننده"], "مدیر مالی", "۷ روز", rule_loss(ex, "F_Refund")),
            P("مهم", f"بیشترین نشت: «{an.RULES[top_k][0]}»", f"{money(rule_loss(ex, top_k))} در این بازه", ["بازنویسی قانون مربوط و پایش هفتگی", "گزارش به حراست"], "مدیر عملیات", "۳۰ روز", rule_loss(ex, top_k)),
            P("مهم" if INS.LongStay.sum() else "پایش", "خودروهای بیش از ۴۸ ساعت", f"{int(INS.LongStay.sum())} خودرو هنوز خارج نشده‌اند", ["تطبیق با دوربین طبقات", "پیگیری مالک خودرو"], "مدیر پارکینگ", "۳ روز", INS.LongStay.sum() * 20000),
        ], YEL)


# ============================================================ ۲ · حراست و ممیزی
def page2():
    ex = TX[TX.Exited]
    dl = opt("discount_logs", D0, D1)
    dcodes = opt("discount_codes", limit=5000)
    rows = [dict(روش=v[0], دسته="مالی و پرداخت" if k != "F_Lost" else "فیش", تعداد=int(ex[k].sum()), زیان=rule_loss(ex, k), وزن=v[1], معادل_در_سند=v[2], منطق=v[3]) for k, v in an.RULES.items()]
    dr, ol = an.discount_reuse(dl), an.over_limit_codes(dcodes)
    rows += [dict(روش="ورود باز با کارت مشترک", دسته="تکرار", تعداد=int(INS.DupCard.sum()), زیان=0.0, وزن=30, معادل_در_سند="نقض توالی تردد", منطق="چند ردیف بدون خروج با CardID یکسان"),
             dict(روش="ورود باز با پلاک مشترک", دسته="تکرار", تعداد=int(INS.DupPlate.sum()), زیان=0.0, وزن=30, معادل_در_سند="نقض توالی تردد", منطق="چند ردیف بدون خروج با PlateID یکسان (PlateID>0)"),
             dict(روش="خودروی بیش از ۴۸ ساعت داخل", دسته="رسوبی", تعداد=int(INS.LongStay.sum()), زیان=0.0, وزن=15, معادل_در_سند="خودروی رسوبی", منطق="ExitDateTime خالی و ورود بیش از ۴۸ ساعت قبل"),
             dict(روش="کد تخفیف تکراری", دسته="تخفیف", تعداد=len(dr), زیان=0.0, وزن=25, معادل_در_سند="تکرار بن تخفیف", منطق="DiscountCode با بیش از یک ثبت در DiscountLogs"),
             dict(روش="کد تخفیف بیش از سقف", دسته="تخفیف", تعداد=len(ol), زیان=0.0, وزن=25, معادل_در_سند="تکرار بن تخفیف", منطق="UsedCount بیشتر از MaxCount")]
    mt = pd.DataFrame(rows)
    nflag = int((ex.NFlags > 0).sum())
    top(f"<b>{nflag:,}</b> تردد پرچم‌دار از <b>{len(ex):,}</b> خروج؛ زیان مشکوک <b>{money(float(ex.Loss.sum()))}</b>، بیشترین زیان مربوط به <b>{mt.sort_values('زیان').iloc[-1]['روش']}</b>. "
        f"<b>{int(mt.loc[mt.دسته.isin(['تکرار', 'تخفیف', 'رسوبی']), 'تعداد'].sum())}</b> مورد تکرار/تخفیف/رسوبی هم ثبت شده.")
    T = st.tabs(["روش‌های تخلف", "نقشه زمانی و گیت", "ترددهای پرریسک", "تکرار و محدودیت‌ها", "اقدامات پیشنهادی"])
    with T[0]:
        a1, a2 = st.columns([3, 2])
        with a1.container(border=True):
            head("نقشه روش‌های تخلف", "افقی: تعداد · عمودی: زیان · اندازه: وزن ریسک")
            show(px.scatter(mt[mt.تعداد > 0], x="تعداد", y="زیان", size="وزن", color="دسته", text="روش", size_max=34, color_discrete_sequence=PALETTE).update_traces(textposition="top center"), R(2)) if (mt.تعداد > 0).any() else empty()
        with a2.container(border=True):
            head("پارتو: تعداد هر روش")
            p = mt[mt.تعداد > 0].sort_values("تعداد", ascending=False)
            if len(p):
                cum = p.تعداد.cumsum() / p.تعداد.sum()
                f = go.Figure([go.Bar(x=p.روش, y=p.تعداد, marker_color=MINT, name="تعداد"), go.Scatter(x=p.روش, y=cum, yaxis="y2", line=dict(color=YEL), name="تجمعی")])
                f.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 1.02], tickformat=".0%", showgrid=False))
                show(f, R(2))
            else:
                empty()
        with st.container(border=True):
            head("منطق کشف هر روش", "برگرفته از سند کشف تقلب؛ ستونی که در دیتابیس نبود پیاده نشده")
            st.dataframe(mt, hide_index=True, use_container_width=True, height=R(2) - 10, column_config={"زیان": st.column_config.NumberColumn("زیان (تومان)", format="%d")})
    with T[1]:
        b1, b2 = st.columns(2)
        with b1.container(border=True):
            head("نقشه حرارتی پرچم‌ها", "روز هفته × ساعت")
            hm = ex.assign(n=ex.NFlags).pivot_table(index="Weekday", columns="Hour", values="n", aggfunc="sum").reindex(index=an.WD_ORDER, columns=range(24)).fillna(0)
            show(px.imshow(hm, aspect="auto", color_continuous_scale=[DEEP, TEAL, YEL], labels=dict(x="ساعت", y="", color="پرچم")), R(2))
        with b2.container(border=True):
            head("پرچم‌ها به تفکیک گیت خروج (OutputGateID)")
            g = ex.groupby("OutputGateID")[list(an.RULES)].sum().rename(columns={k: v[0] for k, v in an.RULES.items()}).reset_index().melt("OutputGateID")
            g["OutputGateID"] = g.OutputGateID.astype(str)
            show(px.bar(g, x="OutputGateID", y="value", color="variable", color_discrete_sequence=PALETTE).update_layout(xaxis_title="شناسه گیت خروج", yaxis_title="تعداد"), R(2))
        with st.container(border=True):
            head("روند روزانه پرچم‌ها")
            r = ex.groupby("Date")[list(an.RULES)].sum().rename(columns={k: v[0] for k, v in an.RULES.items()}).reset_index().melt("Date")
            show(px.bar(r, x="Date", y="value", color="variable", color_discrete_sequence=PALETTE), R(2))
    with T[2]:
        hi = ex[ex.Risk_Score > 0].sort_values(["Risk_Score", "Loss"], ascending=False)
        cols = ["ID", "ExitDateTime", "ExitUserID", "OutputGateID", "TotalPrice", "FinalPrice", "Cash", "Pos", "Refund", "Loss", "Risk_Score", "Risk_Level"]
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1.2, 1.4])
            with c1:
                head("ترددهای پرریسک", "امتیاز ریسک = مجموع وزن قوانین (سقف ۱۰۰)")
            c2.download_button("دانلود CSV", hi[cols].to_csv(index=False).encode("utf-8-sig"), "high_risk.csv", "text/csv", use_container_width=True)
            if c3.button("🖼 تصویر تردد", key="img_risk", use_container_width=True, disabled=hi.empty):
                img_dialog(hi.ID.head(500).astype(int).tolist(), True)
            st.dataframe(hi[cols].head(500), hide_index=True, use_container_width=True, height=R(1, 20),
                         column_config={"Risk_Score": st.column_config.ProgressColumn("امتیاز", min_value=0, max_value=100, format="%d"), "Loss": st.column_config.NumberColumn("زیان (تومان)", format="%d")})
    with T[3]:
        d1_, d2_ = st.columns(2)
        with d1_.container(border=True):
            head("ورود باز با کارت یا پلاک مشترک", "ردیف‌های بدون خروج")
            x = INS[INS.DupCard | INS.DupPlate]
            st.dataframe(x[["ID", "CardID", "PlateID", "EnrtyDateTime", "InputGateID", "Age_H"]], hide_index=True, use_container_width=True, height=R(2)) if len(x) else empty("موردی نیست.")
        with d2_.container(border=True):
            head("کدهای تخفیف تکراری")
            st.dataframe(dr, hide_index=True, use_container_width=True, height=R(2)) if len(dr) else empty("موردی نیست.")
        with st.container(border=True):
            head("کدهای تخفیف بیش از سقف استفاده", "UsedCount > MaxCount")
            st.dataframe(ol[["ID", "Code", "DiscountType", "Amount", "UsedCount", "MaxCount", "DailyCount", "Active", "ExpireDate"]], hide_index=True, use_container_width=True, height=R(2)) if len(ol) else empty("موردی نیست.")
    with T[4]:
        top2 = mt[mt.تعداد > 0].sort_values("تعداد", ascending=False).head(2)
        items = [P("فوری", f"بازنویسی قانون «{r['روش']}»", f"{r['تعداد']} رخداد · زیان {money(r['زیان'])}", ["تبدیل شرط به قانون لحظه‌ای", "ارزیابی ماهانه مثبت کاذب", "فعال‌سازی پیامک شیفت"], "تیم علم داده", "۷ روز", r["زیان"]) for _, r in top2.iterrows()]
        items += [P("مهم" if len(dr) else "پایش", "قفل استفاده‌ی مکرر از کد تخفیف", f"{len(dr)} کد با بیش از یک استفاده · {len(ol)} کد بیش از سقف", ["ابطال خودکار کد پس از اولین استفاده", "بازبینی صادرکنندگان کد"], "مدیر عملیات", "۱۰ روز", len(dr) * 20000),
                  P("مهم" if (INS.DupCard.sum() or INS.DupPlate.sum()) else "پایش", "ورودهای باز تکراری", f"{int(INS.DupCard.sum())} ردیف کارت مشترک · {int(INS.DupPlate.sum())} ردیف پلاک مشترک", ["اعتبارسنجی خروج قبل از ورود مجدد", "بازبینی دستی ردیف‌ها"], "مدیر پارکینگ", "۷ روز", 0)]
        plan(items, MINT)


# ============================================================ ۳ · عملیات و اپراتور
def page3():
    prof, z, hit = an.operator_profile(VW)
    top((f"<b>بازرسی سرزده برای {'، '.join(map(str, hit))}</b> لازم است (Z نسبت نقد و خروج رایگان بیش از ۲.۵). " if hit else "اپراتوری از آستانه‌ی بازرسی سرزده (Z=2.5) عبور نکرده. ")
        + f"<b>{int(INS.LongStay.sum())}</b> خودرو از <b>{len(INS)}</b> خودروی داخل بیش از ۴۸ ساعت مانده است.")
    T = st.tabs(["اپراتورها", "خودروهای داخل", "اقدامات پیشنهادی"])
    with T[0]:
        if prof.empty:
            empty("داده‌ی کافی برای پروفایل نیست.")
        else:
            a1, a2 = st.columns([2, 3])
            with a1.container(border=True):
                head("Z-Score ترکیبی", "بالاتر از میانگین همکاران = مشکوک‌تر")
                zz = prof["Z ترکیبی"].sort_values().reset_index()
                zz.columns = ["اپراتور", "Z"]
                show(px.bar(zz, x="Z", y="اپراتور", orientation="h", color="Z", color_continuous_scale=[TEAL, YEL, CORAL]), R(2))
            with a2.container(border=True):
                head("رادار رفتار صندوقدار", "هر محور نسبت به بیشترین مقدار همکاران")
                sel = st.selectbox("صندوقدار", list(prof.index), label_visibility="collapsed")
                cols = ["نسبت نقد", "نرخ خروج رایگان", "نرخ تخفیف", "نرخ مهمان", "نرخ اشتراکی"]
                nm = prof[cols] / prof[cols].max().replace(0, 1)
                f = go.Figure([go.Scatterpolar(r=list(nm.loc[sel]) + [nm.loc[sel].iloc[0]], theta=cols + cols[:1], fill="toself", name=str(sel), line_color=CORAL),
                               go.Scatterpolar(r=list(nm.mean()) + [nm.mean().iloc[0]], theta=cols + cols[:1], fill="toself", name="میانگین همکاران", line_color=MINT)])
                f.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 1], gridcolor="rgba(255,255,255,.15)")))
                show(f, R(2) - 48)
        r1, r2 = st.columns(2)
        with r1.container(border=True):
            head("پروفایل اپراتورها", "بر اساس نام ExitUser")
            st.dataframe(prof.round(3), use_container_width=True, height=R(2), column_config={"درآمد": st.column_config.NumberColumn("درآمد (تومان)", format="%d")}) if len(prof) else empty()
        with r2.container(border=True):
            head("پروفایل بر اساس شناسه کاربر خروج", "Taradods.ExitUserID")
            st.dataframe(an.id_profile(TX).round(2), use_container_width=True, height=R(2), column_config={"مبلغ بازپرداخت": st.column_config.NumberColumn("مبلغ بازپرداخت (تومان)", format="%d")})
    with T[1]:
        x = INS.sort_values("Age_H", ascending=False)
        l_, r_ = st.columns([3, 2])
        with l_.container(border=True):
            c1, c2 = st.columns([4, 1.4])
            with c1:
                head("کارتابل خودروهای داخل پارکینگ", "ExitDateTime خالی · مرتب بر اساس مدت حضور")
            if c2.button("🖼 تصویر ورود", key="img_ins", use_container_width=True, disabled=x.empty):
                img_dialog(x.ID.head(200).astype(int).tolist(), False)
            st.dataframe(x[["ID", "CardID", "PlateID", "EnrtyDateTime", "InputGateID", "Age_H", "LongStay", "DupCard", "DupPlate", "IsLost"]].head(500), hide_index=True, use_container_width=True, height=R(1, 20),
                         column_config={"Age_H": st.column_config.ProgressColumn("ساعت حضور", min_value=0, max_value=float(max(x.Age_H.max(), 48)) if len(x) else 48, format="%.0f")})
        with r_.container(border=True):
            head("توزیع مدت حضور خودروهای داخل (ساعت)")
            show(px.histogram(INS, x="Age_H", nbins=40, color_discrete_sequence=[TEAL]), R(1)) if len(INS) else empty()
    with T[2]:
        items = []
        if hit:
            items.append(P("فوری", "بازرسی سرزده", f"{'، '.join(map(str, hit))}: Z نسبت نقد و Z خروج رایگان از ۲.۵ گذشت", ["حضور بازرس در باجه", "تطبیق دخل و ترددهای رایگان"], "مدیر شیفت", "۲۴ ساعت", 0))
        elif len(prof):
            t = prof["Z ترکیبی"].idxmax()
            items.append(P("پایش", f"پایش {t}", f"بالاترین Z ترکیبی ({prof.loc[t, 'Z ترکیبی']:.2f})", ["مقایسه ماهانه با همکاران"], "سرپرست شیفت", "۳۰ روز", 0))
        items.append(P("فوری" if INS.LongStay.sum() else "پایش", "خودروهای بیش از ۴۸ ساعت", f"{int(INS.LongStay.sum())} خودرو", ["بازبینی تصویر ورود", "تطبیق با دوربین طبقات", "گزارش به حراست"], "مدیر پارکینگ", "۲۴ ساعت", INS.LongStay.sum() * 20000))
        items.append(P("مهم" if (INS.DupCard.sum() or INS.DupPlate.sum()) else "پایش", "ورودهای باز تکراری", f"{int(INS.DupCard.sum())} کارت مشترک · {int(INS.DupPlate.sum())} پلاک مشترک", ["اعتبارسنجی خروج قبل از ورود مجدد"], "مدیر پارکینگ", "۷ روز", 0))
        plan(items, TEAL)


# ============================================================ ۴ · فنی و تجهیزات
def page_tech():
    anpr = opt("anpr", D0, D1)
    asum, agap = an.anpr_summary(anpr), an.anpr_gaps(anpr)
    noise = int(asum["نویز (<0.60)"].sum()) if len(asum) else 0
    top(f"<b>{noise:,}</b> خوانش ANPR با اطمینان زیر {an.LOW_CONF} (نویز) ثبت شده"
        + (f"؛ بیشترین وقفه‌ی خوانش مربوط به گیت <b>{agap.iloc[0]['GateId']}</b> و برابر <b>{agap.iloc[0]['بیشترین فاصله (دقیقه)']}</b> دقیقه است." if len(agap) else "."))
    T = st.tabs(["دوربین پلاک‌خوان (ANPR)", "راهبند", "ممیزی سیستم", "اقدامات پیشنهادی"])
    with T[0]:
        if anpr.empty:
            empty("خوانش ANPR در این بازه نیست.")
        else:
            g1, g2 = st.columns(2)
            with g1.container(border=True):
                head("اطمینان خوانش ANPR به تفکیک گیت", f"خط نقطه‌چین = مرز نویز {an.LOW_CONF}")
                a = anpr.assign(Confidence=pd.to_numeric(anpr.Confidence, errors="coerce"), GateId=anpr.GateId.astype(str))
                fg = px.box(a, x="GateId", y="Confidence", color_discrete_sequence=[MINT])
                fg.add_hline(y=an.LOW_CONF, line_dash="dot", line_color=YEL)
                show(fg, R(2))
            with g2.container(border=True):
                head("بیشترین فاصله بین دو خوانش هر گیت", "نشانه‌ی احتمالی قطعی دوربین")
                st.dataframe(agap, hide_index=True, use_container_width=True, height=R(2))
            with st.container(border=True):
                head("خلاصه کیفیت ANPR")
                st.dataframe(asum.round(3), hide_index=True, use_container_width=True, height=R(2))
    with T[1]:
        bl = opt("barrier", D0, D1)
        if bl.empty:
            empty("لاگ راهبند در این بازه نیست.")
        else:
            bl = bl.assign(LogDateTime=pd.to_datetime(bl.LogDateTime))
            msgs = st.multiselect("پیام‌ها", sorted(bl.Message.dropna().unique()), default=sorted(bl.Message.dropna().unique())[:3])
            x = bl[bl.Message.isin(msgs)] if msgs else bl
            h1, h2 = st.columns(2)
            with h1.container(border=True):
                head("ساعت رخداد پیام‌ها به تفکیک گیت", "BarrierLogs")
                show(px.histogram(x.assign(ساعت=x.LogDateTime.dt.hour), x="ساعت", color=x.GateId.astype(str), nbins=24, color_discrete_sequence=PALETTE), R(1, 80))
            with h2.container(border=True):
                head("پرتکرارترین پیام‌ها", "معنی هر Message در اسکیما توضیح داده نشده")
                top_ = bl.groupby(["GateId", "Message"]).size().reset_index(name="تعداد").sort_values("تعداد", ascending=False).head(15)
                st.dataframe(top_, hide_index=True, use_container_width=True, height=R(1, 80))
    with T[2]:
        act, ev, ses = opt("activity", D0, D1), opt("events", D0, D1), opt("sessions", D0, D1)
        m1, m2 = st.columns(2)
        with m1.container(border=True):
            head("فعالیت‌ها به تفکیک عنوان", "ActivityLogs ← Activities")
            if act.empty: empty()
            else: show(px.bar(act.groupby("ActivityTitle").size().reset_index(name="تعداد").sort_values("تعداد").tail(15), x="تعداد", y="ActivityTitle", orientation="h", color_discrete_sequence=[MINT]), R(2))
        with m2.container(border=True):
            head("فعالیت کاربران در ساعات شب (۲۲ تا ۰۶)", "EventLogs")
            if ev.empty: empty()
            else:
                e = ev.assign(ServerTime=pd.to_datetime(ev.ServerTime))
                night = e[(e.ServerTime.dt.hour >= NIGHT[0]) | (e.ServerTime.dt.hour < NIGHT[1])]
                show(px.bar(night.groupby("UserName").size().reset_index(name="تعداد").sort_values("تعداد").tail(15), x="تعداد", y="UserName", orientation="h", color_discrete_sequence=[CORAL]), R(2)) if len(night) else empty("فعالیت شبانه‌ای نیست.")
        with st.container(border=True):
            head("نشست‌های کاربران", "نشست‌های بدون زمان خروج و ورودهای شبانه")
            if ses.empty: empty()
            else:
                s = ses.assign(ServerLoginTime=pd.to_datetime(ses.ServerLoginTime), ServerLogoffTime=pd.to_datetime(ses.ServerLogoffTime))
                s["ورود شبانه"] = (s.ServerLoginTime.dt.hour >= NIGHT[0]) | (s.ServerLoginTime.dt.hour < NIGHT[1])
                s["بدون خروج"] = s.ServerLogoffTime.isna()
                st.dataframe(s[s["ورود شبانه"] | s["بدون خروج"]][["ID", "UserName", "ClientIP", "ServerLoginTime", "ServerLogoffTime", "LogoffReason", "ورود شبانه", "بدون خروج"]].head(300),
                             hide_index=True, use_container_width=True, height=R(2))
    with T[3]:
        items = []
        if len(agap):
            items.append(P("مهم", f"بررسی دوربین گیت {agap.iloc[0]['GateId']}", f"بیشترین وقفه خوانش {agap.iloc[0]['بیشترین فاصله (دقیقه)']} دقیقه", ["تست دوربین و نور", "بررسی قطعی شبکه"], "فنی سخت‌افزار", "۷ روز", 0))
        items.append(P("پایش", "کالیبراسیون ANPR", f"{noise:,} خوانش زیر {an.LOW_CONF} (نویز)", ["تنظیم زاویه و نور", "حذف نویز از شاخص تقلب"], "فنی سخت‌افزار", "۳۰ روز", 0))
        items.append(P("پایش", "بازبینی نشست‌های شبانه و بدون خروج", "در تب «ممیزی سیستم» فهرست شده است", ["تطبیق با برنامه‌ی شیفت", "قفل خودکار نشست‌های باز"], "مدیر فناوری", "۱۴ روز", 0))
        plan(items, TEAL)


# ============================================================ ۵ · مالی و حسابداری
def page4():
    ex = TX[TX.Exited]
    pos, req, ri = opt("pos_tx", D0, D1), opt("pay_requests", D0, D1), opt("real_income", D0, D1)
    dl, codes, guests = opt("discount_logs", D0, D1), opt("discount_codes", limit=5000), opt("guests", D0, D1)
    cards, blocked = opt("cards", limit=5000), opt("blocked", limit=2000)
    dr, ol = an.discount_reuse(dl), an.over_limit_codes(codes)
    pos_sum = pd.to_numeric(pos.Amount, errors="coerce").sum() if len(pos) else 0
    edited = int(ri.IsEdited.fillna(False).astype(bool).sum()) if len(ri) else 0
    top(f"تراکنش‌های کارتخوان <b>{money(pos_sum)}</b> و درآمد ثبت‌شده‌ی سامانه <b>{money(ex.FinalPrice.sum())}</b> است. "
        f"<b>{len(dr)}</b> کد تخفیف تکراری، <b>{len(ol)}</b> کد بیش از سقف و <b>{edited}</b> ردیف درآمد واقعی ویرایش‌شده دیده شد؛ پلاک مسدود: <b>{len(blocked)}</b>.")
    T = st.tabs(["کارتخوان", "درآمد ثبت‌شده و واقعی", "تخفیف", "اشتراک، مهمان و مسدودی", "اقدامات پیشنهادی"])
    with T[0]:
        p1, p2, p3 = st.columns(3)
        with p1.container(border=True):
            head("وضعیت تراکنش‌های کارتخوان")
            show(px.pie(pos.groupby("Status").size().reset_index(name="تعداد"), names="Status", values="تعداد", hole=.55, color_discrete_sequence=PALETTE), R(2)) if len(pos) else empty()
        with p2.container(border=True):
            head("مبلغ روزانه کارتخوان")
            if len(pos):
                q = pos.assign(Amount=pd.to_numeric(pos.Amount, errors="coerce"), d=pd.to_datetime(pos.TransactionDateTime).dt.normalize()).groupby("d").Amount.sum().reset_index()
                show(px.bar(q, x="d", y="Amount", color_discrete_sequence=[TEAL]), R(2))
            else: empty()
        with p3.container(border=True):
            head("مبلغ هر ترمینال", "PosTerminalNo")
            if len(pos):
                q = pos.assign(Amount=pd.to_numeric(pos.Amount, errors="coerce")).groupby(["PosTerminalNo"]).Amount.agg(["sum", "count"]).reset_index()
                q["PosTerminalNo"] = q.PosTerminalNo.astype(str)
                show(px.bar(q, x="PosTerminalNo", y="sum", color="count", color_continuous_scale=[MINT, YEL]), R(2))
            else: empty()
        with st.container(border=True):
            head("درخواست‌های پرداخت", "PaymentRequests")
            if len(req):
                q = req.assign(Price=pd.to_numeric(req.Price, errors="coerce")).groupby("Status").agg(تعداد=("ID", "size"), مبلغ=("Price", "sum")).reset_index()
                st.dataframe(q, hide_index=True, use_container_width=True, height=R(2))
            else: empty()
    with T[1]:
        with st.container(border=True):
            head("درآمد روزانه: ثبت‌شده در سامانه در برابر درآمد واقعی", "بین RealIncomes و Taradods رابطه‌ی FK ثبت نشده؛ مغایرت خودکار محاسبه نمی‌شود")
            sysd = ex.groupby("Date").agg(نقد_سامانه=("Cash", "sum"), کارتخوان_سامانه=("Pos", "sum"))
            if len(ri):
                r = ri.assign(d=pd.to_datetime(ri.DateTime).dt.normalize(), Pecuniary=pd.to_numeric(ri.Pecuniary, errors="coerce"), Pos=pd.to_numeric(ri.Pos, errors="coerce")).groupby("d").agg(نقد_واقعی=("Pecuniary", "sum"), کارتخوان_واقعی=("Pos", "sum"))
                m = sysd.join(r, how="outer").fillna(0)
                m.index.name = "تاریخ"
                show(px.line(m.reset_index().melt("تاریخ"), x="تاریخ", y="value", color="variable", markers=True, color_discrete_sequence=PALETTE), R(2))
            else: empty("درآمد واقعی در این بازه ثبت نشده.")
        with st.container(border=True):
            head("ردیف‌های درآمد واقعی", "IsEdited و Closed")
            if len(ri):
                st.dataframe(ri[["ID", "DateTime", "Pecuniary", "Pos", "CreatorUserID", "SupervisorID", "IsEdited", "Closed", "SetPosTransaction"]].head(300), hide_index=True, use_container_width=True, height=R(2))
            else: empty()
    with T[2]:
        t1, t2 = st.columns(2)
        with t1.container(border=True):
            head("کدهای تخفیف تکراری")
            st.dataframe(dr, hide_index=True, use_container_width=True, height=R(2)) if len(dr) else empty("موردی نیست.")
        with t2.container(border=True):
            head("مصرف کدها نسبت به سقف", "ViewDiscountCodes")
            if len(codes):
                q = codes.assign(UsedCount=pd.to_numeric(codes.UsedCount, errors="coerce"), MaxCount=pd.to_numeric(codes.MaxCount, errors="coerce")).dropna(subset=["MaxCount"])
                q = q[q.MaxCount > 0].assign(نسبت=lambda x: x.UsedCount / x.MaxCount).sort_values("نسبت", ascending=False).head(20)
                show(px.bar(q, x="Code", y="نسبت", color_discrete_sequence=[YEL]), R(2)) if len(q) else empty()
            else: empty()
        with st.container(border=True):
            head("سهم ترددهای تخفیف‌خورده به تفکیک صندوقدار")
            ve = VW[VW.Exited & VW.ExitUser.notna()]
            if len(ve):
                g = ve.groupby("ExitUser").IsDiscount.mean().sort_values().tail(15).reset_index()
                show(px.bar(g, x="IsDiscount", y="ExitUser", orientation="h", color_discrete_sequence=[CORAL]).update_xaxes(tickformat=".0%"), R(2))
            else: empty()
    with T[3]:
        u1, u2 = st.columns(2)
        with u1.container(border=True):
            head("ثبت مهمان به تفکیک شناسه کاربر", "Guests.UserID")
            if len(guests):
                show(px.bar(guests.groupby("UserID").size().reset_index(name="تعداد").assign(UserID=lambda x: x.UserID.astype(str)).sort_values("تعداد").tail(15), x="تعداد", y="UserID", orientation="h", color_discrete_sequence=[MINT]), R(2))
            else: empty()
        with u2.container(border=True):
            head("کارت‌های اشتراکی منقضی‌شده ولی فعال", "Active=1 و EndDate گذشته")
            if len(cards):
                x = cards.assign(EndDate=pd.to_datetime(cards.EndDate))
                x = x[x.Active.fillna(False).astype(bool) & (x.EndDate < NOW)]
                st.dataframe(x[["FullName", "TagID", "Title", "EndDate"]].head(200), hide_index=True, use_container_width=True, height=R(2)) if len(x) else empty("موردی نیست.")
            else: empty()
        with st.container(border=True):
            head("پلاک‌های مسدود", "BlockPlates ← Plates")
            st.dataframe(blocked[["Id", "P1", "P2", "P3", "P4", "CreateDate", "UpdateDate"]], hide_index=True, use_container_width=True, height=R(2)) if len(blocked) else empty()
    with T[4]:
        plan([P("فوری" if len(dr) else "پایش", "کنترل کد تخفیف", f"{len(dr)} کد تکراری · {len(ol)} کد بیش از سقف", ["ابطال خودکار پس از استفاده", "بررسی صادرکنندگان کد"], "مدیر عملیات", "۱۰ روز", len(dr) * 20000),
              P("مهم" if edited else "پایش", "ممیزی ویرایش درآمد واقعی", f"{edited} ردیف RealIncomes ویرایش شده", ["مقایسه نسخه‌ی قبل و بعد با سرپرست", "الزام تایید دوم برای ویرایش"], "حسابرسی داخلی", "۷ روز", 0),
              P("مهم", "تطبیق درآمد سامانه با درآمد واقعی", "تفاوت روزانه را در تب «درآمد ثبت‌شده و واقعی» ببینید", ["تعیین رابطه‌ی رسمی بین RealIncomes و Taradods", "گزارش تفاوت روزانه به مدیر مالی"], "مدیر مالی", "۳۰ روز", 0)], GRN)


# ============================================================ ۶ · هشدار لحظه‌ای شیفت
def page5():
    anpr, dl = opt("anpr", D0, D1), opt("discount_logs", D0, D1)
    days = sorted(TX0.Date.dropna().dt.date.unique())
    if not days:
        top("داده‌ای در این بازه نیست.")
        empty()
        return
    with st.sidebar:
        st.markdown("#### فیلترهای هشدار")
        day = st.selectbox("تاریخ شیفت", days, index=len(days) - 1)
        shift = st.radio("شیفت", ["صبح", "عصر", "شب"], horizontal=True, index=1)
        sevf = st.multiselect("شدت", ["فوری", "مهم", "پایش"], default=["فوری", "مهم", "پایش"])
    al = SA.evaluate(TX0, VW0, INS, anpr, dl, day, shift)
    if len(al):
        al = al[al.severity.isin(sevf)].reset_index(drop=True)
    cn = al.severity.value_counts() if len(al) else pd.Series(dtype=int)
    top(f"شیفت <b>{shift}</b> · {day}: <b>{cn.get('فوری', 0)} هشدار فوری</b> و <b>{cn.get('مهم', 0)} هشدار مهم</b> و {cn.get('پایش', 0)} هشدار پایشی؛ "
        f"هشدار فوری به مدیر شیفت، حراست و مدیر پارکینگ پیامک می‌شود (جمع بخش‌های پیامک: {int(sum(SA.sms_segments(m_) for m_ in al.message)) if len(al) else 0}).")
    T = st.tabs(["هشدارهای شیفت", "پیامک و ارسال", "قوانین", "راه‌اندازی"])
    with T[0]:
        if al.empty:
            st.success("در این شیفت هشداری ثبت نشده است.")
        else:
            x1, x2 = st.columns(2)
            h = R(1, 175)
            with x1.container(border=True):
                head("هشدار به تفکیک قانون")
                show(px.bar(al.groupby(["title", "severity"]).size().reset_index(name="تعداد"), x="تعداد", y="title", color="severity", orientation="h", color_discrete_map=PCOL).update_layout(yaxis_title=""), h)
            with x2.container(border=True):
                head("خط زمانی هشدارها")
                show(px.scatter(al.assign(ساعت=pd.to_datetime(al.time)), x="ساعت", y="severity", color="severity", size="count", hover_data=["title", "entity"], color_discrete_map=PCOL,
                                category_orders={"severity": ["پایش", "مهم", "فوری"]}), h)
            for col, (_, a_) in zip(st.columns(4), al.head(4).iterrows()):
                roles = "، ".join(SA.ROLE_FA[r_] for r_ in a_.roles) or "فقط داشبورد"
                col.markdown(f'<div class="acard" style="--pc:{PCOL[a_.severity]}"><div class="ah"><span class="pill">{a_.severity}</span><b>{a_.title}</b></div><div class="ae">{fa(a_.message)}</div>'
                             f'<div class="am"><span>گیرنده: <b>{roles}</b></span></div></div>', unsafe_allow_html=True)
    with T[1]:
        try:
            sec = dict(st.secrets.get("sms", {}))
        except Exception:  # noqa: BLE001
            sec = {}
        rec = dict(sec.get("recipients", {})) or {"shift_manager": ["09120000001"], "security": ["09350000002"], "site_manager": ["09120000003"]}
        l_, r_ = st.columns([2, 3])
        with l_.container(border=True):
            head("گیرندگان و ارسال", "شماره‌ها را در secrets بخش [sms.recipients] بگذارید")
            st.dataframe(pd.DataFrame([{"نقش": SA.ROLE_FA.get(k, k), "شماره‌ها": "، ".join(x[:4] + "***" + x[-3:] for x in v_)} for k, v_ in rec.items()]), hide_index=True, use_container_width=True, height=150)
            real = st.checkbox("ارسال واقعی (نیازمند کلید API در secrets)", value=False)
            minsev = st.selectbox("حداقل شدت برای ارسال", ["فوری", "مهم", "پایش"], index=1)
            if st.button("ارسال پیامک‌ها", type="primary", disabled=al.empty, use_container_width=True):
                gw = SA.SMSGateway(sec.get("provider"), sec.get("api_key"), sec.get("sender"), dry_run=not real)
                res = SA.dispatch(al, gw, rec, SA.AlertStore() if real else None, minsev)
                st.dataframe(pd.DataFrame(res), hide_index=True, use_container_width=True, height=120)
                st.success(f"{sum(r2['ok'] for r2 in res)} از {len(res)} ارسال موفق" + (" (حالت آزمایشی؛ پیامکی ارسال نشد)" if gw.dry else ""))
        with r_.container(border=True):
            head("پیش‌نمایش پیامک‌ها")
            if len(al):
                st.dataframe(pd.DataFrame({"شدت": al.severity, "متن پیامک": al.message, "بخش": [SA.sms_segments(m_) for m_ in al.message], "گیرنده": [" + ".join(SA.ROLE_FA[r3] for r3 in r) or "-" for r in al.roles]}),
                             hide_index=True, use_container_width=True, height=R(1, 20))
            else:
                empty("هشداری برای ارسال نیست.")
    with T[2]:
        rules = [(r_[0], r_[3], r_[2], "، ".join(SA.ROLE_FA[x] for x in SA.ROUTING[r_[2]]) or "داشبورد") for r_ in SA.FLAG_RULES]
        rules += [("A6", "کد تخفیف تکراری در شیفت", "فوری", "مدیر شیفت، حراست، مدیر پارکینگ"), ("A7", "انبوه خوانش ANPR نویزی در یک گیت", "مهم", "مدیر شیفت"),
                  ("A8", "خودروی بیش از ۴۸ ساعت", "پایش", "داشبورد"), ("A9", "ورود باز تکراری (کارت/پلاک)", "مهم", "مدیر شیفت"),
                  ("A10", "پروتکل Z-Score (نقد و خروج رایگان > ۲.۵)", "فوری", "مدیر شیفت، حراست، مدیر پارکینگ")]
        with st.container(border=True):
            head("قوانین هشدار")
            st.dataframe(pd.DataFrame(rules, columns=["کد", "قانون", "شدت", "گیرنده"]), hide_index=True, use_container_width=True, height=R(1, 20))
    with T[3]:
        s1, s2 = st.columns(2)
        with s1.container(border=True):
            head("اجرای دوره‌ای روی سرور", "هر ۵ دقیقه؛ اتصال از .streamlit/secrets.toml")
            st.code("*/5 * * * * cd /path/to/app && python shift_alerts.py --watch --interval 300 --send", language="bash")
        with s2.container(border=True):
            head("تنظیم پیامک در secrets")
            st.code('[sms]\nprovider = "kavenegar"   # یا smsir\napi_key = "..."\nsender = "..."\n\n[sms.recipients]\nshift_manager = ["0912xxxxxxx"]\nsecurity = ["0935xxxxxxx"]\nsite_manager = ["0912xxxxxxx"]', language="toml")


# ============================================================ ثبت داشبوردها و صفحه‌ی اصلی
def _icon(paths, color):
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='{color}' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'>{paths}</svg>")
    return f'url("data:image/svg+xml,{quote(svg)}")'


DASH = [
    dict(k="mgmt", t="مدیریتی", sub="مدیرعامل و مدیریت ارشد", ac=YEL, fn=page1,
         icon="<path d='M4 20V10M10 20V4M16 20v-7M22 20H2'/>"),
    dict(k="audit", t="حراست و ممیزی", sub="ریشه‌یابی ناهنجاری و تخلف", ac=MINT, fn=page2,
         icon="<path d='M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z'/><path d='M8.5 12l2.5 2.5L15.5 9.5'/>"),
    dict(k="ops", t="عملیات و اپراتور", sub="مدیر شیفت و مدیر پارکینگ", ac=TEAL, fn=page3,
         icon="<circle cx='9' cy='8' r='3'/><path d='M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6'/><circle cx='17' cy='9' r='2.2'/><path d='M17 14c2.5 0 4 1.8 4 4'/>"),
    dict(k="tech", t="فنی و تجهیزات", sub="ANPR، راهبند و ممیزی سیستم", ac=CORAL, fn=page_tech,
         icon="<rect x='3' y='7' width='18' height='12' rx='2'/><circle cx='12' cy='13' r='3.2'/><path d='M8 7l1.5-3h5L16 7'/>"),
    dict(k="fin", t="مالی و حسابداری", sub="کارتخوان، تخفیف و درآمد", ac=GRN, fn=page4,
         icon="<rect x='3' y='6' width='18' height='13' rx='2'/><path d='M3 10h18'/><circle cx='16.5' cy='14.5' r='1.3'/>"),
    dict(k="alert", t="هشدار لحظه‌ای شیفت", sub="هشدار و پیامک به مسئولان", ac=YEL, fn=page5,
         icon="<path d='M6 16V11a6 6 0 1112 0v5l2 2H4z'/><path d='M10 21a2 2 0 004 0'/>"),
]
KEYS = [d["k"] for d in DASH]


def home():
    ex = TX0[TX0.Exited]
    rev, loss = float(ex.FinalPrice.sum()), float(ex.Loss.sum())
    flagged = float((ex.NFlags > 0).mean()) if len(ex) else 0.0
    cash, pos = ex.Cash.sum(), ex.Pos.sum()
    cs = cash / (cash + pos) if (cash + pos) else 0
    st.markdown('<div class="hometitle">سنجمان · پایش و ممیزی پارکینگ</div><div class="homesub">برای ورود، داشبورد مخصوص بخش خود را انتخاب کنید</div>', unsafe_allow_html=True)
    c = st.columns(2)
    kpi(c[0], "درآمد ثبت‌شده", mh(rev), f"نقد {cs * 100:.0f}٪ · کارتخوان {(1 - cs) * 100:.0f}٪ · {len(ex):,} خروج", "ok", True, YEL)
    kpi(c[1], "زیان مشکوک", mh(loss), f"{flagged * 100:.1f}٪ ترددها پرچم‌دار", "bad" if loss else "ok", True, CORAL)
    th = max(130, (VH - 400) // 2)
    css = []
    for d in DASH:
        s = f".st-key-tile_{d['k']} button"
        css.append(f"{s}{{height:{th}px;flex-direction:column;gap:4px;background:linear-gradient(135deg,{SLATE},{SURF})!important;border:2px solid {d['ac']}66!important;border-radius:26px!important;transition:.15s}}"
                   f"{s}:hover{{border-color:{d['ac']}!important;transform:translateY(-3px)}}"
                   f"{s}::before{{content:'';width:{min(72, th // 2)}px;height:{min(72, th // 2)}px;background:{_icon(d['icon'], d['ac'])} center/contain no-repeat}}"
                   f"{s} p{{font-size:1.4rem!important;font-weight:800!important;color:{TXT}!important}}"
                   f"{s}::after{{content:'{d['sub']}';color:{SUB};font-size:.9rem}}")
    st.markdown(f"<style>{''.join(css)}</style>", unsafe_allow_html=True)
    for row in (DASH[:3], DASH[3:]):
        for col, d in zip(st.columns(3), row):
            col.button(d["t"], key=f"tile_{d['k']}", on_click=go_to, args=(d["k"],), use_container_width=True)


_cur = st.session_state.get("dash")
CUR = next((d for d in DASH if d["k"] == _cur), None)
if CUR and CUR["k"] != "alert":
    with st.sidebar:
        st.markdown("#### فیلتر داشبورد")
        g_shift = st.radio("شیفت", ["همه شیفت‌ها", "صبح", "عصر", "شب"], horizontal=True, key="g_shift")
        gates = VW0.dropna(subset=["OutputGate"]).drop_duplicates("OutputGateID")[["OutputGateID", "OutputGate"]].sort_values("OutputGate")
        g_gate = st.selectbox("گیت خروج", ["همه گیت‌ها"] + list(gates.OutputGate), key="g_gate", help="با انتخاب هر گیت، نمودارهای ترافیک و پرداخت همان گیت نمایش داده می‌شود")
    if g_shift != "همه شیفت‌ها":
        TX, VW = TX[TX.Shift == g_shift], VW[VW.Shift == g_shift]
    if g_gate != "همه گیت‌ها":
        gid = gates.loc[gates.OutputGate == g_gate, "OutputGateID"].iloc[0]
        TX, VW = TX[TX.OutputGateID == gid], VW[VW.OutputGate == g_gate]

if CUR is None:
    home()
else:
    CUR["fn"]()
