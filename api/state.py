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
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Tuple

RISK_FREE = 0.045

# Massive (Polygon-style) API key — 历史聚合数据
MASSIVE_KEY = "LGOwbUJ6_VvPovE08rGOwohlCkt6IFeL"
MASSIVE_BASE = "https://api.massive.com"

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
        for tk in set(tickers):
            if tk in _cache_prices:
                out[tk] = _cache_prices[tk]
                continue
            try:
                fi = yf.Ticker(tk).fast_info
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


def fetch_chain(ticker: str, expiry_str: str) -> Dict:
    """{(strike, 'call'|'put'): {bid, ask, mid, last, iv}}"""
    key = (ticker, expiry_str)
    if key in _cache_chain:
        return _cache_chain[key]
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        if expiry_str not in t.options:
            _cache_chain[key] = {}
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
                    "volume": volume, "oi": oi,
                }
        _cache_chain[key] = out
        return out
    except Exception:
        _cache_chain[key] = {}
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
        t = yf.Ticker(ticker)
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
        df = yf.Ticker(ticker).history(
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


def position_advice(ps):
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
    status = "🟢 持仓健康"
    facts, actions = [], []

    is_otm = (is_call and money > 0) or ((not is_call) and money < 0)
    moneyness_label = "OTM 安全区" if is_otm else "ITM 风险区"
    facts.append(f"{ps['ticker']} 现价 ${underlying:.2f}，行权价 ${strike:.0f}（距 {money:+.1f}%，{moneyness_label}）")
    facts.append(f"剩余 {days} 天到期，{ps['contracts']} 张合约")
    facts.append(f"现在买回需 ${buyback_total:,.0f}，浮盈亏 ${pnl:+,.0f} ({pnl_pct:+.1f}%)")

    pnl_word = "锁利" if pnl >= 0 else "止损"
    pnl_amt = abs(pnl)

    if is_call:
        if money < 0:
            severity = _max_sev(severity, "danger"); status = "🚨 Call 已 ITM"
            facts.append(f"⚡ 标的 > 行权价，到期需交付 {shares} 股")
            actions += [f"立即买回（${buyback_total:,.0f}，{pnl_word} ${pnl_amt:,.0f}）", "Roll up", "买保护 Call"]
        elif money < 5:
            severity = _max_sev(severity, "danger"); status = "🚨 接近行权（ATM）"
            actions += [f"立即买回（${buyback_total:,.0f}，{pnl_word} ${pnl_amt:,.0f}）", "Roll up"]
        elif money < 15:
            severity = _max_sev(severity, "warn"); status = "⚠️ 距行权较近"
    else:
        cash_need = strike * shares
        if money > 0:
            severity = _max_sev(severity, "danger"); status = "🚨 Put 已 ITM"
            facts.append(f"⚡ 到期被指派需 ${cash_need:,.0f} 接 {shares} 股")
            actions += [f"立即买回（${buyback_total:,.0f}，{pnl_word} ${pnl_amt:,.0f}）", "Roll 到下月", "接受指派"]
        elif money > -5:
            severity = _max_sev(severity, "danger"); status = "🚨 接近行权（ATM）"
            actions += [f"立即买回（${buyback_total:,.0f}，{pnl_word} ${pnl_amt:,.0f}）", "Roll 到下月"]
        elif money > -15:
            severity = _max_sev(severity, "warn"); status = "⚠️ 距行权较近"

    if pnl_pct >= 80:
        if severity == "good": status = "🎯 强烈建议平仓"
        facts.append(f"💰 已实现 {pnl_pct:.0f}% 权利金（${pnl:,.0f}）")
        ac = f"立即买回 ${mark:.2f}/股 锁利 ${pnl:,.0f}"
        if ac not in actions: actions.insert(0, ac)
    elif pnl_pct >= 50:
        if severity == "good":
            status = "✅ 可考虑平仓"
            actions.insert(0, f"买回 ${mark:.2f}/股 锁利 ${pnl:,.0f}")

    if pnl_pct < -50:
        severity = _max_sev(severity, "danger")
        facts.append(f"📉 浮亏 ${-pnl:,.0f}（>50% 权利金）")
    elif pnl_pct < -20:
        severity = _max_sev(severity, "warn")
        facts.append(f"📉 浮亏 ${-pnl:,.0f}")

    if 0 < days <= 3:
        facts.append(f"⏱️ 仅 {days} 天到期，gamma 风险大")

    # 财报警告
    if ps.get("earnings_before_expiry"):
        ed = ps["earnings_date"]
        eud = ps["earnings_days_until"]
        if eud is not None and eud >= 0:
            severity = _max_sev(severity, "warn")
            if ps["type"] == "put" and ps.get("type") == "put":
                # Short put 财报后股价跌可能很惨
                facts.append(f"⚠️ {ed} 财报（剩 {eud} 天）在你到期前，财报前 IV 通常飙升、后 IV crush；卖 put 同时承担方向 + IV 风险")
            else:
                facts.append(f"⚠️ {ed} 财报（剩 {eud} 天）在你到期前，注意 IV crush + gamma 风险")
            if "财报前 1-2 天平仓" not in str(actions):
                actions.insert(0, "财报前 1-2 天考虑平仓，避免 IV crush")

    if not actions:
        actions.append("继续持有让 Theta 累积收益" if pnl_pct >= 0 else "继续持有等时间衰减")

    return {
        "position_id": ps["id"], "label": ps["label"],
        "subtitle": f"Exp {ps['expiry']} · {ps['contracts']} 张 · 剩 {days} 天",
        "type": severity, "status": status,
        "pnl": pnl, "pnl_pct": pnl_pct,
        "facts": facts, "actions": actions,
    }


def get_suggestions(positions):
    cards = []
    active = [p for p in positions if not p["closed"] and p["days"] >= 0]
    total_pnl = sum(p["pnl"] for p in active)
    total_sold = sum(p["sold"] for p in active) or 1
    total_pct = total_pnl / total_sold * 100
    total_theta = sum(p["daily_theta"] for p in active)
    n_danger = sum(1 for p in active if (p["type"] == "call" and p["moneyness"] < 5) or (p["type"] == "put" and p["moneyness"] > -5))
    n_tp = sum(1 for p in active if p["pnl_pct"] >= 80)
    n_close = sum(1 for p in active if 0 <= p["days"] <= 3)

    # Beta-weighted Delta（简化版：直接累加，不调 beta，因为 single-ticker 多）
    total_delta_shares = sum(p["delta"] * p["contracts"] * 100 for p in active)

    # 财报警告计数
    n_earnings = sum(1 for p in active if p.get("earnings_before_expiry"))

    # 包租公视角：持仓集中度 — 单一 ticker 的抵押金占比
    #   short option 用 strike × contracts × 100 估算"如果全部被指派"的暴露
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
        f"{len(active)} 个空头持仓，总浮盈 ${total_pnl:+,.0f}（{total_pct:+.1f}%）",
        f"每日 Theta +${total_theta:.0f}",
        f"已收权利金 ${total_sold:,.0f}",
        f"📐 组合 Delta 等价 {total_delta_shares:+.0f} 股（{'long' if total_delta_shares > 0 else 'short'}-biased）",
    ]
    if len(ticker_exposure) > 1:
        port_facts.append(f"🏘 集中度：{top_ticker} 占 {top_concentration:.0f}%（共 {len(ticker_exposure)} 个标的）")
    if n_earnings:
        port_facts.append(f"⚠️ {n_earnings} 个持仓在财报之后到期（IV crush 风险）")
    if n_danger: port_facts.append(f"🚨 {n_danger} 个持仓接近/超行权价")
    if n_tp: port_facts.append(f"🎯 {n_tp} 个持仓达到 80% 利润")
    if n_close: port_facts.append(f"⏱️ {n_close} 个持仓 3 天内到期")

    if n_danger > 0:
        port_sev, port_status = "danger", f"🚨 {n_danger} 个需评估"
    elif n_tp > 0:
        port_sev, port_status = "good", f"🎯 {n_tp} 个建议平仓"
    else:
        port_sev, port_status = "good", "🟢 组合健康"

    cards.append({
        "position_id": None, "label": "组合总览",
        "subtitle": f"{len(active)} 持仓 · 实时聚合",
        "type": port_sev, "status": port_status,
        "pnl": total_pnl, "pnl_pct": total_pct,
        "facts": port_facts, "actions": [],
    })

    # 集中度警告 — 包租公说"别把所有租客都放在一栋楼"
    if top_concentration >= 50 and len(ticker_exposure) >= 2:
        if top_concentration >= 75:
            sev, status = "danger", f"🚨 集中度过高 · {top_ticker} 占 {top_concentration:.0f}%"
            advice = "几乎全部押在一个标的上。这个 ticker 单日大跌 10% 你可能就被全员指派。"
        elif top_concentration >= 60:
            sev, status = "warn", f"⚠️ 集中度偏高 · {top_ticker} 占 {top_concentration:.0f}%"
            advice = "超过六成暴露在一个标的。考虑下次推荐时换个 ticker，分散一下房产。"
        else:
            sev, status = "caution", f"💡 集中度提醒 · {top_ticker} 占 {top_concentration:.0f}%"
            advice = "过半暴露在单一标的。包租公经验：3-5 个标的左右更稳。"
        cards.append({
            "position_id": None,
            "label": f"集中度 · {top_ticker}",
            "subtitle": f"{top_concentration:.0f}% / 共 {len(ticker_exposure)} 标的",
            "type": sev, "status": status,
            "pnl": 0, "pnl_pct": 0,
            "facts": [
                advice,
                f"当前 {top_ticker} 抵押暴露 ${ticker_exposure[top_ticker]:,.0f}",
                f"组合总抵押暴露 ${total_exposure:,.0f}",
                "💡 一只标的大跌、IV 飙升、财报暴雷 — 全靠它一个，没有缓冲。",
            ],
            "actions": [],
        })

    for ps in positions:
        adv = position_advice(ps)
        if adv: cards.append(adv)
    return cards


