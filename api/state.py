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
            "tsla": {}, "meta": {},
            "total_sold": 0, "total_mktval": 0, "total_pnl": 0,
            "total_pnl_pct": 0, "total_theta": 0,
            "positions": [], "suggestions": [], "history": [],
        }

    positions = [parse_position(p) for p in positions_raw]
    tickers = list(set(p["ticker"] for p in positions))
    prices = fetch_prices(tickers + ["TSLA", "META"])  # 这俩拿来显示
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
            result = compute(payload)
            self._send_json(200, result)
        except Exception as e:
            self._send_json(500, {
                "error": str(e),
                "trace": traceback.format_exc(),
            })
