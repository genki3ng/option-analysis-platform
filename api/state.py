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
                out[(float(row["strike"]), type_)] = {
                    "bid": bid, "ask": ask, "mid": mid, "last": last, "iv": iv,
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
            u = get_underlying_at(p["ticker"], d, earliest - timedelta(days=5))
            if u is None: continue
            days_left = (p["expiry"] - d).days
            T = max(days_left / 365.0, 1e-8)
            iv = pos_iv.get(position_id(p), 0.4)
            shares = p["contracts"] * 100
            sold = p["sell_price"] * shares

            if days_left <= 0:
                mark = max(u - p["strike"], 0) if p["type"] == "call" else max(p["strike"] - u, 0)
            else:
                mark = price_option(u, p["strike"], T, RISK_FREE, iv, p["type"] == "call")[0]

            mktval = mark * shares
            pnl = sold - mktval
            total_pnl += pnl
            total_sold += sold
            per_pos[position_id(p)] = pnl

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
        u = prices.get(p["ticker"], {}).get("price", 0)
        if u <= 0: continue
        days_left = (p["expiry"] - today).days
        T = max(days_left / 365.0, 1e-8)
        iv = pos_iv.get(position_id(p), 0.4)
        shares = p["contracts"] * 100
        sold = p["sell_price"] * shares
        if days_left <= 0:
            mark = max(u - p["strike"], 0) if p["type"] == "call" else max(p["strike"] - u, 0)
        else:
            mark = price_option(u, p["strike"], T, RISK_FREE, iv, p["type"] == "call")[0]
        mktval = mark * shares
        pnl = sold - mktval
        today_pnl += pnl
        today_sold += sold
        today_per_pos[position_id(p)] = pnl

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

    port_facts = [
        f"{len(active)} 个空头持仓，总浮盈 ${total_pnl:+,.0f}（{total_pct:+.1f}%）",
        f"每日 Theta +${total_theta:.0f}",
        f"已收权利金 ${total_sold:,.0f}",
    ]
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

    return {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "yfinance_available": _check_yf(),
        "tickers": prices,
        "intraday": intraday,
        # 向后兼容（前端老代码用到）
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


def _make_verdict(opt: dict, is_short: bool, intent: str, iv_rank: Optional[dict]) -> dict:
    """生成一句话推荐 verdict（权重评分，严重的优劣权重更大）"""
    pros, cons = [], []
    weight = 0  # 综合权重：正数 = 偏好，负数 = 不偏好

    # 流动性（通用）
    if opt["spread_pct"] > 10:
        cons.append(f"买卖价差大 {opt['spread_pct']:.0f}%（成交可能折价）"); weight -= 2
    elif opt["spread_pct"] > 5:
        cons.append(f"买卖价差 {opt['spread_pct']:.0f}%"); weight -= 1
    elif opt["spread_pct"] < 3:
        pros.append("流动性好（spread 小）"); weight += 1

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

    # 综合评级（基于加权得分，越大越好）
    if weight >= 5:
        tier, stars, label, color = 5, "⭐⭐⭐⭐⭐", "强烈推荐", "green"
    elif weight >= 2:
        tier, stars, label, color = 4, "⭐⭐⭐⭐", "推荐", "green"
    elif weight >= -1:
        tier, stars, label, color = 3, "⭐⭐⭐", "一般", "yellow"
    elif weight >= -4:
        tier, stars, label, color = 2, "⭐⭐", "谨慎", "orange"
    else:
        tier, stars, label, color = 1, "⭐", "不建议", "red"

    # 一句话总结
    if pros and not cons:
        one_line = "✅ 多项优势：" + " · ".join(pros[:2])
    elif pros and cons:
        one_line = "⚖️ 优 (" + pros[0] + ")，但 " + cons[0]
    elif cons and not pros:
        one_line = "⚠️ " + " · ".join(cons[:2])
    else:
        one_line = "符合筛选条件，但无突出优劣"

    return {
        "tier": tier,
        "weight": weight,
        "stars": stars,
        "label": label,
        "color": color,
        "one_line": one_line,
        "pros": pros,
        "cons": cons,
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
        for (strike, type_), q in chain.items():
            if (type_ == "call") != is_call:
                continue
            if q["bid"] <= 0 or q["mid"] <= 0 or q["iv"] <= 0:
                continue  # 流动性差或无数据

            days = (date.fromisoformat(exp_str) - today).days
            if days < 1:
                continue
            T = days / 365.0
            iv = q["iv"]
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
            prob_safe = (1 - abs_delta) * 100  # 粗估安全概率

            # 综合评分
            liquidity_factor = max(0.3, 1.0 - spread_pct / 50)
            if is_short:
                # Short: 年化收益 × 安全度 × 流动性
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
            })

    # 1. 先算 IV rank（用任意候选的 IV 作样本）
    iv_rank = None
    if candidates:
        sample_iv = candidates[0]["iv"] / 100
        iv_rank = _compute_iv_rank(ticker, sample_iv)

    # 2. 给每个候选打 verdict（含 tier 1-5）
    for c in candidates:
        c["verdict"] = _make_verdict(c, is_short, intent, iv_rank)

    # 3. 按 (verdict tier 优先, 原 score 次要) 排序 —
    #    确保 ⭐⭐⭐⭐⭐ 永远排在 ⭐⭐⭐ 前面
    candidates.sort(key=lambda x: (-x["verdict"]["tier"], -x["score"]))

    return {
        "ticker": ticker,
        "underlying": underlying,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