# ── 主计算入口 ────────────────────────────────────────────────────────────────
def compute(payload):
    positions_raw = payload.get("positions", [])
    state = payload.get("state", {})

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
    suggestions = get_suggestions(enriched)

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

    morning_brief = _generate_morning_brief(enriched, prices, total_pnl - total_realized, total_realized)

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


def _build_occ_symbol(ticker: str, expiry: date, strike: float, is_call: bool) -> str:
    """构造 OCC option 符号，例如 TSLA260520P00400000"""
    y = expiry.strftime("%y%m%d")
    cp = "C" if is_call else "P"
    s = f"{int(round(strike * 1000)):08d}"
    return f"{ticker}{y}{cp}{s}"


_cache_occ_hist: Dict[str, dict] = {}

def fetch_massive_option_history(occ_symbol: str, days_back: int = 30) -> Optional[dict]:
    """通过 Massive 拉取期权过去 N 天的日 K，计算价位带"""
    if occ_symbol in _cache_occ_hist:
        return _cache_occ_hist[occ_symbol]

    end = date.today()
    start = end - timedelta(days=days_back + 7)  # 多拿几天保险
    url = (f"{MASSIVE_BASE}/v2/aggs/ticker/O:{occ_symbol}/range/1/day/"
           f"{start.isoformat()}/{end.isoformat()}"
           f"?adjusted=true&sort=desc&limit=120&apiKey={MASSIVE_KEY}")
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            _cache_occ_hist[occ_symbol] = None
            return None
        closes = [float(r["c"]) for r in results if r.get("c", 0) > 0]
        if not closes:
            return None
        # 最近 30 天
        recent = closes[:30]
        out = {
            "n_days": len(recent),
            "low": round(min(recent), 3),
            "high": round(max(recent), 3),
            "avg": round(sum(recent) / len(recent), 3),
            "median": round(sorted(recent)[len(recent)//2], 3),
            "latest": round(recent[0], 3),
            "oldest": round(recent[-1], 3),
        }
        _cache_occ_hist[occ_symbol] = out
        return out
    except Exception:
        _cache_occ_hist[occ_symbol] = None
        return None


def _compute_iv_rank(ticker: str, current_iv: float) -> Optional[dict]:
    """用历史 30 天已实现波动率近似 IV rank（粗略但有用）"""
    if current_iv <= 0:
        return None
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=True)
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
        hist = yf.Ticker(ticker).history(period="6mo", interval="1d", auto_adjust=True)
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
ALGORITHM_VERSION = "1.1"
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


def _wheel_friendly_factor(strike: float, underlying: float, is_csp: bool,
                            price_band: Optional[dict]) -> tuple:
    """
    Wheel 友好度：对 CSP，strike 是否在历史合理位置？
    若 strike 显著低于 30d 均价 → 被指派 = 好价位接货
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


def _landlord_score(opt: dict, is_csp: bool, underlying: float,
                     iv_rank: Optional[dict], backtest: Optional[dict],
                     earnings_cross: bool, risk: str) -> dict:
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

    # 7. 财报跨期：保守 = 硬否决，平衡 = 严重扣分，激进 = 轻微
    earnings_f = 1.0
    if earnings_cross:
        if risk == "conservative":
            earnings_f = 0.0           # 包租公保守派：财报房客一律不租
        elif risk == "balanced":
            earnings_f = 0.55
        else:
            earnings_f = 0.78

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
                  iv_rank: Optional[dict], price_band: Optional[dict] = None,
                  backtest: Optional[dict] = None, risk: str = "balanced",
                  is_csp: bool = False, underlying: float = 0) -> dict:
    """生成一句话推荐 verdict（包租公算法 1.0 — 房东视角，损失厌恶）"""
    pros, cons = [], []
    weight = 0  # 综合权重：正数 = 偏好，负数 = 不偏好

    # ── 包租公专属信号 #1：Wheel 友好（CSP strike 是否好接货价）
    if is_csp and underlying > 0:
        _, wf_signal = _wheel_friendly_factor(opt["strike"], underlying, True, price_band)
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

    # ── Massive 历史价位带信号（最近 30 天）
    if price_band:
        mid = opt["mid"]
        lo, hi, avg = price_band["low"], price_band["high"], price_band["avg"]
        rng = hi - lo
        if rng > 0:
            # 当前价在 30 天区间中的位置（0 = 最低，1 = 最高）
            pos = (mid - lo) / rng
            if is_short:
                # 卖期权：current 高（vs 历史）= 你能收更多权利金 = 好
                if pos >= 0.75:
                    pros.append(f"📊 当前 ${mid:.2f} 在 30d 区间高位（${lo:.2f}-${hi:.2f}），收的多")
                    weight += 2
                elif pos >= 0.55:
                    pros.append(f"📊 当前价处于 30d 区间偏高")
                    weight += 1
                elif pos <= 0.25:
                    cons.append(f"📊 当前 ${mid:.2f} 在 30d 区间低位（${lo:.2f}-${hi:.2f}），不如等反弹")
                    weight -= 2
            else:
                # 买期权：current 低 = 便宜 = 好
                if pos <= 0.25:
                    pros.append(f"📊 当前 ${mid:.2f} 在 30d 区间低位（${lo:.2f}-${hi:.2f}），买入便宜")
                    weight += 2
                elif pos <= 0.45:
                    pros.append(f"📊 当前价处于 30d 区间偏低")
                    weight += 1
                elif pos >= 0.75:
                    cons.append(f"📊 当前 ${mid:.2f} 在 30d 区间高位（${lo:.2f}-${hi:.2f}），买入偏贵")
                    weight -= 2

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
        exps = yf.Ticker(ticker).options
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
    if not ticker:
        return {"error": "请提供 ticker"}
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
    for exp_str in target_exps:
        chain = fetch_chain(ticker, exp_str)

        # Bug fix: 深度 ITM 期权 yfinance 经常不返回 IV → LEAPS 全被切空
        # Fallback: 取本 chain 同 type 所有非零 IV 的中位数，缺 IV 的合约借用
        same_type_ivs = [q["iv"] for (_, t), q in chain.items()
                         if t == ("call" if is_call else "put") and q["iv"] > 0]
        fallback_iv = (sorted(same_type_ivs)[len(same_type_ivs) // 2]
                       if same_type_ivs else 0.30)

        for (strike, type_), q in chain.items():
            if (type_ == "call") != is_call:
                continue
            # 只要求 bid+mid 有效；iv 缺失用 fallback（对 LEAPS 深度 ITM 很常见）
            if q["bid"] <= 0 or q["mid"] <= 0:
                continue
            iv = q["iv"] if q["iv"] > 0 else fallback_iv
            if iv <= 0:
                continue  # 还是没有 IV（chain 完全无数据）

            days = (date.fromisoformat(exp_str) - today).days
            if days < 1:
                continue
            T = days / 365.0
            mid = q["mid"]

            _, delta, theta, vega = price_option(
                underlying, strike, T, RISK_FREE, iv, is_call)
            abs_delta = abs(delta)
            if not (delta_band[0] <= abs_delta <= delta_band[1]):
                continue

            spread = q["ask"] - q["bid"]
            spread_pct = spread / mid * 100 if mid else 100

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

        # 包租公算法 1.0：替换原 score 为 rent_score（仅 short）
        if is_short:
            ls = _landlord_score(c, is_csp, underlying, iv_rank, backtest,
                                  earnings_cross, risk)
            c["rent_score"] = ls["score"]
            c["score_components"] = ls["components"]
            c["score"] = ls["score"]   # 排序统一用 rent_score

        c["verdict"] = _make_verdict(c, is_short, intent, iv_rank, None,
                                      backtest, risk=risk, is_csp=is_csp,
                                      underlying=underlying)

    # 5. 排序后保留 top 15，富集 Massive 价位带
    candidates.sort(key=lambda x: (-x["verdict"]["tier"], -x["score"]))
    candidates = candidates[:15]

    for c in candidates:
        occ = _build_occ_symbol(c["ticker"],
                                 date.fromisoformat(c["expiry"]),
                                 c["strike"],
                                 c["type"] == "call")
        hist = fetch_massive_option_history(occ, days_back=30)
        if hist:
            c["price_band"] = hist
            c["verdict"] = _make_verdict(c, is_short, intent, iv_rank, hist,
                                          backtest, risk=risk, is_csp=is_csp,
                                          underlying=underlying)

    # 6. 终极排序
    candidates.sort(key=lambda x: (-x["verdict"]["tier"], -x["score"]))

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
    }


def _generate_morning_brief(positions: List[dict], prices: Dict[str, Dict],
                             total_pnl: float, total_realized: float) -> List[str]:
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
        lines.append("📊 今日市场: " + " · ".join(today_chgs[:4]))

    # 2. 今日组合 P&L
    active = [p for p in positions if not p["closed"] and p["days"] >= 0]
    if active:
        emoji = "🟢" if total_pnl >= 0 else "🔴"
        lines.append(f"{emoji} 持仓累计浮盈亏 ${total_pnl:+,.0f}"
                     + (f" · 已实现 ${total_realized:+,.0f}" if total_realized else ""))

    # 3. 财报警告（最近 1 个）
    earnings_alerts = [p for p in active if p.get("earnings_before_expiry")
                       and p.get("earnings_days_until", 999) <= 21]
    if earnings_alerts:
        e = sorted(earnings_alerts, key=lambda p: p["earnings_days_until"])[0]
        lines.append(f"⚠️ {e['ticker']} 财报剩 {e['earnings_days_until']} 天 "
                     f"({e['earnings_date']})，你的 {e['label']} {e['expiry']} 到期跨越 — 留意 IV crush")

    # 4. 利润目标 / 风险（取最紧急的）
    actionable = [p for p in active if p["pnl_pct"] >= 80]
    if actionable:
        a = max(actionable, key=lambda p: p["pnl_pct"])
        lines.append(f"🎯 {a['label']} 已实现 {a['pnl_pct']:.0f}% 权利金"
                     f"（${a['pnl']:+,.0f}），可考虑平仓锁利")

    # 5. 即将到期
    expiring = [p for p in active if p["days"] <= 3]
    if expiring:
        e = min(expiring, key=lambda p: p["days"])
        money = e.get("moneyness", 0)
        is_call = e["type"] == "call"
        is_itm = (is_call and money < 0) or (not is_call and money > 0)
        risk_note = "已 ITM，关注指派风险" if is_itm else f"OTM 距 {abs(money):.1f}%"
        lines.append(f"⏱️ {e['label']} 剩 {e['days']} 天到期 · {risk_note}")

    # 6. 危险持仓警告
    danger = [p for p in active if (p["type"] == "call" and p["moneyness"] < 5)
              or (p["type"] == "put" and p["moneyness"] > -5)]
    if danger and not any("ITM" in l for l in lines):
        d = danger[0]
        lines.append(f"🚨 {d['label']} 距行权仅 {abs(d['moneyness']):.1f}%，gamma 风险大")

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
            if action == "recommend":
                result = recommend(payload)
            else:
                result = compute(payload)
            self._send_json(200, result)
        except Exception as e:
            self._send_json(500, {
                "error": str(e),
                "trace": traceback.format_exc(),
            })
