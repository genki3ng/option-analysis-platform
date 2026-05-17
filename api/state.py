"""
Option Analysis Platform — Vercel serverless function
POST 接受 { positions: [...], state: {} } → 返回完整计算结果

无任何持久化：所有用户数据放浏览器 localStorage
"""

from http.server import BaseHTTPRequestHandler
import json
import math
import time
import traceback
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Tuple

RISK_FREE = 0.045

# ── i18n: translation tables for server-rendered strings ───────────
# Keyed by simplified Chinese (source). For static labels, value is plain text.
# For templates with placeholders ({key}), use .format(**vars) at call site.
TRANS_EN = {
    # Morning brief
    "📊 今日市场:": "📊 Today:",
    "🟢 持仓累计浮盈亏": "🟢 Portfolio P&L",
    "🔴 持仓累计浮盈亏": "🔴 Portfolio P&L",
    "已实现": "Realized",
    "财报剩": "earnings in",
    "天": "d",
    "天到期": "d to expiry",
    "到期跨越 — 留意 IV crush": "expires across earnings — watch IV crush",
    "已实现 {pct}% 权利金": "already at {pct}% of premium",
    "可考虑平仓锁利": "consider closing to lock in profit",
    "剩 {days} 天到期 · {note}": "{days}d to expiry · {note}",
    "已 ITM，关注指派风险": "Now ITM — watch assignment risk",
    "OTM 距 {pct}%": "OTM by {pct}%",
    "距行权仅 {pct}%，gamma 风险大": "Only {pct}% from strike — high gamma risk",
    # Suggestion status
    "🟢 持仓健康": "🟢 Healthy",
    "🚨 Call 已 ITM": "🚨 Call is ITM",
    "🚨 Put 已 ITM": "🚨 Put is ITM",
    "🚨 接近行权（ATM）": "🚨 Near strike (ATM)",
    "⚠️ 距行权较近": "⚠️ Approaching strike",
    "🎯 强烈建议平仓": "🎯 Strongly recommend closing",
    "✅ 可考虑平仓": "✅ Consider closing",
    "🟢 组合健康": "🟢 Portfolio healthy",
    # Card labels
    "组合总览": "Portfolio Overview",
    "{n} 持仓 · 实时聚合": "{n} positions · live aggregation",
    "🚨 {n} 个需评估": "🚨 {n} need review",
    "🎯 {n} 个建议平仓": "🎯 {n} suggested to close",
    "集中度": "Concentration",
    "{tk} 占 {pct}%": "{tk} = {pct}%",
    "{n} 个空头持仓，总浮盈 ${pnl} ({pct}%)": "{n} short positions, total P&L ${pnl} ({pct}%)",
    "每日 Theta": "Daily Theta",
    "已收权利金": "Premium collected",
    "📐 组合 Delta 等价 {d} 股（{bias}-biased）": "📐 Portfolio Delta ≈ {d} shares ({bias}-biased)",
    "🏘 集中度：{tk} 占 {pct}%（共 {n} 个标的）": "🏘 Concentration: {tk} = {pct}% (across {n} tickers)",
    "⚠️ {n} 个持仓在财报之后到期（IV crush 风险）": "⚠️ {n} positions expire after earnings (IV-crush risk)",
    "🚨 {n} 个持仓接近/超行权价": "🚨 {n} positions near/past strike",
    "🎯 {n} 个持仓达到 80% 利润": "🎯 {n} positions at 80% profit",
    "⏱️ {n} 个持仓 3 天内到期": "⏱️ {n} positions expire within 3 days",
    # Position advice
    "Exp {exp} · {n} 张 · 剩 {d} 天": "Exp {exp} · {n} contracts · {d}d left",
    "OTM 安全区": "OTM safe zone",
    "ITM 风险区": "ITM danger zone",
    "{tk} 现价 ${px}，行权价 ${k}（距 {money}%，{label}）":
      "{tk} at ${px}, strike ${k} ({money}%, {label})",
    "剩余 {days} 天到期，{n} 张合约": "{days}d to expiry, {n} contracts",
    "现在买回需 ${bb}，浮盈亏 ${pnl} ({pct}%)": "Buyback cost ${bb}, P&L ${pnl} ({pct}%)",
    "⚡ 标的 > 行权价，到期需交付 {n} 股": "⚡ Stock > strike, must deliver {n} shares at expiry",
    "⚡ 到期被指派需 ${cash} 接 {n} 股": "⚡ Assignment requires ${cash} to buy {n} shares",
    "立即买回（${bb}，{verb} ${amt}）": "Buy back now (${bb}, {verb} ${amt})",
    "锁利": "lock in",
    "止损": "stop loss",
    "💰 已实现 {pct}% 权利金（${pnl}）": "💰 Already at {pct}% of premium (${pnl})",
    "立即买回 ${px}/股 锁利 ${pnl}": "Buy back at ${px}/sh, lock in ${pnl}",
    "买回 ${px}/股 锁利 ${pnl}": "Buy back at ${px}/sh, lock in ${pnl}",
    "📉 浮亏 ${amt}（>50% 权利金）": "📉 Unrealized loss ${amt} (>50% of premium)",
    "📉 浮亏 ${amt}": "📉 Unrealized loss ${amt}",
    "⏱️ 仅 {days} 天到期，gamma 风险大": "⏱️ Only {days}d left — high gamma risk",
    "⚠️ {date} 财报（剩 {n} 天）在你到期前，财报前 IV 通常飙升、后 IV crush；卖 put 同时承担方向 + IV 风险":
      "⚠️ {date} earnings ({n}d away) before your expiry. IV spikes pre-earnings then crushes post; short put = both directional + IV risk",
    "⚠️ {date} 财报（剩 {n} 天）在你到期前，注意 IV crush + gamma 风险":
      "⚠️ {date} earnings ({n}d away) before your expiry — watch IV crush + gamma",
    "财报前 1-2 天考虑平仓，避免 IV crush": "Close 1-2 days before earnings to avoid IV crush",
    "继续持有让 Theta 累积收益": "Hold to let Theta accumulate",
    "继续持有等时间衰减": "Hold and wait for time decay",
    # Concentration card
    "🚨 集中度过高 · {tk} 占 {pct}%": "🚨 Concentration too high · {tk} = {pct}%",
    "⚠️ 集中度偏高 · {tk} 占 {pct}%": "⚠️ Concentration high · {tk} = {pct}%",
    "💡 集中度提醒 · {tk} 占 {pct}%": "💡 Concentration notice · {tk} = {pct}%",
    "集中度 · {tk}": "Concentration · {tk}",
    "{pct}% / 共 {n} 标的": "{pct}% / {n} tickers",
    "几乎全部押在一个标的上。这个 ticker 单日大跌 10% 你可能就被全员指派。":
      "Nearly all exposure on one ticker. A 10% single-day drop could trigger assignment across the board.",
    "超过六成暴露在一个标的。考虑下次推荐时换个 ticker，分散一下房产。":
      "Over 60% exposure to one ticker. Consider rotating tickers next time to spread the risk.",
    "过半暴露在单一标的。包租公经验：3-5 个标的左右更稳。":
      "Over half on one ticker. Landlord's rule of thumb: 3-5 tickers is steadier.",
    "当前 {tk} 抵押暴露 ${exp}": "{tk} collateral exposure ${exp}",
    "组合总抵押暴露 ${exp}": "Total collateral exposure ${exp}",
    "💡 一只标的大跌、IV 飙升、财报暴雷 — 全靠它一个，没有缓冲。":
      "💡 If that ticker tanks, IV spikes, or earnings blow up — there's no cushion.",
}

TRANS_TW = {
    "📊 今日市场:": "📊 今日市場:",
    "🟢 持仓累计浮盈亏": "🟢 持倉累計浮盈虧",
    "🔴 持仓累计浮盈亏": "🔴 持倉累計浮盈虧",
    "已实现": "已實現",
    "财报剩": "財報剩",
    "天": "天",
    "天到期": "天到期",
    "到期跨越 — 留意 IV crush": "到期跨越 — 留意 IV crush",
    "已实现 {pct}% 权利金": "已實現 {pct}% 權利金",
    "可考虑平仓锁利": "可考慮平倉鎖利",
    "剩 {days} 天到期 · {note}": "剩 {days} 天到期 · {note}",
    "已 ITM，关注指派风险": "已 ITM，關注指派風險",
    "OTM 距 {pct}%": "OTM 距 {pct}%",
    "距行权仅 {pct}%，gamma 风险大": "距行權僅 {pct}%，gamma 風險大",
    "🟢 持仓健康": "🟢 持倉健康",
    "🚨 Call 已 ITM": "🚨 Call 已 ITM",
    "🚨 Put 已 ITM": "🚨 Put 已 ITM",
    "🚨 接近行权（ATM）": "🚨 接近行權（ATM）",
    "⚠️ 距行权较近": "⚠️ 距行權較近",
    "🎯 强烈建议平仓": "🎯 強烈建議平倉",
    "✅ 可考虑平仓": "✅ 可考慮平倉",
    "🟢 组合健康": "🟢 組合健康",
    "组合总览": "組合總覽",
    "{n} 持仓 · 实时聚合": "{n} 持倉 · 即時聚合",
    "🚨 {n} 个需评估": "🚨 {n} 個需評估",
    "🎯 {n} 个建议平仓": "🎯 {n} 個建議平倉",
    "集中度": "集中度",
    "{tk} 占 {pct}%": "{tk} 佔 {pct}%",
    "{n} 个空头持仓，总浮盈 ${pnl} ({pct}%)": "{n} 個空頭持倉，總浮盈 ${pnl} ({pct}%)",
    "每日 Theta": "每日 Theta",
    "已收权利金": "已收權利金",
    "📐 组合 Delta 等价 {d} 股（{bias}-biased）": "📐 組合 Delta 等價 {d} 股（{bias}-biased）",
    "🏘 集中度：{tk} 占 {pct}%（共 {n} 个标的）": "🏘 集中度：{tk} 佔 {pct}%（共 {n} 個標的）",
    "⚠️ {n} 个持仓在财报之后到期（IV crush 风险）": "⚠️ {n} 個持倉在財報之後到期（IV crush 風險）",
    "🚨 {n} 个持仓接近/超行权价": "🚨 {n} 個持倉接近/超行權價",
    "🎯 {n} 个持仓达到 80% 利润": "🎯 {n} 個持倉達到 80% 利潤",
    "⏱️ {n} 个持仓 3 天内到期": "⏱️ {n} 個持倉 3 天內到期",
    "Exp {exp} · {n} 张 · 剩 {d} 天": "Exp {exp} · {n} 張 · 剩 {d} 天",
    "OTM 安全区": "OTM 安全區",
    "ITM 风险区": "ITM 風險區",
    "{tk} 现价 ${px}，行权价 ${k}（距 {money}%，{label}）":
      "{tk} 現價 ${px}，行權價 ${k}（距 {money}%，{label}）",
    "剩余 {days} 天到期，{n} 张合约": "剩餘 {days} 天到期，{n} 張合約",
    "现在买回需 ${bb}，浮盈亏 ${pnl} ({pct}%)": "現在買回需 ${bb}，浮盈虧 ${pnl} ({pct}%)",
    "⚡ 标的 > 行权价，到期需交付 {n} 股": "⚡ 標的 > 行權價，到期需交付 {n} 股",
    "⚡ 到期被指派需 ${cash} 接 {n} 股": "⚡ 到期被指派需 ${cash} 接 {n} 股",
    "立即买回（${bb}，{verb} ${amt}）": "立即買回（${bb}，{verb} ${amt}）",
    "锁利": "鎖利",
    "止损": "止損",
    "💰 已实现 {pct}% 权利金（${pnl}）": "💰 已實現 {pct}% 權利金（${pnl}）",
    "立即买回 ${px}/股 锁利 ${pnl}": "立即買回 ${px}/股 鎖利 ${pnl}",
    "买回 ${px}/股 锁利 ${pnl}": "買回 ${px}/股 鎖利 ${pnl}",
    "📉 浮亏 ${amt}（>50% 权利金）": "📉 浮虧 ${amt}（>50% 權利金）",
    "📉 浮亏 ${amt}": "📉 浮虧 ${amt}",
    "⏱️ 仅 {days} 天到期，gamma 风险大": "⏱️ 僅 {days} 天到期，gamma 風險大",
    "⚠️ {date} 财报（剩 {n} 天）在你到期前，财报前 IV 通常飙升、后 IV crush；卖 put 同时承担方向 + IV 风险":
      "⚠️ {date} 財報（剩 {n} 天）在你到期前，財報前 IV 通常飆升、後 IV crush；賣 put 同時承擔方向 + IV 風險",
    "⚠️ {date} 财报（剩 {n} 天）在你到期前，注意 IV crush + gamma 风险":
      "⚠️ {date} 財報（剩 {n} 天）在你到期前，注意 IV crush + gamma 風險",
    "财报前 1-2 天考虑平仓，避免 IV crush": "財報前 1-2 天考慮平倉，避免 IV crush",
    "继续持有让 Theta 累积收益": "繼續持有讓 Theta 累積收益",
    "继续持有等时间衰减": "繼續持有等時間衰減",
    "🚨 集中度过高 · {tk} 占 {pct}%": "🚨 集中度過高 · {tk} 佔 {pct}%",
    "⚠️ 集中度偏高 · {tk} 占 {pct}%": "⚠️ 集中度偏高 · {tk} 佔 {pct}%",
    "💡 集中度提醒 · {tk} 占 {pct}%": "💡 集中度提醒 · {tk} 佔 {pct}%",
    "集中度 · {tk}": "集中度 · {tk}",
    "{pct}% / 共 {n} 标的": "{pct}% / 共 {n} 標的",
    "几乎全部押在一个标的上。这个 ticker 单日大跌 10% 你可能就被全员指派。":
      "幾乎全部押在一個標的上。這個 ticker 單日大跌 10% 你可能就被全員指派。",
    "超过六成暴露在一个标的。考虑下次推荐时换个 ticker，分散一下房产。":
      "超過六成暴露在一個標的。考慮下次推薦時換個 ticker，分散一下房產。",
    "过半暴露在单一标的。包租公经验：3-5 个标的左右更稳。":
      "過半暴露在單一標的。包租公經驗：3-5 個標的左右更穩。",
    "当前 {tk} 抵押暴露 ${exp}": "當前 {tk} 抵押暴露 ${exp}",
    "组合总抵押暴露 ${exp}": "組合總抵押暴露 ${exp}",
    "💡 一只标的大跌、IV 飙升、财报暴雷 — 全靠它一个，没有缓冲。":
      "💡 一只標的大跌、IV 飆升、財報暴雷 — 全靠它一個，沒有緩衝。",
}

def _T(lang: str, key: str, **vars) -> str:
    """Translate + interpolate. Falls back to zh source if missing."""
    if lang == "en":
        s = TRANS_EN.get(key, key)
    elif lang in ("zh_tw", "zh-TW", "zh-tw"):
        s = TRANS_TW.get(key, key)
    else:
        s = key
    if vars:
        try:
            s = s.format(**vars)
        except (KeyError, IndexError):
            pass
    return s

# 财报日历（主要标的；yfinance 拿不到时 fallback）
# 季度财报通常按固定 cycle，这里记下未来 1 年的近似日期
EARNINGS_DATES = {
    "TSLA":  [date(2026, 4, 22), date(2026, 7, 22), date(2026, 10, 21), date(2027, 1, 28)],
    "META":  [date(2026, 4, 30), date(2026, 7, 30), date(2026, 10, 29), date(2027, 1, 29)],
    "AAPL":  [date(2026, 4, 30), date(2026, 7, 31), date(2026, 10, 30), date(2027, 1, 28)],
    "GOOGL": [date(2026, 4, 28), date(2026, 7, 28), date(2026, 10, 27), date(2027, 1, 27)],
    "AMZN":  [date(2026, 5, 1),  date(2026, 7, 31), date(2026, 10, 30), date(2027, 1, 30)],
    "NVDA":  [date(2026, 5, 27), date(2026, 8, 26), date(2026, 11, 25), date(2027, 2, 24)],
    "MSFT":  [date(2026, 4, 29), date(2026, 7, 29), date(2026, 10, 28), date(2027, 1, 27)],
    "SPY":   [],  # ETF 无财报
    "QQQ":   [],
    "IWM":   [],
}


def _next_earnings_date(ticker: str, after: date) -> Optional[date]:
    """返回 ticker 在 after 之后的下一次财报日"""
    if ticker not in EARNINGS_DATES:
        return None
    for d in EARNINGS_DATES[ticker]:
        if d > after:
            return d
    return None


# ── Black-Scholes ─────────────────────────────────────────────────────────────
def _ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def _npdf(x): return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_call(S, K, T, r, sigma):
    if T <= 1e-8 or sigma <= 0:
        return max(S - K, 0.0), float(S > K), 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    price = S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    delta = _ncdf(d1)
    theta = (-(S * _npdf(d1) * sigma) / (2 * math.sqrt(T))
             - r * K * math.exp(-r * T) * _ncdf(d2)) / 365
    vega = S * _npdf(d1) * math.sqrt(T) / 100
    return price, delta, theta, vega


def bs_put(S, K, T, r, sigma):
    if T <= 1e-8 or sigma <= 0:
        return max(K - S, 0.0), -float(S < K), 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    price = K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)
    delta = _ncdf(d1) - 1.0
    theta = (-(S * _npdf(d1) * sigma) / (2 * math.sqrt(T))
             + r * K * math.exp(-r * T) * _ncdf(-d2)) / 365
    vega = S * _npdf(d1) * math.sqrt(T) / 100
    return price, delta, theta, vega


def price_option(S, K, T, r, sigma, is_call):
    return (bs_call if is_call else bs_put)(S, K, T, r, sigma)


def implied_vol(target, S, K, T, r, is_call):
    if T <= 0 or target <= 0:
        return 0.4
    lo, hi = 0.01, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        p = price_option(S, K, T, r, mid, is_call)[0]
        if p < target: lo = mid
        else: hi = mid
        if hi - lo < 1e-6: break
    return (lo + hi) / 2


# ── 市场数据 (yfinance) ────────────────────────────────────────────────────────
# Vercel 单次调用内 cache（跨调用不持久，不依赖）
_cache_prices: Dict[str, Dict] = {}
_cache_chain: Dict[Tuple[str, str], Dict] = {}
_cache_hist: Dict[Tuple[str, str], Dict[str, float]] = {}
_cache_intraday: Dict[str, List] = {}
_cache_intraday_ts: Dict[str, float] = {}


def fetch_prices(tickers: List[str]) -> Dict[str, Dict]:
    """实时价 + 前收盘"""
    out = {}
    try:
        import yfinance as yf
        session = _get_yf_session()
        for tk in set(tickers):
            if tk in _cache_prices:
                out[tk] = _cache_prices[tk]
                continue
            try:
                ticker_obj = yf.Ticker(tk, session=session) if session else yf.Ticker(tk)
                fi = ticker_obj.fast_info
                out[tk] = {
                    "price": float(fi.last_price),
                    "prev": float(fi.previous_close),
                }
                _cache_prices[tk] = out[tk]
            except Exception:
                out[tk] = {"price": 0.0, "prev": 0.0}
    except ImportError:
        for tk in set(tickers):
            out[tk] = {"price": 0.0, "prev": 0.0}
    return out


# ── Schwab API (primary data source) ───────────────────────────────
# 用 refresh_token 换 access_token（access 缓存 25 分钟，refresh 7 天有效）
import os
SCHWAB_CLIENT_ID = os.environ.get("SCHWAB_CLIENT_ID", "")
SCHWAB_CLIENT_SECRET = os.environ.get("SCHWAB_CLIENT_SECRET", "")
SCHWAB_REFRESH_TOKEN = os.environ.get("SCHWAB_REFRESH_TOKEN", "")
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_API_BASE = "https://api.schwabapi.com"

_schwab_access_token: Optional[str] = None
_schwab_token_expires_at: float = 0


_schwab_last_err: Optional[str] = None

def _schwab_get_access_token() -> Optional[str]:
    """换 access_token，缓存 25 分钟。失败返回 None。"""
    global _schwab_access_token, _schwab_token_expires_at, _schwab_last_err
    import time as _t
    if _schwab_access_token and _t.time() < _schwab_token_expires_at:
        return _schwab_access_token
    if not SCHWAB_CLIENT_ID:
        _schwab_last_err = "missing SCHWAB_CLIENT_ID env"; return None
    if not SCHWAB_CLIENT_SECRET:
        _schwab_last_err = "missing SCHWAB_CLIENT_SECRET env"; return None
    if not SCHWAB_REFRESH_TOKEN:
        _schwab_last_err = "missing SCHWAB_REFRESH_TOKEN env"; return None

    import base64
    auth = base64.b64encode(f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": SCHWAB_REFRESH_TOKEN,
    }).encode()
    req = urllib.request.Request(
        SCHWAB_TOKEN_URL, data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        _schwab_access_token = d.get("access_token")
        _schwab_token_expires_at = _t.time() + 25 * 60
        _schwab_last_err = None
        return _schwab_access_token
    except urllib.error.HTTPError as e:
        _schwab_last_err = f"token HTTP {e.code}: {e.read().decode()[:200]}"
        return None
    except Exception as e:
        _schwab_last_err = f"token exception: {type(e).__name__}: {e}"
        return None


def fetch_chain_schwab(ticker: str, expiry_str: str) -> Dict:
    """
    用 Schwab Market Data API 拉 option chain，按 expiry 过滤。
    返回 {(strike, 'call'|'put'): {...}} 或 {} 失败。
    """
    global _schwab_last_err
    tok = _schwab_get_access_token()
    if not tok:
        return {}
    url = (
        f"{SCHWAB_API_BASE}/marketdata/v1/chains"
        f"?symbol={ticker}"
        f"&fromDate={expiry_str}&toDate={expiry_str}"
        f"&includeUnderlyingQuote=false"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
        })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        _schwab_last_err = f"chain {ticker} {expiry_str} HTTP {e.code}: {e.read().decode()[:200]}"
        return {}
    except Exception as e:
        _schwab_last_err = f"chain {ticker} {expiry_str}: {type(e).__name__}: {e}"
        return {}

    if data.get("status") != "SUCCESS":
        return {}

    out: Dict = {}
    # Schwab returns callExpDateMap / putExpDateMap, keyed by "YYYY-MM-DD:DTE"
    for type_, mapkey in (("call", "callExpDateMap"), ("put", "putExpDateMap")):
        exp_map = data.get(mapkey) or {}
        for exp_key, strikes_dict in exp_map.items():
            # exp_key format: "2026-05-22:7" — only date prefix matters
            if not exp_key.startswith(expiry_str):
                continue
            for strike_str, contracts in strikes_dict.items():
                if not contracts:
                    continue
                c = contracts[0]  # array of len 1 typically
                try:
                    strike = float(strike_str)
                    bid = float(c.get("bid", 0) or 0)
                    ask = float(c.get("ask", 0) or 0)
                    last = float(c.get("last", 0) or 0)
                    mark = float(c.get("mark", 0) or 0)
                    mid = mark if mark > 0 else ((bid + ask) / 2 if bid > 0 and ask > 0 else last)
                    iv = float(c.get("volatility", 0) or 0)
                    if iv > 5:   # Schwab returns IV as percent
                        iv = iv / 100
                    vol = int(c.get("totalVolume", 0) or 0)
                    oi = int(c.get("openInterest", 0) or 0)
                    out[(strike, type_)] = {
                        "bid": bid, "ask": ask, "mid": mid, "last": last, "iv": iv,
                        "volume": vol, "oi": oi,
                    }
                except Exception:
                    continue
    return out


# ── yfinance + curl_cffi UA 伪装 ─────────────────────────────────
# yfinance 默认用 requests 库，Yahoo 能识别出来限流。
# curl_cffi 能伪装 Chrome 的 TLS fingerprint + HTTP/2 frames，绕开识别。
_yf_session = None  # 延迟初始化，复用整个 function 实例

def _get_yf_session():
    """返回 Chrome-impersonated curl_cffi session，失败则返回 None（让 yf 用默认）"""
    global _yf_session
    if _yf_session is False:
        return None
    if _yf_session is not None:
        return _yf_session
    try:
        from curl_cffi import requests as cffi_requests
        _yf_session = cffi_requests.Session(impersonate="chrome")
        return _yf_session
    except Exception:
        _yf_session = False
        return None


def _fetch_chain_direct(ticker: str, expiry_str: str) -> Dict:
    """
    直接调 Yahoo 的 options JSON endpoint，用 curl_cffi 伪装 Chrome。
    完全绕开 yfinance 的内部 session，避免被它 reset 成 requests。

    策略：query1 → query2 双 host 尝试，附 Chrome 标准 headers + consent cookie
    """
    session = _get_yf_session()
    if not session:
        return {}

    # Yahoo 接受 unix timestamp（午夜 UTC）
    try:
        d = date.fromisoformat(expiry_str)
        ts = int(datetime(d.year, d.month, d.day).timestamp())
    except Exception:
        return {}

    # Yahoo Finance 经常要求 consent cookie；先注入一份避开 GDPR 重定向
    cookies = {
        "EuConsent": "CPwH3IAPwH3IAAOACBENC1CgAP_AAAAAAAYgIwBd_X_fb39j-_5_f_t0eY1P9_7__-0zjhfdt-8N3f_X_L8X42M7vF36pq4KuR4Eu3LBIQdlHOHcTUmw6okVrTPsbk2Mr7NKJ7PEinMbe2dYGH9_n93TuZKY7_____z_v-v_v____f_7-3f3__5_3---_e_V_99zfn9_____9nP___9v-_9______3_79_-AYgIwBd_X_fb39j-_5_f_t0eY1P9_7__-0zjhfdt-8N3f_X_L8X42M7vF36pq4KuR4Eu3LBIQdlHOHcTUmw6okVrTPsbk2Mr7NKJ7PEinMbe2dYGH9_n93TuZKY7_____z_v-v_v____f_7-3f3__5_3---_e_V_99zfn9_____9nP___9v-_9______3_79_-A",
        "GUC": "AQEABAEAAAAAAA",
        "A1S": "d=AQABBJ4AAAAAAA",
    }
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://finance.yahoo.com/",
        "Origin": "https://finance.yahoo.com",
    }

    data = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        url = f"https://{host}/v7/finance/options/{ticker}?date={ts}"
        try:
            r = session.get(url, timeout=8, headers=headers, cookies=cookies)
            if r.status_code == 200:
                d_json = r.json()
                if d_json.get("optionChain", {}).get("result"):
                    data = d_json
                    break
        except Exception:
            continue

    if data is None:
        return {}

    try:
        result = data.get("optionChain", {}).get("result", [])
        if not result:
            return {}
        options_arr = result[0].get("options", [])
        if not options_arr:
            return {}
        opt = options_arr[0]
    except Exception:
        return {}

    out: Dict = {}
    for type_, key in (("call", "calls"), ("put", "puts")):
        for c in opt.get(key, []):
            try:
                strike = float(c.get("strike", 0))
                if strike <= 0:
                    continue
                bid = float(c.get("bid", 0) or 0)
                ask = float(c.get("ask", 0) or 0)
                last = float(c.get("lastPrice", 0) or 0)
                mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
                iv = float(c.get("impliedVolatility", 0) or 0)
                vol = int(c.get("volume", 0) or 0)
                oi = int(c.get("openInterest", 0) or 0)
                out[(strike, type_)] = {
                    "bid": bid, "ask": ask, "mid": mid, "last": last, "iv": iv,
                    "volume": vol, "oi": oi,
                }
            except Exception:
                continue
    return out


_cache_chain_ts: Dict[tuple, float] = {}   # chain 缓存时间戳
CHAIN_CACHE_TTL = 30 * 60   # 30 分钟内成功的 chain 直接复用，避开 Yahoo 限流抖动

def fetch_chain(ticker: str, expiry_str: str) -> Dict:
    """
    {(strike, 'call'|'put'): {bid, ask, mid, last, iv, volume, oi}}

    主路径：Schwab Market Data API（实时、稳定，需要 OAuth refresh token）
    备用 1：Yahoo direct JSON + curl_cffi（被限流是常态）
    备用 2：yfinance
    - 30 分钟 TTL：成功拿到的 chain 反复用
    - 仅缓存非空结果
    """
    import time as _t
    key = (ticker, expiry_str)
    cached = _cache_chain.get(key)
    cached_ts = _cache_chain_ts.get(key, 0)
    if cached and (_t.time() - cached_ts) < CHAIN_CACHE_TTL:
        return cached

    # ── 1. Schwab API（实时、稳定）
    out = fetch_chain_schwab(ticker, expiry_str)
    if out:
        for v in out.values():
            v["source"] = "schwab"
        _cache_chain[key] = out
        _cache_chain_ts[key] = _t.time()
        return out

    # ── 2. Yahoo direct + curl_cffi
    for attempt in range(2):
        out = _fetch_chain_direct(ticker, expiry_str)
        if out:
            for v in out.values():
                v["source"] = "yahoo"
            _cache_chain[key] = out
            _cache_chain_ts[key] = _t.time()
            return out
        if attempt == 0:
            _t.sleep(1.0)

    # ── 2. yfinance 兜底（curl_cffi session 偶尔会被它绕开但万一有用）
    import yfinance as yf
    session = _get_yf_session()
    try:
        t = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        if expiry_str not in t.options:
            return {}
        chain = t.option_chain(expiry_str)
        out = {}
        for df, type_ in ((chain.calls, "call"), (chain.puts, "put")):
            for _, row in df.iterrows():
                bid = float(row.get("bid", 0) or 0)
                ask = float(row.get("ask", 0) or 0)
                last = float(row.get("lastPrice", 0) or 0)
                mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
                iv = float(row.get("impliedVolatility", 0) or 0)
                volume = int(row.get("volume", 0) or 0)
                oi = int(row.get("openInterest", 0) or 0)
                out[(float(row["strike"]), type_)] = {
                    "bid": bid, "ask": ask, "mid": mid, "last": last, "iv": iv,
                    "volume": volume, "oi": oi, "source": "yfinance",
                }
        if out:
            _cache_chain[key] = out
            _cache_chain_ts[key] = _t.time()
            return out
    except Exception:
        pass

    return {}


def fetch_option_quote(ticker, expiry, strike, is_call):
    expiry_str = expiry.isoformat() if hasattr(expiry, "isoformat") else str(expiry)
    chain = fetch_chain(ticker, expiry_str)
    q = chain.get((float(strike), "call" if is_call else "put"))
    if q and q.get("mid", 0) > 0:
        return q
    return None


def fetch_intraday(ticker: str) -> List[Dict]:
    """今日分钟级走势。返回 [{t: 'HH:MM', p: price}, ...]"""
    now = time.time()
    if ticker in _cache_intraday and now - _cache_intraday_ts.get(ticker, 0) < 60:
        return _cache_intraday[ticker]
    try:
        import yfinance as yf
        session = _get_yf_session()
        t = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        hist = t.history(period="1d", interval="5m", prepost=False)
        out = []
        for idx, row in hist.iterrows():
            close = float(row.get("Close", 0) or 0)
            if close > 0:
                out.append({"t": idx.strftime("%H:%M"), "p": close})
        _cache_intraday[ticker] = out
        _cache_intraday_ts[ticker] = now
        return out
    except Exception:
        _cache_intraday[ticker] = []
        _cache_intraday_ts[ticker] = now
        return []


def fetch_history(ticker: str, start: date) -> Dict[str, float]:
    key = (ticker, start.isoformat())
    if key in _cache_hist:
        return _cache_hist[key]
    try:
        import yfinance as yf
        session = _get_yf_session()
        ticker_obj = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        df = ticker_obj.history(
            start=start.isoformat(),
            end=(date.today() + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
        out = {idx.date().isoformat(): float(row["Close"])
               for idx, row in df.iterrows()}
        _cache_hist[key] = out
        return out
    except Exception:
        _cache_hist[key] = {}
        return {}


def get_underlying_at(ticker, d, earliest):
    h = fetch_history(ticker, earliest)
    cur = d
    for _ in range(7):
        if cur.isoformat() in h:
            return h[cur.isoformat()]
        cur -= timedelta(days=1)
    return None


# ── 持仓状态计算 ──────────────────────────────────────────────────────────────
def parse_position(d):
    """从前端 JSON 持仓字典构建标准化对象"""
    return {
        "ticker": d["ticker"].upper(),
        "type": d["type"].lower(),
        "strike": float(d["strike"]),
        "expiry": date.fromisoformat(d["expiry"]),
        "contracts": int(d["contracts"]),
        "sell_price": float(d["sell_price"]),
        "trade_date": date.fromisoformat(d["trade_date"]),
    }


def position_id(p):
    return f"{p['ticker']}_{p['type']}_{int(p['strike'])}_{p['expiry'].isoformat()}"


def position_state(p, today, state, prices, earliest):
    """计算一个持仓的当前状态"""
    pid = position_id(p)
    closed_info = state.get(pid, {})
    closed = bool(closed_info.get("closed"))
    close_date = closed_info.get("close_date")
    close_price = closed_info.get("close_price")
    close_reason = closed_info.get("close_reason")

    underlying = prices.get(p["ticker"], {}).get("price", 0.0)
    days = (p["expiry"] - today).days
    T = max(days / 365.0, 1e-8)
    is_call = (p["type"] == "call")
    shares = p["contracts"] * 100
    sold_total = p["sell_price"] * shares
    total_days = (p["expiry"] - p["trade_date"]).days

    # 财报警告
    earnings_date = _next_earnings_date(p["ticker"], today)
    earnings_before_expiry = (
        earnings_date is not None and today < earnings_date < p["expiry"]
    )
    earnings_days_until = (earnings_date - today).days if earnings_date else None

    base = {
        "id": pid,
        "label": f"{p['ticker']} ${p['strike']:.0f} {p['type'].capitalize()}",
        "ticker": p["ticker"],
        "type": p["type"],
        "strike": p["strike"],
        "expiry": p["expiry"].isoformat(),
        "contracts": p["contracts"],
        "sell_price": p["sell_price"],
        "trade_date": p["trade_date"].isoformat(),
        "underlying": underlying,
        "days": days,
        "total_days": total_days,
        "sold": sold_total,
        "closed": closed,
        "close_date": close_date,
        "close_price": close_price,
        "close_reason": close_reason,
        "earnings_date": earnings_date.isoformat() if earnings_date else None,
        "earnings_before_expiry": earnings_before_expiry,
        "earnings_days_until": earnings_days_until,
    }

    if underlying <= 0:
        # 无标的价 → 占位
        base.update({
            "trade_iv": 0.0, "trade_iv_original": 0.0, "mark_src": "no_data",
            "mark": p["sell_price"], "delta": 0.0, "daily_theta": 0.0,
            "mktval": sold_total, "pnl": 0.0, "pnl_pct": 0.0,
            "moneyness": 0.0, "no_data": True,
        })
        return base

    # 反推交易日 IV（仅作显示备用）
    trade_u = get_underlying_at(p["ticker"], p["trade_date"], earliest) or underlying
    trade_T = max((p["expiry"] - p["trade_date"]).days / 365.0, 1e-8)
    trade_iv = implied_vol(p["sell_price"], trade_u, p["strike"], trade_T, RISK_FREE, is_call)

    if closed and close_price is not None:
        mark = close_price
        delta = theta = vega = 0.0
        iv = trade_iv
        mark_src = "closed"
    elif days <= 0:
        mark = max(underlying - p["strike"], 0) if is_call else max(p["strike"] - underlying, 0)
        delta = theta = vega = 0.0
        iv = trade_iv
        mark_src = "expired"
    else:
        quote = fetch_option_quote(p["ticker"], p["expiry"], p["strike"], is_call)
        if quote and quote["mid"] > 0:
            mark = quote["mid"]
            iv = quote["iv"] if quote["iv"] > 0 else trade_iv
            _, delta, theta, vega = price_option(underlying, p["strike"], T, RISK_FREE, iv, is_call)
            mark_src = "market"
        else:
            iv = trade_iv
            mark, delta, theta, vega = price_option(underlying, p["strike"], T, RISK_FREE, iv, is_call)
            mark_src = "model"

    mktval = mark * shares
    pnl = sold_total - mktval
    pnl_pct = pnl / sold_total * 100 if sold_total else 0.0

    base.update({
        "trade_iv": iv * 100,
        "trade_iv_original": trade_iv * 100,
        "mark_src": mark_src,
        "mark": mark,
        "delta": delta,
        "daily_theta": -theta * shares,
        "mktval": mktval,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "moneyness": (p["strike"] / underlying - 1) * 100,
    })
    return base


# ── 历史 P&L ──────────────────────────────────────────────────────────────────
def portfolio_history(positions, state, prices, today):
    if not positions:
        return []
    earliest = min(p["trade_date"] for p in positions)

    # 各持仓的反推 IV
    pos_iv = {}
    for p in positions:
        tu = get_underlying_at(p["ticker"], p["trade_date"], earliest - timedelta(days=5))
        if tu is None: continue
        T = max((p["expiry"] - p["trade_date"]).days / 365.0, 1e-8)
        pos_iv[position_id(p)] = implied_vol(
            p["sell_price"], tu, p["strike"], T, RISK_FREE, p["type"] == "call")

    # 所有交易日
    all_days = set()
    for tk in set(p["ticker"] for p in positions):
        all_days.update(fetch_history(tk, earliest - timedelta(days=5)).keys())
    sorted_days = sorted(all_days)

    series = []
    for d_str in sorted_days:
        d = date.fromisoformat(d_str)
        if d < earliest or d > today: continue

        total_pnl = total_sold = 0.0
        per_pos = {}
        for p in positions:
            if d < p["trade_date"]: continue
            shares = p["contracts"] * 100
            sold = p["sell_price"] * shares
            pid = position_id(p)

            # ── 已平仓：close_date 之后用 realized P&L 锁定（不再用 BS 重估）
            closed_info = state.get(pid, {})
            close_date_str = closed_info.get("close_date")
            close_price = closed_info.get("close_price")
            if (closed_info.get("closed") and close_date_str and close_price is not None):
                try:
                    cd = date.fromisoformat(close_date_str)
                    if d >= cd:
                        # 锁定的实际盈亏，不随股价波动
                        pnl = (p["sell_price"] - float(close_price)) * shares
                        total_pnl += pnl
                        total_sold += sold
                        per_pos[pid] = pnl
                        continue
                except Exception:
                    pass

            # ── 活跃 / 平仓日之前：用 BS 模型计算
            u = get_underlying_at(p["ticker"], d, earliest - timedelta(days=5))
            if u is None: continue
            days_left = (p["expiry"] - d).days
            T = max(days_left / 365.0, 1e-8)
            iv = pos_iv.get(pid, 0.4)

            if days_left <= 0:
                mark = max(u - p["strike"], 0) if p["type"] == "call" else max(p["strike"] - u, 0)
            else:
                mark = price_option(u, p["strike"], T, RISK_FREE, iv, p["type"] == "call")[0]

            mktval = mark * shares
            pnl = sold - mktval
            total_pnl += pnl
            total_sold += sold
            per_pos[pid] = pnl

        series.append({
            "date": d_str, "total_pnl": total_pnl,
            "total_sold": total_sold, "per_pos": per_pos,
        })

    # 今日实时点
    today_str = today.isoformat()
    today_pnl = today_sold = 0.0
    today_per_pos = {}
    for p in positions:
        if today < p["trade_date"]: continue
        shares = p["contracts"] * 100
        sold = p["sell_price"] * shares
        pid = position_id(p)

        # 已平仓 → 锁定 realized P&L
        closed_info = state.get(pid, {})
        close_price = closed_info.get("close_price")
        if closed_info.get("closed") and close_price is not None:
            pnl = (p["sell_price"] - float(close_price)) * shares
            today_pnl += pnl
            today_sold += sold
            today_per_pos[pid] = pnl
            continue

        u = prices.get(p["ticker"], {}).get("price", 0)
        if u <= 0: continue
        days_left = (p["expiry"] - today).days
        T = max(days_left / 365.0, 1e-8)
        iv = pos_iv.get(pid, 0.4)
        if days_left <= 0:
            mark = max(u - p["strike"], 0) if p["type"] == "call" else max(p["strike"] - u, 0)
        else:
            mark = price_option(u, p["strike"], T, RISK_FREE, iv, p["type"] == "call")[0]
        mktval = mark * shares
        pnl = sold - mktval
        today_pnl += pnl
        today_sold += sold
        today_per_pos[pid] = pnl

    if today_per_pos:
        if series and series[-1]["date"] == today_str:
            series[-1] = {"date": today_str, "total_pnl": today_pnl,
                          "total_sold": today_sold, "per_pos": today_per_pos}
        else:
            series.append({"date": today_str, "total_pnl": today_pnl,
                           "total_sold": today_sold, "per_pos": today_per_pos})

    return series


# ── 操作建议（简化版，与本地版一致核心逻辑）────────────────────────────────────
def _max_sev(a, b):
    order = {"good": 0, "info": 1, "warn": 2, "danger": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def position_advice(ps, lang: str = "zh"):
    days = ps["days"]
    if days < 0 or ps["closed"]:
        return None
    is_call = ps["type"] == "call"
    pnl, pnl_pct = ps["pnl"], ps["pnl_pct"]
    money = ps["moneyness"]
    underlying, strike, mark = ps["underlying"], ps["strike"], ps["mark"]
    shares = ps["contracts"] * 100
    buyback_total = mark * shares
    severity = "good"
    status = _T(lang, "🟢 持仓健康")
    facts, actions = [], []

    is_otm = (is_call and money > 0) or ((not is_call) and money < 0)
    money_label = _T(lang, "OTM 安全区") if is_otm else _T(lang, "ITM 风险区")
    facts.append(_T(lang, "{tk} 现价 ${px}，行权价 ${k}（距 {money}%，{label}）",
                    tk=ps['ticker'], px=f"{underlying:.2f}", k=f"{strike:.0f}",
                    money=f"{money:+.1f}", label=money_label))
    facts.append(_T(lang, "剩余 {days} 天到期，{n} 张合约", days=days, n=ps['contracts']))
    facts.append(_T(lang, "现在买回需 ${bb}，浮盈亏 ${pnl} ({pct}%)",
                    bb=f"{buyback_total:,.0f}", pnl=f"{pnl:+,.0f}", pct=f"{pnl_pct:+.1f}"))

    pnl_verb = _T(lang, "锁利") if pnl >= 0 else _T(lang, "止损")
    pnl_amt = abs(pnl)
    buy_back_action = _T(lang, "立即买回（${bb}，{verb} ${amt}）",
                          bb=f"{buyback_total:,.0f}", verb=pnl_verb, amt=f"{pnl_amt:,.0f}")

    if is_call:
        if money < 0:
            severity = _max_sev(severity, "danger")
            status = _T(lang, "🚨 Call 已 ITM")
            facts.append(_T(lang, "⚡ 标的 > 行权价，到期需交付 {n} 股", n=shares))
            actions += [buy_back_action, "Roll up", "Buy protective Call" if lang == "en" else "买保护 Call"]
        elif money < 5:
            severity = _max_sev(severity, "danger")
            status = _T(lang, "🚨 接近行权（ATM）")
            actions += [buy_back_action, "Roll up"]
        elif money < 15:
            severity = _max_sev(severity, "warn")
            status = _T(lang, "⚠️ 距行权较近")
    else:
        cash_need = strike * shares
        if money > 0:
            severity = _max_sev(severity, "danger")
            status = _T(lang, "🚨 Put 已 ITM")
            facts.append(_T(lang, "⚡ 到期被指派需 ${cash} 接 {n} 股",
                            cash=f"{cash_need:,.0f}", n=shares))
            actions += [buy_back_action,
                        "Roll to next month" if lang == "en" else "Roll 到下月",
                        "Accept assignment" if lang == "en" else "接受指派"]
        elif money > -5:
            severity = _max_sev(severity, "danger")
            status = _T(lang, "🚨 接近行权（ATM）")
            actions += [buy_back_action,
                        "Roll to next month" if lang == "en" else "Roll 到下月"]
        elif money > -15:
            severity = _max_sev(severity, "warn")
            status = _T(lang, "⚠️ 距行权较近")

    if pnl_pct >= 80:
        if severity == "good":
            status = _T(lang, "🎯 强烈建议平仓")
        facts.append(_T(lang, "💰 已实现 {pct}% 权利金（${pnl}）",
                        pct=f"{pnl_pct:.0f}", pnl=f"{pnl:,.0f}"))
        ac = _T(lang, "立即买回 ${px}/股 锁利 ${pnl}", px=f"{mark:.2f}", pnl=f"{pnl:,.0f}")
        if ac not in actions: actions.insert(0, ac)
    elif pnl_pct >= 50:
        if severity == "good":
            status = _T(lang, "✅ 可考虑平仓")
            actions.insert(0, _T(lang, "买回 ${px}/股 锁利 ${pnl}",
                                  px=f"{mark:.2f}", pnl=f"{pnl:,.0f}"))

    if pnl_pct < -50:
        severity = _max_sev(severity, "danger")
        facts.append(_T(lang, "📉 浮亏 ${amt}（>50% 权利金）", amt=f"{-pnl:,.0f}"))
    elif pnl_pct < -20:
        severity = _max_sev(severity, "warn")
        facts.append(_T(lang, "📉 浮亏 ${amt}", amt=f"{-pnl:,.0f}"))

    if 0 < days <= 3:
        facts.append(_T(lang, "⏱️ 仅 {days} 天到期，gamma 风险大", days=days))

    # 财报警告
    if ps.get("earnings_before_expiry"):
        ed = ps["earnings_date"]
        eud = ps["earnings_days_until"]
        if eud is not None and eud >= 0:
            severity = _max_sev(severity, "warn")
            if ps["type"] == "put":
                facts.append(_T(lang,
                    "⚠️ {date} 财报（剩 {n} 天）在你到期前，财报前 IV 通常飙升、后 IV crush；卖 put 同时承担方向 + IV 风险",
                    date=ed, n=eud))
            else:
                facts.append(_T(lang,
                    "⚠️ {date} 财报（剩 {n} 天）在你到期前，注意 IV crush + gamma 风险",
                    date=ed, n=eud))
            earn_action = _T(lang, "财报前 1-2 天考虑平仓，避免 IV crush")
            if earn_action not in actions:
                actions.insert(0, earn_action)

    if not actions:
        actions.append(_T(lang, "继续持有让 Theta 累积收益") if pnl_pct >= 0
                       else _T(lang, "继续持有等时间衰减"))

    return {
        "position_id": ps["id"], "label": ps["label"],
        "subtitle": _T(lang, "Exp {exp} · {n} 张 · 剩 {d} 天",
                       exp=ps['expiry'], n=ps['contracts'], d=days),
        "type": severity, "status": status,
        "pnl": pnl, "pnl_pct": pnl_pct,
        "facts": facts, "actions": actions,
    }


def get_suggestions(positions, lang: str = "zh"):
    cards = []
    active = [p for p in positions if not p["closed"] and p["days"] >= 0]
    total_pnl = sum(p["pnl"] for p in active)
    total_sold = sum(p["sold"] for p in active) or 1
    total_pct = total_pnl / total_sold * 100
    total_theta = sum(p["daily_theta"] for p in active)
    n_danger = sum(1 for p in active if (p["type"] == "call" and p["moneyness"] < 5) or (p["type"] == "put" and p["moneyness"] > -5))
    n_tp = sum(1 for p in active if p["pnl_pct"] >= 80)
    n_close = sum(1 for p in active if 0 <= p["days"] <= 3)

    total_delta_shares = sum(p["delta"] * p["contracts"] * 100 for p in active)
    n_earnings = sum(1 for p in active if p.get("earnings_before_expiry"))

    ticker_exposure: Dict[str, float] = {}
    for p in active:
        tkr = p.get("ticker") or "?"
        strike = p.get("strike", 0)
        contracts = p.get("contracts", 1)
        exposure = strike * contracts * 100
        ticker_exposure[tkr] = ticker_exposure.get(tkr, 0) + exposure
    total_exposure = sum(ticker_exposure.values())
    top_ticker, top_concentration = None, 0
    if total_exposure > 0 and ticker_exposure:
        top_ticker, top_exposure = max(ticker_exposure.items(), key=lambda kv: kv[1])
        top_concentration = top_exposure / total_exposure * 100

    port_facts = [
        _T(lang, "{n} 个空头持仓，总浮盈 ${pnl} ({pct}%)",
           n=len(active), pnl=f"{total_pnl:+,.0f}", pct=f"{total_pct:+.1f}"),
        f"{_T(lang, '每日 Theta')} +${total_theta:.0f}",
        f"{_T(lang, '已收权利金')} ${total_sold:,.0f}",
        _T(lang, "📐 组合 Delta 等价 {d} 股（{bias}-biased）",
           d=f"{total_delta_shares:+.0f}", bias='long' if total_delta_shares > 0 else 'short'),
    ]
    if len(ticker_exposure) > 1:
        port_facts.append(_T(lang, "🏘 集中度：{tk} 占 {pct}%（共 {n} 个标的）",
                              tk=top_ticker, pct=f"{top_concentration:.0f}", n=len(ticker_exposure)))
    if n_earnings:
        port_facts.append(_T(lang, "⚠️ {n} 个持仓在财报之后到期（IV crush 风险）", n=n_earnings))
    if n_danger:
        port_facts.append(_T(lang, "🚨 {n} 个持仓接近/超行权价", n=n_danger))
    if n_tp:
        port_facts.append(_T(lang, "🎯 {n} 个持仓达到 80% 利润", n=n_tp))
    if n_close:
        port_facts.append(_T(lang, "⏱️ {n} 个持仓 3 天内到期", n=n_close))

    if n_danger > 0:
        port_sev = "danger"
        port_status = _T(lang, "🚨 {n} 个需评估", n=n_danger)
    elif n_tp > 0:
        port_sev = "good"
        port_status = _T(lang, "🎯 {n} 个建议平仓", n=n_tp)
    else:
        port_sev = "good"
        port_status = _T(lang, "🟢 组合健康")

    cards.append({
        "position_id": None, "label": _T(lang, "组合总览"),
        "subtitle": _T(lang, "{n} 持仓 · 实时聚合", n=len(active)),
        "type": port_sev, "status": port_status,
        "pnl": total_pnl, "pnl_pct": total_pct,
        "facts": port_facts, "actions": [],
    })

    # 集中度警告
    if top_concentration >= 50 and len(ticker_exposure) >= 2:
        if top_concentration >= 75:
            sev = "danger"
            status = _T(lang, "🚨 集中度过高 · {tk} 占 {pct}%", tk=top_ticker, pct=f"{top_concentration:.0f}")
            advice = _T(lang, "几乎全部押在一个标的上。这个 ticker 单日大跌 10% 你可能就被全员指派。")
        elif top_concentration >= 60:
            sev = "warn"
            status = _T(lang, "⚠️ 集中度偏高 · {tk} 占 {pct}%", tk=top_ticker, pct=f"{top_concentration:.0f}")
            advice = _T(lang, "超过六成暴露在一个标的。考虑下次推荐时换个 ticker，分散一下房产。")
        else:
            sev = "caution"
            status = _T(lang, "💡 集中度提醒 · {tk} 占 {pct}%", tk=top_ticker, pct=f"{top_concentration:.0f}")
            advice = _T(lang, "过半暴露在单一标的。包租公经验：3-5 个标的左右更稳。")
        cards.append({
            "position_id": None,
            "label": _T(lang, "集中度 · {tk}", tk=top_ticker),
            "subtitle": _T(lang, "{pct}% / 共 {n} 标的", pct=f"{top_concentration:.0f}", n=len(ticker_exposure)),
            "type": sev, "status": status,
            "pnl": 0, "pnl_pct": 0,
            "facts": [
                advice,
                _T(lang, "当前 {tk} 抵押暴露 ${exp}",
                   tk=top_ticker, exp=f"{ticker_exposure[top_ticker]:,.0f}"),
                _T(lang, "组合总抵押暴露 ${exp}", exp=f"{total_exposure:,.0f}"),
                _T(lang, "💡 一只标的大跌、IV 飙升、财报暴雷 — 全靠它一个，没有缓冲。"),
            ],
            "actions": [],
        })

    for ps in positions:
        adv = position_advice(ps, lang=lang)
        if adv: cards.append(adv)
    return cards


# ── 主计算入口 ────────────────────────────────────────────────────────────────
def compute(payload):
    positions_raw = payload.get("positions", [])
    state = payload.get("state", {})
    lang = payload.get("lang", "zh")

    if not positions_raw:
        return {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "yfinance_available": _check_yf(),
            "tickers": {}, "intraday": {},
            "tsla": {}, "meta": {},  # 向后兼容
            "total_sold": 0, "total_mktval": 0, "total_pnl": 0,
            "total_pnl_pct": 0, "total_theta": 0,
            "positions": [], "suggestions": [], "history": [],
        }

    positions = [parse_position(p) for p in positions_raw]
    tickers = sorted(set(p["ticker"] for p in positions))
    prices = fetch_prices(tickers)
    intraday = {tk: fetch_intraday(tk) for tk in tickers}
    today = date.today()
    earliest = min(p["trade_date"] for p in positions) - timedelta(days=5)

    enriched = [position_state(p, today, state, prices, earliest) for p in positions]
    history = portfolio_history(positions, state, prices, today)
    suggestions = get_suggestions(enriched, lang=lang)

    total_sold = sum(x["sold"] for x in enriched)
    total_mktval = sum(x["mktval"] for x in enriched)
    total_pnl = total_sold - total_mktval
    total_pnl_pct = total_pnl / total_sold * 100 if total_sold else 0
    total_theta = sum(x["daily_theta"] for x in enriched if not x["closed"] and x["days"] >= 0)
    total_realized = sum(
        (x["sell_price"] - x["close_price"]) * x["contracts"] * 100
        for x in enriched
        if x.get("closed") and x.get("close_price") is not None
    )

    morning_brief = _generate_morning_brief(enriched, prices, total_pnl - total_realized, total_realized, lang=lang)

    return {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "yfinance_available": _check_yf(),
        "tickers": prices,
        "intraday": intraday,
        "tsla": prices.get("TSLA", {}),
        "meta": prices.get("META", {}),
        "total_sold": total_sold,
        "total_mktval": total_mktval,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "total_theta": total_theta,
        "positions": enriched,
        "suggestions": suggestions,
        "history": history,
        "morning_brief": morning_brief,
    }


# ── Option 推荐引擎 ───────────────────────────────────────────────────────────
def _decide_strategy(direction: str, intent: str):
    """根据方向 + 意图决定 (是否 Call, 是否做空)"""
    direction = (direction or "bullish").lower()
    intent = (intent or "premium").lower()
    if intent == "csp":              return False, True   # short put 准备接货
    if intent == "covered_call":     return True, True    # short call 减仓
    if intent == "long_vol":
        return (True, False) if direction == "bullish" else (False, False)
    if intent == "long_leaps":
        # LEAPS 股票替代：根据方向决定 long call 或 long put（通常 call）
        return (True, False) if direction != "bearish" else (False, False)
    # 默认 premium：根据方向决定
    if direction == "bullish":       return False, True   # short put
    if direction == "bearish":       return True, True    # short call
    return False, True  # neutral 默认 short put


def _compute_iv_rank(ticker: str, current_iv: float) -> Optional[dict]:
    """用历史 30 天已实现波动率近似 IV rank（粗略但有用）"""
    if current_iv <= 0:
        return None
    try:
        import yfinance as yf
        session = _get_yf_session()
        ticker_obj = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        hist = ticker_obj.history(period="1y", interval="1d", auto_adjust=True)
        closes = hist["Close"].dropna().tolist()
        if len(closes) < 60:
            return None
        # 计算 30 天滚动年化已实现波动率
        rv_series = []
        for i in range(30, len(closes)):
            rets = [math.log(closes[j] / closes[j-1])
                    for j in range(i-29, i+1) if closes[j-1] > 0]
            if len(rets) < 10:
                continue
            mu = sum(rets) / len(rets)
            var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
            rv = math.sqrt(var * 252)
            rv_series.append(rv)
        if not rv_series:
            return None
        rv_low, rv_high = min(rv_series), max(rv_series)
        rv_now = rv_series[-1]
        # IV rank 用当前 IV 在 RV 范围里的位置近似
        iv_rank = max(0, min(100,
            (current_iv - rv_low) / (rv_high - rv_low) * 100 if rv_high > rv_low else 50))
        # IV percentile 用当前 IV 比多少天的 RV 高
        iv_pct = sum(1 for r in rv_series if r < current_iv) / len(rv_series) * 100
        return {
            "current_iv_pct": round(current_iv * 100, 1),
            "rv_30d_now_pct": round(rv_now * 100, 1),
            "rv_52w_low_pct": round(rv_low * 100, 1),
            "rv_52w_high_pct": round(rv_high * 100, 1),
            "iv_rank": round(iv_rank, 0),
            "iv_percentile": round(iv_pct, 0),
        }
    except Exception:
        return None


def _backtest_strategy(ticker: str, days_back: int = 90,
                       sample_dte: int = 7, delta_target: float = 0.25,
                       is_short_put: bool = True) -> Optional[dict]:
    """
    粗略回测：过去 N 天每个交易日卖一笔 sample_dte DTE delta_target Δ 期权，
    模拟最终结果。返回胜率 + 平均收益。
    """
    try:
        import yfinance as yf
        session = _get_yf_session()
        ticker_obj = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        hist = ticker_obj.history(period="6mo", interval="1d", auto_adjust=True)
        closes = hist["Close"].dropna().tolist()
        if len(closes) < 60:
            return None
        # 估算每天的隐含波动率（用 20 天 RV 近似）
        wins, losses = 0, 0
        total_pnl_pct = 0
        for i in range(20, len(closes) - sample_dte, 5):  # 每 5 天采样
            S = closes[i]
            # 20 天 RV
            rets = [math.log(closes[j] / closes[j-1]) for j in range(i-19, i+1)]
            rv = math.sqrt(sum((r - sum(rets)/len(rets))**2 for r in rets) / 19 * 252)
            if rv <= 0 or rv > 3: continue
            # 选 strike 让 Delta ≈ delta_target（粗估）
            # 对于 short put: K = S * exp(-z * sigma * sqrt(T)), z ~ delta_target 反算
            # 简化：K = S * (1 - sigma * sqrt(T) * delta_target * 2)
            T = sample_dte / 365
            offset = rv * math.sqrt(T) * 0.85  # 大约 -0.25 delta
            K = S * (1 - offset) if is_short_put else S * (1 + offset)
            # 模拟到期 stock price
            S_exp = closes[i + sample_dte]
            # P&L: short put 卖 X 收钱，到期如果 S_exp > K 全收，否则赔 (K - S_exp)
            premium_pct = offset * 0.3  # 粗估权利金占股价的百分比
            if is_short_put:
                if S_exp >= K:
                    pnl = premium_pct  # 全收权利金
                    wins += 1
                else:
                    pnl = premium_pct - (K - S_exp) / S
                    losses += 1
            else:  # short call
                if S_exp <= K:
                    pnl = premium_pct
                    wins += 1
                else:
                    pnl = premium_pct - (S_exp - K) / S
                    losses += 1
            total_pnl_pct += pnl
        n = wins + losses
        if n < 5:
            return None
        return {
            "win_rate": round(wins / n * 100, 0),
            "avg_pnl_pct": round(total_pnl_pct / n * 100, 1),
            "n_trades": n,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# 包租公算法 1.0 — Landlord Algorithm 1.0
#
# 设计原则（房东视角）：
#   1. 收稳定的周租 — 不追高赌注，追胜率
#   2. 不闹事的房客 — 安全度优先（N(d2) 真实概率）
#   3. 甜蜜区 DTE   — 7-21 天为佳（周租周期）
#   4. 甜蜜区 Delta — 0.15-0.30 为佳（既能收租又不易被指派）
#   5. 不养事儿精  — 财报跨期对保守派直接否决，对激进派扣分
#   6. 资金效率    — 年化收益 × 安全幂次 × 流动性
#   7. Wheel 友好  — CSP 若 strike 在历史低位，被指派也是好价位
# ─────────────────────────────────────────────────────────────────────
ALGORITHM_NAME = "包租公算法"
ALGORITHM_VERSION = "1.2"
ALGORITHM_TAGLINE = "把股票租出去，每周收稳定的租金"
# v1.1 changes: 流动性因子从单一 spread% 升级为 spread × OI × volume 复合分


def _prob_safe_bs(S: float, K: float, T: float, sigma: float, is_call: bool) -> float:
    """
    用 BS 模型算"到期安全"的真实概率（百分比 0-100）。
    Short call: 安全 = S_T < K, 概率 = N(-d2)
    Short put : 安全 = S_T > K, 概率 = N(d2)
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d2 = (math.log(S / K) + (RISK_FREE - 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    except (ValueError, ZeroDivisionError):
        return 0.0
    # Short call 安全 = 标的低于 strike：P(S_T < K) = N(-d2)
    # Short put  安全 = 标的高于 strike：P(S_T > K) = N(d2)
    return (_ncdf(-d2) if is_call else _ncdf(d2)) * 100


def _dte_sweet_factor(days: int) -> float:
    """
    DTE 甜蜜区加成：14 天为峰值，<5 或 >35 衰减。
    Returns 0.5 ~ 1.2 multiplier.
    """
    if days <= 0:
        return 0.5
    if days < 5:
        return 0.65 + 0.07 * days       # 5→1.0
    if days <= 21:
        # 7-21 天为甜蜜区，14 天最甜
        return 1.0 + 0.2 * max(0, 1 - abs(days - 14) / 7)
    if days <= 35:
        return 1.0 - (days - 21) / 28   # 21→1.0, 35→0.5
    return 0.5


def _delta_sweet_factor(abs_delta: float) -> float:
    """
    Delta 甜蜜区加成：0.22 为峰值。
    < 0.10 收太少；> 0.40 风险大。
    Returns 0.6 ~ 1.15.
    """
    if abs_delta <= 0:
        return 0.6
    if abs_delta < 0.10:
        return 0.6 + abs_delta * 4      # 0.10→1.0
    if abs_delta <= 0.30:
        # 0.10-0.30 甜蜜区，0.22 最甜
        return 1.0 + 0.15 * max(0, 1 - abs(abs_delta - 0.22) / 0.12)
    if abs_delta <= 0.45:
        return 1.0 - (abs_delta - 0.30) / 0.30   # 0.30→1.0, 0.45→0.5
    return 0.5


def _liquidity_factor_v11(spread_pct: float, oi: int, volume: int) -> tuple:
    """
    包租公算法 1.1：复合流动性 = spread × OI × volume modifier
    返回 (score, breakdown)
    Score 范围约 0.25 ~ 1.10。

    单看 spread 不够 —— 一份 spread 看似 5% 但 OI=0 的合约，挂单可能一天不成交。
    """
    # 1. Spread 基础分（继承 1.0）
    spread_score = max(0.4, min(1.0, 1.0 - spread_pct / 40))

    # 2. OI 修正 — 持仓量决定二级市场深度
    if oi >= 1000:   oi_mod = 1.10   # 充裕
    elif oi >= 500:  oi_mod = 1.00
    elif oi >= 200:  oi_mod = 0.95
    elif oi >= 50:   oi_mod = 0.85
    elif oi >= 10:   oi_mod = 0.70
    else:            oi_mod = 0.50   # 几乎无人持有，平仓困难

    # 3. Volume 修正 — 当日交易活跃度
    if volume >= 200: vol_mod = 1.05
    elif volume >= 50: vol_mod = 1.00
    elif volume >= 10: vol_mod = 0.93
    elif volume >= 1:  vol_mod = 0.82
    else:              vol_mod = 0.65  # 当日无成交，价差可能很 stale

    score = spread_score * oi_mod * vol_mod
    return score, {
        "spread_score": round(spread_score, 2),
        "oi_mod": oi_mod,
        "vol_mod": vol_mod,
        "oi": oi,
        "volume": volume,
    }


def _wheel_friendly_factor(strike: float, underlying: float, is_csp: bool) -> tuple:
    """
    Wheel 友好度：对 CSP，strike 相对现价是否在好接货价位？
    Returns (factor, signal_text or None)
    """
    if not is_csp:
        return 1.0, None
    # Strike 相对当前价的折扣
    discount = (underlying - strike) / underlying * 100  # %
    if discount >= 10:
        return 1.10, f"📦 即便被指派，{strike:.0f} 是 -{discount:.0f}% 接货价（划算）"
    if discount >= 5:
        return 1.05, None
    if discount < 2:
        # strike 太接近现价 → 被指派概率大且没便宜
        return 0.92, None
    return 1.0, None


def _summarize_data_source(chain_stats: dict) -> dict:
    """汇总本次推荐用到的数据源：primary = 出现最多的；is_fallback = 不是 schwab。"""
    sources = chain_stats.get("sources") or {}
    primary = "unknown"
    if sources:
        primary = max(sources.items(), key=lambda kv: kv[1])[0]
    return {
        "chains_ok": chain_stats["good_count"],
        "chains_empty": chain_stats["empty_count"],
        "total_chains": chain_stats["total"],
        "sources": sources,
        "primary": primary,
        "is_fallback": primary not in ("schwab", "unknown"),
    }


def _earnings_factor(days_to_earnings: int, risk: str) -> float:
    """财报因子（包租公 1.2）：按距财报天数衰减，替代原 1.1 的 cross 二元否决。

    保守模式下 ≤5 天硬否决（IV crush 风险极高、新手最常踩的坑）；
    其他时段用距离衰减，避免误杀 14+ 天后到期、风险其实可控的合约。
    """
    if risk == "conservative" and days_to_earnings <= 5:
        return 0.0
    if days_to_earnings <= 2:    base = 0.20
    elif days_to_earnings <= 7:  base = 0.50
    elif days_to_earnings <= 14: base = 0.75
    elif days_to_earnings <= 21: base = 0.88
    else:                         base = 0.95
    if risk == "conservative":
        return round(base * 0.80, 2)
    if risk == "aggressive":
        return round(min(1.0, base * 1.15), 2)
    return round(base, 2)


def _landlord_score(opt: dict, is_csp: bool, underlying: float,
                     iv_rank: Optional[dict], backtest: Optional[dict],
                     earnings_cross: bool, earnings_days_until: Optional[int],
                     risk: str) -> dict:
    """
    包租公分（rent_score）— 综合"周租"质量评分。
    返回 {"score": float, "components": {...}}，components 用于解释。
    """
    ay         = max(0, opt["annualized_yield_pct"])   # 年化租金 %
    prob_safe  = max(0, min(100, opt["prob_safe_pct"])) / 100  # 0-1
    spread_pct = opt["spread_pct"]
    days       = opt["days"]
    abs_delta  = abs(opt["delta"])
    oi         = opt.get("oi", 0)
    volume     = opt.get("volume", 0)

    # 1. 基础：年化收益（房租）
    base = ay

    # 2. 安全度幂次 — 安全压倒一切
    safety = prob_safe ** 1.5

    # 3. DTE 甜蜜区
    dte_f = _dte_sweet_factor(days)

    # 4. Delta 甜蜜区
    delta_f = _delta_sweet_factor(abs_delta)

    # 5. IV rank 加成（IV 高 = 多收租）
    iv_f = 1.0
    if iv_rank and "iv_rank" in iv_rank:
        ir = iv_rank["iv_rank"]
        if ir >= 70:   iv_f = 1.20
        elif ir >= 50: iv_f = 1.08
        elif ir <= 20: iv_f = 0.85
        elif ir <= 35: iv_f = 0.93

    # 6. 流动性（包租公 1.1：spread × OI × volume 复合）
    liq_f, liq_breakdown = _liquidity_factor_v11(spread_pct, oi, volume)

    # 7. 财报跨期：1.2 用距财报天数衰减（见 _earnings_factor）
    earnings_f = 1.0
    if earnings_cross and earnings_days_until is not None and earnings_days_until >= 0:
        earnings_f = _earnings_factor(earnings_days_until, risk)

    # 8. 回测胜率加成
    bt_f = 1.0
    if backtest and backtest.get("n_trades", 0) >= 5:
        wr = backtest["win_rate"]
        if wr >= 75: bt_f = 1.12
        elif wr >= 60: bt_f = 1.04
        elif wr < 45: bt_f = 0.85

    score = base * safety * dte_f * delta_f * iv_f * liq_f * earnings_f * bt_f

    return {
        "score": round(score, 2),
        "components": {
            "annualized": round(ay, 1),
            "safety": round(safety, 3),
            "dte_factor": round(dte_f, 2),
            "delta_factor": round(delta_f, 2),
            "iv_factor": round(iv_f, 2),
            "liquidity_factor": round(liq_f, 2),
            "liquidity_breakdown": liq_breakdown,
            "earnings_factor": round(earnings_f, 2),
            "backtest_factor": round(bt_f, 2),
        }
    }


def _make_verdict(opt: dict, is_short: bool, intent: str,
                  iv_rank: Optional[dict],
                  backtest: Optional[dict] = None, risk: str = "balanced",
                  is_csp: bool = False, underlying: float = 0) -> dict:
    """生成一句话推荐 verdict（包租公算法 1.0 — 房东视角，损失厌恶）"""
    pros, cons = [], []
    weight = 0  # 综合权重：正数 = 偏好，负数 = 不偏好

    # ── 包租公专属信号 #1：Wheel 友好（CSP strike 是否好接货价）
    if is_csp and underlying > 0:
        _, wf_signal = _wheel_friendly_factor(opt["strike"], underlying, True)
        if wf_signal:
            pros.append(wf_signal); weight += 2

    # ── 包租公专属信号 #2：DTE 甜蜜区（7-21 天）
    if is_short and opt.get("days"):
        d = opt["days"]
        if 7 <= d <= 21:
            pros.append(f"📅 {d} 天到期，周租甜蜜区"); weight += 1
        elif d < 5:
            cons.append(f"📅 仅 {d} 天，gamma 风险大"); weight -= 2
        elif d > 35:
            cons.append(f"📅 {d} 天太长，钱躺得久"); weight -= 1

    # 流动性（包租公算法 1.1：spread + OI + volume 综合判断）
    if opt["spread_pct"] > 10:
        cons.append(f"买卖价差大 {opt['spread_pct']:.0f}%（成交可能折价）"); weight -= 2
    elif opt["spread_pct"] > 5:
        cons.append(f"买卖价差 {opt['spread_pct']:.0f}%"); weight -= 1
    elif opt["spread_pct"] < 3:
        pros.append("流动性好（spread 小）"); weight += 1

    oi_val = int(opt.get("oi", 0))
    vol_val = int(opt.get("volume", 0))
    if oi_val < 10:
        cons.append(f"OI 仅 {oi_val}（几乎无人持有，平仓困难）"); weight -= 2
    elif oi_val < 50:
        cons.append(f"OI 偏低 {oi_val}（二级市场薄）"); weight -= 1
    elif oi_val >= 1000:
        pros.append(f"OI {oi_val:,}（持仓量充裕，好进好出）"); weight += 1

    if vol_val == 0:
        cons.append("今日 0 成交（价格可能 stale）"); weight -= 1
    elif vol_val >= 200:
        pros.append(f"今日成交 {vol_val:,}（活跃）"); weight += 1

    if is_short:
        ay = opt["annualized_yield_pct"]
        ps = opt["prob_safe_pct"]
        money = opt["moneyness_pct"]

        # 年化收益
        if ay >= 100:
            pros.append(f"年化 {ay:.0f}%（极高收益）"); weight += 3
        elif ay >= 60:
            pros.append(f"年化 {ay:.0f}%（高收益）"); weight += 2
        elif ay >= 30:
            pros.append(f"年化 {ay:.0f}%（不错）"); weight += 1
        elif ay >= 15:
            pass  # 中性
        else:
            cons.append(f"年化只有 {ay:.0f}%（偏低）"); weight -= 1

        # 安全概率
        if ps >= 85:
            pros.append(f"安全概率 {ps:.0f}%（很安全）"); weight += 2
        elif ps >= 70:
            pros.append(f"安全概率 {ps:.0f}%"); weight += 1
        elif ps < 55:
            cons.append(f"安全概率仅 {ps:.0f}%（偏险）"); weight -= 2
        elif ps < 65:
            cons.append(f"安全概率 {ps:.0f}%（一般）"); weight -= 1

        # 距行权 — gamma 风险（严重，扣分多）
        if abs(money) < 2:
            cons.append(f"距行权仅 {abs(money):.1f}%（gamma 风险极大）"); weight -= 3
        elif abs(money) < 4:
            cons.append(f"距行权 {abs(money):.1f}%（gamma 偏高）"); weight -= 2
        elif abs(money) > 10:
            pros.append(f"距行权 {abs(money):.0f}%（远离危险区）"); weight += 1

        # IV 配合度
        if iv_rank:
            ir = iv_rank["iv_rank"]
            if ir >= 70:
                pros.append(f"📈 IV 高（rank {ir:.0f}），卖期权好时机"); weight += 2
            elif ir >= 50:
                pros.append(f"📊 IV 中位（rank {ir:.0f}）"); weight += 0
            elif ir <= 20:
                cons.append(f"📉 IV 很低（rank {ir:.0f}），权利金偏少"); weight -= 2
            elif ir <= 35:
                cons.append(f"📉 IV 低（rank {ir:.0f}）"); weight -= 1

    elif intent == "long_leaps":
        lev = opt.get("leverage_x", 0)
        be = opt.get("breakeven_pct", 0)

        # 杠杆
        if lev >= 3:
            pros.append(f"杠杆 {lev}x（资金效率极高）"); weight += 3
        elif lev >= 2:
            pros.append(f"杠杆 {lev}x"); weight += 2
        elif lev < 1.5:
            cons.append(f"杠杆只 {lev}x（资金效率低）"); weight -= 1

        # 盈亏平衡
        if be is not None:
            if be < 5:
                pros.append(f"盈亏平衡只需涨 {be:.1f}%"); weight += 2
            elif be < 10:
                pros.append(f"盈亏平衡涨 {be:.1f}%"); weight += 1
            elif be > 20:
                cons.append(f"盈亏平衡需涨 {be:.0f}%（偏远）"); weight -= 2
            elif be > 12:
                cons.append(f"盈亏平衡涨 {be:.0f}%"); weight -= 1

        # IV 配合度（买期权希望 IV 低）
        if iv_rank:
            ir = iv_rank["iv_rank"]
            if ir <= 25:
                pros.append(f"📉 IV 很低（rank {ir:.0f}），买期权便宜"); weight += 2
            elif ir <= 40:
                pros.append(f"📊 IV 偏低（rank {ir:.0f}）"); weight += 1
            elif ir >= 70:
                cons.append(f"📈 IV 高（rank {ir:.0f}），买期权偏贵"); weight -= 2

        # 时间
        if opt["days"] >= 180:
            pros.append("时间充裕（theta 衰减慢）"); weight += 1
        elif opt["days"] < 45:
            cons.append("时间偏短，theta 衰减快"); weight -= 2

    else:  # long_vol etc.
        if iv_rank:
            ir = iv_rank["iv_rank"]
            if ir <= 30:
                pros.append("IV 低（买期权便宜）"); weight += 2
            elif ir >= 70:
                cons.append("IV 高（买期权偏贵）"); weight -= 2

    # 回测信号（如果有）
    if backtest and backtest.get("n_trades", 0) >= 5:
        wr = backtest["win_rate"]
        if wr >= 75:
            pros.append(f"📊 类似策略 6 个月回测胜率 {wr:.0f}%（{backtest['n_trades']} 次模拟）"); weight += 2
        elif wr >= 60:
            pros.append(f"📊 类似策略回测胜率 {wr:.0f}%"); weight += 1
        elif wr < 45:
            cons.append(f"📊 类似策略回测胜率仅 {wr:.0f}%，历史上不利"); weight -= 2

    # 财报警告 — 包租公算法 1.0：保守派 = 硬否决，平衡派 = 重扣，激进派 = 轻扣
    earnings_veto = False
    if opt.get("earnings_warning"):
        ed = opt["earnings_warning"]
        if is_short and risk == "conservative":
            cons.append(f"🚫 {ed['date']} 财报跨期（剩 {ed['days']} 天）— 包租公保守派不接此单")
            weight -= 5
            earnings_veto = True
        elif is_short and risk == "balanced":
            cons.append(f"⚠️ {ed['date']} 财报跨期（剩 {ed['days']} 天），IV crush 风险")
            weight -= 3
        else:
            cons.append(f"⚠️ {ed['date']} 财报跨期（剩 {ed['days']} 天）")
            weight -= 2

    # Spread 替代方案（短期高风险时建议）
    if is_short and opt.get("spread_alt"):
        sa = opt["spread_alt"]
        pros.append(f"🛡 可考虑改成 Spread (买 ${sa['protect_strike']:.0f} 保护腿)，最大亏损降到 ${sa['max_loss']:,.0f}")

    # 损失厌恶：cons 数量 ≥ pros 时再扣一分（包租公房东最讨厌"麻烦")
    if len(cons) > len(pros):
        weight -= 1

    # 综合评级（基于加权得分，越大越好）
    if earnings_veto:
        # 财报硬否决：不会超过 2 星
        tier, stars, label, color = (
            (2, "⭐⭐", "谨慎 — 财报跨期", "orange")
            if weight >= -6 else (1, "⭐", "不建议", "red")
        )
    elif weight >= 6:
        tier, stars, label, color = 5, "⭐⭐⭐⭐⭐", "五星房源", "green"
    elif weight >= 3:
        tier, stars, label, color = 4, "⭐⭐⭐⭐", "推荐出租", "green"
    elif weight >= 0:
        tier, stars, label, color = 3, "⭐⭐⭐", "一般房源", "yellow"
    elif weight >= -3:
        tier, stars, label, color = 2, "⭐⭐", "谨慎出租", "orange"
    else:
        tier, stars, label, color = 1, "⭐", "别租", "red"

    # 一句话总结 — 包租公口吻
    if is_short:
        if tier == 5:
            voice = "📦 收稳定的周租，房客很少闹事"
        elif tier == 4:
            voice = "📬 不错的房子，建议出租"
        elif tier == 3:
            voice = "🏚 一般房源，看你心情"
        elif tier == 2:
            voice = "⚠️ 房客有风险，谨慎"
        else:
            voice = "🚫 这房子别租"
    else:
        voice = ""

    if pros and not cons:
        one_line = (voice + " · " if voice else "✅ ") + " · ".join(pros[:2])
    elif pros and cons:
        one_line = (voice + " · " if voice else "⚖️ ") + pros[0] + "，但 " + cons[0]
    elif cons and not pros:
        one_line = (voice + " · " if voice else "⚠️ ") + " · ".join(cons[:2])
    else:
        one_line = voice or "符合筛选条件，但无突出优劣"

    return {
        "tier": tier,
        "weight": weight,
        "stars": stars,
        "label": label,
        "color": color,
        "one_line": one_line,
        "pros": pros,
        "cons": cons,
        "earnings_veto": earnings_veto,
    }


def _find_expiries(ticker: str, target_days: int, n: int = 3):
    """找最接近 target_days 的到期日"""
    try:
        import yfinance as yf
        session = _get_yf_session()
        ticker_obj = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        exps = ticker_obj.options
        today = date.today()
        scored = []
        for e in exps:
            try:
                d = date.fromisoformat(e)
                days = (d - today).days
                if days < 1:
                    continue
                scored.append((abs(days - target_days), e, days))
            except Exception:
                continue
        scored.sort()
        return [e for _, e, _ in scored[:n]]
    except Exception:
        return []


def recommend(req: dict) -> dict:
    """返回排名后的 option 候选清单"""
    ticker = (req.get("ticker") or "").upper().strip()
    lang = req.get("lang", "zh")
    if not ticker:
        return {"error": _T(lang, "请提供 ticker")}
    direction = req.get("direction", "bullish")
    intent = req.get("intent", "premium")
    timeframe = int(req.get("timeframe", 7))
    risk = req.get("risk", "balanced")

    # 拿当前价
    prices = fetch_prices([ticker])
    underlying = prices.get(ticker, {}).get("price", 0.0)
    if underlying <= 0:
        return {"error": f"无法拉到 {ticker} 实时价格"}

    is_call, is_short = _decide_strategy(direction, intent)
    # LEAPS / 股票替代：扫描深度 ITM 区间（Delta 0.55-0.85）
    if intent == "long_leaps":
        delta_band = {
            "conservative": (0.75, 0.90),  # 接近股票
            "balanced":     (0.65, 0.80),  # 平衡杠杆
            "aggressive":   (0.55, 0.72),  # 高杠杆
        }.get(risk, (0.65, 0.80))
    else:
        delta_band = {
            "conservative": (0.08, 0.20),
            "balanced":     (0.20, 0.35),
            "aggressive":   (0.35, 0.50),
        }.get(risk, (0.20, 0.35))

    target_exps = _find_expiries(ticker, timeframe, n=3)
    today = date.today()

    candidates = []
    chain_stats = {"empty_count": 0, "good_count": 0, "total": len(target_exps),
                   "sources": {}}
    for exp_str in target_exps:
        chain = fetch_chain(ticker, exp_str)
        if chain:
            chain_stats["good_count"] += 1
            # 取该 chain 任一条记录的 source（fetch_chain 内每条都标了同源）
            try:
                src = next(iter(chain.values())).get("source", "unknown")
            except StopIteration:
                src = "unknown"
            chain_stats["sources"][src] = chain_stats["sources"].get(src, 0) + 1
        else:
            chain_stats["empty_count"] += 1

        # Bug fix: 深度 ITM 期权 yfinance 经常不返回 IV / bid / ask（数据稀薄）
        # → LEAPS 整个候选清单被切空。Fallback：
        #   IV → chain 同 type 非零 IV 的中位数
        #   Mid → intrinsic value × 1.05 兜底（对 long_leaps 必要）
        same_type_ivs = [q["iv"] for (_, t), q in chain.items()
                         if t == ("call" if is_call else "put") and q["iv"] > 0]
        fallback_iv = (sorted(same_type_ivs)[len(same_type_ivs) // 2]
                       if same_type_ivs else 0.30)

        for (strike, type_), q in chain.items():
            if (type_ == "call") != is_call:
                continue

            days = (date.fromisoformat(exp_str) - today).days
            if days < 1:
                continue
            T = days / 365.0

            # Mid 价：先用真实 bid/ask，缺失时对 LEAPS 用 intrinsic 兜底
            mid = q["mid"]
            if mid <= 0:
                if intent == "long_leaps":
                    intrinsic = max(underlying - strike, 0) if is_call else max(strike - underlying, 0)
                    if intrinsic > 0:
                        mid = intrinsic * 1.03
                    else:
                        continue
                else:
                    continue

            # IV 缺失：用同 chain 中位数兜底
            iv = q["iv"] if q["iv"] > 0 else fallback_iv
            if iv <= 0:
                continue

            _, delta, theta, vega = price_option(
                underlying, strike, T, RISK_FREE, iv, is_call)
            abs_delta = abs(delta)
            if not (delta_band[0] <= abs_delta <= delta_band[1]):
                continue

            if q["bid"] > 0 and q["ask"] > 0:
                spread = q["ask"] - q["bid"]
                spread_pct = spread / mid * 100 if mid else 100
            else:
                spread_pct = 8.0  # 缺真实报价时的保守估计（非交易时段常见）

            shares = 100
            premium = mid * shares
            # 抵押金：CSP 用 strike；Covered Call 假定持有正股，用 strike；裸卖也用 strike
            collateral = strike * shares if is_short else mid * shares
            annualized = 0
            if is_short and collateral > 0 and days > 0:
                annualized = (premium / collateral) * (365 / days) * 100
            # 包租公算法 1.0：真实 BS P(safe expiry)，而不是 1-|delta|
            if is_short:
                prob_safe = _prob_safe_bs(underlying, strike, T, iv, is_call)
            else:
                prob_safe = (1 - abs_delta) * 100

            # 综合评分
            liquidity_factor = max(0.3, 1.0 - spread_pct / 50)
            if is_short:
                # 占位 — 真实 rent_score 在加完 earnings 信息后算（在循环外）
                score = annualized * (prob_safe / 100) * liquidity_factor
            elif intent == "long_leaps":
                # LEAPS Long Call: 杠杆 × 时间 × 便宜度 × 流动性
                # 越深度 ITM、越长时间、越低 IV，越好
                leverage = abs_delta * underlying / mid  # 1 元期权能涨多少
                time_value_pct = max(0, (mid - max(underlying - strike if is_call else strike - underlying, 0)) / mid)
                time_value_pct = max(0.01, min(0.6, time_value_pct))  # 时间价值占比，越低越好
                iv_penalty = max(0.3, 1.0 - iv * 1.0)  # IV 越低评分越高
                score = leverage * iv_penalty * liquidity_factor / (1 + time_value_pct * 3)
            else:
                # 普通 long: leverage / 成本
                score = abs_delta * 100 / mid * liquidity_factor

            # LEAPS 用的特殊指标：杠杆和盈亏平衡点
            leverage_x = None
            breakeven_pct = None
            if not is_short and intent == "long_leaps":
                leverage_x = round(abs_delta * underlying / mid, 2)
                breakeven_strike = strike + mid if is_call else strike - mid
                breakeven_pct = round((breakeven_strike / underlying - 1) * 100, 1)

            candidates.append({
                "ticker": ticker,
                "type": type_,
                "strike": strike,
                "expiry": exp_str,
                "days": days,
                "bid": round(q["bid"], 3),
                "ask": round(q["ask"], 3),
                "mid": round(mid, 3),
                "spread_pct": round(spread_pct, 1),
                "iv": round(iv * 100, 1),
                "delta": round(delta, 3),
                "theta_per_day": round(-theta * shares if is_short else theta * shares, 2),
                "vega_per_1pct": round(vega * shares, 2),
                "premium_per_contract": round(premium, 2),
                "collateral_per_contract": round(collateral, 2),
                "annualized_yield_pct": round(annualized, 1),
                "prob_safe_pct": round(prob_safe, 1),
                "moneyness_pct": round((strike / underlying - 1) * 100, 1),
                "score": round(score, 2),
                "leverage_x": leverage_x,
                "breakeven_pct": breakeven_pct,
                "oi": int(q.get("oi", 0)),
                "volume": int(q.get("volume", 0)),
            })

    # 数据源失败 — 友好错误（不要让用户看到一个空表格）
    if not candidates and chain_stats["good_count"] == 0:
        return {
            "error": (
                f"📡 暂时拉不到 {ticker} 的 option chain。"
                f" 数据源临时不可用 — 请 1-2 分钟后重试，或换一个高流动性标的"
                f"（SPY、AAPL、NVDA、TSLA）。"
            ),
            "error_kind": "data_unavailable",
            "ticker": ticker,
            "data_source": {
                **_summarize_data_source(chain_stats),
                "schwab_last_err": _schwab_last_err,
            },
        }

    # 1. IV rank
    iv_rank = None
    if candidates:
        sample_iv = candidates[0]["iv"] / 100
        iv_rank = _compute_iv_rank(ticker, sample_iv)

    # 2. 回测（per ticker，一次就够）— 估个该方向短卖策略的胜率
    backtest = _backtest_strategy(
        ticker, sample_dte=min(max(timeframe, 5), 30),
        delta_target=sum(delta_band) / 2,
        is_short_put=(is_short and not is_call),
    ) if is_short else None

    # 3. 财报警告（per ticker，一次就够）
    earnings_date = _next_earnings_date(ticker, today)
    earnings_warning = None
    if earnings_date:
        earnings_days = (earnings_date - today).days
        if 0 <= earnings_days <= 30:
            earnings_warning = {"date": earnings_date.isoformat(), "days": earnings_days}

    # CSP 标记：short put + 标的看涨/接货意图
    is_csp = (is_short and not is_call)

    # 4. 给每个候选打初步 verdict + 算 spread 替代 + 包租公分
    for c in candidates:
        # 如果到期跨越财报，加 flag
        exp_d = date.fromisoformat(c["expiry"])
        earnings_cross = bool(earnings_date and today < earnings_date < exp_d)
        if earnings_cross:
            c["earnings_warning"] = earnings_warning

        # Short option 距行权 < 8% 时，提供 spread 替代信号
        if is_short and abs(c["moneyness_pct"]) < 8:
            # 买保护腿在 strike 外 5%
            if is_call:
                protect_strike = round(c["strike"] * 1.05, 0)
            else:
                protect_strike = round(c["strike"] * 0.95, 0)
            max_loss = abs(c["strike"] - protect_strike) * 100 * c["contracts"] if c.get("contracts") else abs(c["strike"] - protect_strike) * 100
            c["spread_alt"] = {
                "protect_strike": protect_strike,
                "max_loss": max_loss,
            }

        # 包租公算法 1.2：替换原 score 为 rent_score（仅 short）
        earnings_days_until = (earnings_date - today).days if earnings_date else None
        if is_short:
            ls = _landlord_score(c, is_csp, underlying, iv_rank, backtest,
                                  earnings_cross, earnings_days_until, risk)
            c["rent_score"] = ls["score"]
            c["score_components"] = ls["components"]
            c["score"] = ls["score"]   # 排序统一用 rent_score

        c["verdict"] = _make_verdict(c, is_short, intent, iv_rank,
                                      backtest, risk=risk, is_csp=is_csp,
                                      underlying=underlying)

    # 5. 排序后保留 top 15
    candidates.sort(key=lambda x: (-x["verdict"]["tier"], -x["score"]))
    candidates = candidates[:15]

    return {
        "ticker": ticker,
        "underlying": underlying,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "algorithm": {
            "name": ALGORITHM_NAME,
            "version": ALGORITHM_VERSION,
            "tagline": ALGORITHM_TAGLINE,
        },
        "iv_rank": iv_rank,
        "criteria": {
            "direction": direction,
            "intent": intent,
            "timeframe": timeframe,
            "risk": risk,
            "delta_band": list(delta_band),
            "is_call": is_call,
            "is_short": is_short,
            "expiries_searched": target_exps,
        },
        "candidates": candidates[:10],
        "total_examined": len(candidates),
        "data_source": _summarize_data_source(chain_stats),
    }


def _generate_morning_brief(positions: List[dict], prices: Dict[str, Dict],
                             total_pnl: float, total_realized: float,
                             lang: str = "zh") -> List[str]:
    """生成基于规则的每日 brief（非 AI，但是数据驱动且个性化）"""
    lines = []

    # 1. 今日市场
    today_chgs = []
    for tk, info in prices.items():
        if not info or info.get("prev", 0) == 0: continue
        pct = (info["price"] - info["prev"]) / info["prev"] * 100
        arrow = "📈" if pct >= 0 else "📉"
        today_chgs.append(f"{tk} ${info['price']:.0f} {arrow}{abs(pct):.1f}%")
    if today_chgs:
        lines.append(_T(lang, "📊 今日市场:") + " " + " · ".join(today_chgs[:4]))

    # 2. 今日组合 P&L
    active = [p for p in positions if not p["closed"] and p["days"] >= 0]
    if active:
        emoji_key = "🟢 持仓累计浮盈亏" if total_pnl >= 0 else "🔴 持仓累计浮盈亏"
        line = f"{_T(lang, emoji_key)} ${total_pnl:+,.0f}"
        if total_realized:
            line += f" · {_T(lang, '已实现')} ${total_realized:+,.0f}"
        lines.append(line)

    # 3. 财报警告（最近 1 个）
    earnings_alerts = [p for p in active if p.get("earnings_before_expiry")
                       and p.get("earnings_days_until", 999) <= 21]
    if earnings_alerts:
        e = sorted(earnings_alerts, key=lambda p: p["earnings_days_until"])[0]
        lines.append(
            f"⚠️ {e['ticker']} {_T(lang, '财报剩')} {e['earnings_days_until']} {_T(lang, '天')} "
            f"({e['earnings_date']}), {e['label']} {e['expiry']} "
            f"{_T(lang, '到期跨越 — 留意 IV crush')}"
        )

    # 4. 利润目标 / 风险
    actionable = [p for p in active if p["pnl_pct"] >= 80]
    if actionable:
        a = max(actionable, key=lambda p: p["pnl_pct"])
        achieved = _T(lang, "已实现 {pct}% 权利金", pct=f"{a['pnl_pct']:.0f}")
        consider = _T(lang, "可考虑平仓锁利")
        lines.append(f"🎯 {a['label']} {achieved} (${a['pnl']:+,.0f}), {consider}")

    # 5. 即将到期
    expiring = [p for p in active if p["days"] <= 3]
    if expiring:
        e = min(expiring, key=lambda p: p["days"])
        money = e.get("moneyness", 0)
        is_call = e["type"] == "call"
        is_itm = (is_call and money < 0) or (not is_call and money > 0)
        risk_note = _T(lang, "已 ITM，关注指派风险") if is_itm else _T(lang, "OTM 距 {pct}%", pct=f"{abs(money):.1f}")
        lines.append(f"⏱️ {e['label']} " + _T(lang, "剩 {days} 天到期 · {note}", days=e['days'], note=risk_note))

    # 6. 危险持仓警告
    danger = [p for p in active if (p["type"] == "call" and p["moneyness"] < 5)
              or (p["type"] == "put" and p["moneyness"] > -5)]
    if danger and not any("ITM" in l for l in lines):
        d = danger[0]
        lines.append(f"🚨 {d['label']} " + _T(lang, "距行权仅 {pct}%，gamma 风险大", pct=f"{abs(d['moneyness']):.1f}"))

    return lines


def _check_yf():
    try:
        import yfinance  # noqa: F401
        return True
    except ImportError:
        return False


# ── Vercel handler ────────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        # Health check
        self._send_json(200, {
            "ok": True,
            "yfinance_available": _check_yf(),
            "service": "Option Analysis Platform API",
            "ts": datetime.now().isoformat(),
        })

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body) if body else {}
            action = payload.get("action", "compute")
            if action == "debug_env":
                # Safe diagnostic — only returns whether vars are set + length
                import os as _os
                result = {
                    "has_client_id": bool(_os.environ.get("SCHWAB_CLIENT_ID")),
                    "has_client_secret": bool(_os.environ.get("SCHWAB_CLIENT_SECRET")),
                    "has_refresh_token": bool(_os.environ.get("SCHWAB_REFRESH_TOKEN")),
                    "client_id_len": len(_os.environ.get("SCHWAB_CLIENT_ID", "")),
                    "client_secret_len": len(_os.environ.get("SCHWAB_CLIENT_SECRET", "")),
                    "refresh_token_len": len(_os.environ.get("SCHWAB_REFRESH_TOKEN", "")),
                    "module_var_id_len": len(SCHWAB_CLIENT_ID),
                    "module_var_secret_len": len(SCHWAB_CLIENT_SECRET),
                    "module_var_refresh_len": len(SCHWAB_REFRESH_TOKEN),
                    "env_keys_count": len(_os.environ),
                    "schwab_env_keys": [k for k in _os.environ if "SCHWAB" in k],
                }
            elif action == "recommend":
                result = recommend(payload)
            else:
                result = compute(payload)
            self._send_json(200, result)
        except Exception as e:
            self._send_json(500, {
                "error": str(e),
                "trace": traceback.format_exc(),
            })
