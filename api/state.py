"""
Option Analysis Platform — Vercel serverless function
POST 接受 { positions: [...], state: {} } → 返回完整计算结果

无任何持久化：所有用户数据放浏览器 localStorage
"""

from http.server import BaseHTTPRequestHandler
import json
import math
import re
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
    # ── 包租公式 position_advice（4 触发线 × 3 房东人设）
    "🟢 持仓健康 · {emoji} {style}": "🟢 Healthy · {emoji} {style}",
    "早收租派": "Early-close",
    "接货 Wheel": "Wheel",
    "死磕到期": "Hold-to-expiry",
    "剩余 {days} 天 · {n} 张 · 现在买回 ${bb} · 浮盈亏 {pct}%":
      "{days}d left · {n} contracts · buy back ${bb} now · P&L {pct}%",
    "|Δ| {d}（风格违约线 {th}）": "|Δ| {d} (style breach line {th})",
    "停用": "disabled",
    "立即买回 ${bb}（{verb} ${amt}）": "Buy back now ${bb} ({verb} ${amt})",
    "🚨 红线触发 · 财报跨期": "🚨 Red line · earnings cross",
    "🚨 {date} 财报（剩 {n} 天）在到期前 — 红线 · 立即买回，不接货":
      "🚨 {date} earnings ({n}d away) before expiry — red line, buy back now, no assign",
    "立即买回 ${bb}（避免财报 gap）": "Buy back now ${bb} (avoid earnings gap)",
    "⚠️ 房客违约触发 · {emoji} {style}": "⚠️ Tenant breach · {emoji} {style}",
    "⚠️ |Δ| {d} ≥ {th}（{style} 风格违约线）— Δ 是接货真风险，已亮起":
      "⚠️ |Δ| {d} ≥ {th} ({style} breach line) — Δ is the real assignment risk, alarm lit",
    "Roll 到下月（保持收租，不接货）": "Roll to next month (keep collecting, no assign)",
    "止损平仓 ${bb}（亏 ${amt}）": "Stop out ${bb} (loss ${amt})",
    "Roll 到下月 / 接货转 CC（Wheel 阶段二）":
      "Roll to next month / accept assignment → CC (Wheel phase 2)",
    "⏱️ 21 天换租线 · {emoji} {style}": "⏱️ 21-DTE cutoff · {emoji} {style}",
    "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 经验）— Wheel 派：盈利则关，亏损接货":
      "⏱️ {n}d left ≤ {th}d (Tasty 21-DTE rule) — Wheel: close if profitable, assign if loss",
    "盈利状态 → 买回 ${bb} 锁 ${pnl}": "Profitable → buy back ${bb}, lock ${pnl}",
    "亏损状态 → 持到 expire 接货（Wheel 阶段二）":
      "Loss → hold to expiry for assignment (Wheel phase 2)",
    "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 经验）— 强制平仓，不论盈亏":
      "⏱️ {n}d left ≤ {th}d (Tasty 21-DTE rule) — force close regardless of P&L",
    "强制买回 ${bb}（gamma 风险不值剩余 theta）":
      "Force buy back ${bb} (gamma risk not worth remaining theta)",
    "📬 早收租达成 · {emoji} {style}": "📬 Early collect hit · {emoji} {style}",
    "📬 已达 {pct}% ≥ 锁利目标 {th}% — 早收租触发":
      "📬 {pct}% ≥ profit target {th}% — early-collect triggered",
    "💰 死磕到期 · 等 {n} 天 expire": "💰 Hold to expiry · {n}d to expire",
    "持到 expire 吃满 ${sold}（OTM 归零最爽）":
      "Hold to expire for full ${sold} (OTM → zero is the goal)",
    "ITM 状态 — 准备接货 ${cash}（{n} 股）":
      "ITM — prepare to take assignment ${cash} ({n} shares)",
    "OTM 状态 — 等 expire 自动归零": "OTM — wait for expiry to zero out",
    "📬 离 {th}% 锁利还差 {gap}%（当前 {cur}%）":
      "📬 {gap}% away from {th}% lock target (currently {cur}%)",
    "⚠️ 离 |Δ| {th} 违约线还差 {gap}（当前 {cur}）":
      "⚠️ {gap} away from |Δ| {th} breach line (currently {cur})",
    "⏱️ 离 21 天换租线还差 {gap} 天（当前 {cur} 天）":
      "⏱️ {gap}d away from 21-DTE cutoff (currently {cur}d)",
    "持续监控 · 让 theta 累积收益": "Monitor · let theta accumulate",
    "持续监控 · 等时间衰减": "Monitor · wait for time decay",
    "📉 浮亏 ${amt}（> 50% 权利金，关注 Δ 是否同步上升）":
      "📉 Unrealized loss ${amt} (> 50% of premium — watch if Δ rises)",
    "持续监控": "Monitor",
    "Exp {exp} · {n} 张 · 剩 {d} 天 · {emoji} {style}":
      "Exp {exp} · {n} contracts · {d}d left · {emoji} {style}",
    # Concentration card — 中性化文案，承认集中是策略选择
    "⚠️ 单点集中 · {tk} 占 {pct}%": "⚠️ Single-point · {tk} = {pct}%",
    "💡 高度集中 · {tk} 占 {pct}%": "💡 Highly concentrated · {tk} = {pct}%",
    "🏘 集中度 · {tk} 占 {pct}%": "🏘 Concentration · {tk} = {pct}%",
    "几乎全部押在一个标的。这是你的策略选择 — 留意单点风险（大跌、IV 飙、财报暴雷）就行。":
      "Nearly all exposure on one ticker. That's your call — just stay aware of single-point risk (drawdowns, IV spikes, earnings surprises).",
    "超过七成在一个标的。包租公没有标准答案 — 集中收得多，分散更抗黑天鹅，看你的偏好。":
      "Over 70% on one ticker. No one right answer — concentration collects more rent, diversification weathers black swans. Your call.",
    "六到七成在单一标的。属于偏集中的策略，因人而异 — 看你的资金体量与投资目标。":
      "60-70% on a single ticker. A concentrated stance — fits some accounts and goals more than others.",
    "💡 集中是策略选择，不是 bug — 关键看你能不能扛单点波动。":
      "💡 Concentration is a strategy choice, not a bug — what matters is whether you can ride out a single-name move.",
    # Legacy keys retained for safety (no longer used after 2026-05-19)
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
    # ── Morning brief v2: 包租公管家 + Top 3 + chips ──
    "包租公管家": "Landlord Concierge",
    "持仓 P&L": "P&L",
    "今日 Theta": "Today Theta",
    "未来 7 天到期": "Next 7d expiry",
    "个": "",
    "今日 {n} 件事要看": "{n} items to watch today",
    "持仓平稳，无紧急信号": "Portfolio calm — no urgent signals",
    "{tk} 集中度": "{tk} concentration",
    "跳到": "jumped to",
    "跌到": "dropped to",
    "隔夜 VIX {v} {verb} {p} ({c}%)": "VIX {v} {verb} {p} overnight ({c}%)",
    "VIX 跳涨 {pct}% 至 {v}": "VIX spiked {pct}% to {v}",
    "卖权利金窗口期，扫一眼推荐": "Premium-selling window — check recommendations",
    "{label} 进入 ITM": "{label} entered ITM",
    "昨天还安全，今天突破行权 — 留意指派": "Was safe yesterday, breached strike today — watch assignment",
    "{tk} {d} 天后财报，{label} 跨越": "{tk} earnings in {d}d, {label} crosses it",
    "留意 IV crush 风险": "Watch for IV crush risk",
    "昨天 {yp}%，突破 80% — 可考虑锁利":
      "Yesterday {yp}%, now past 80% — consider locking in profit",
    "{label} 剩 {d} 天到期": "{label} expires in {d}d",
    "进入 7 天到期窗口，准备处理": "Entered 7-day window — prep an exit",
    "接近锁利窗口": "Near profit-taking window",
    "{label} 距行权仅 {pct}%": "{label} only {pct}% from strike",
    "gamma 风险大": "high gamma risk",
    "剩 {d} 天": "{d}d left",
    "浮亏 ${pnl}": "down ${pnl}",
    "考虑买回 / roll": "consider buyback / roll",
    "盯紧，考虑止损": "watch closely — consider stop",
    "浮盈 ${pnl} · 剩 {d} 天 · 接近锁利窗口": "${pnl} profit · {d}d left · near lock-in",
    "{tk} 新闻: {title}": "{tk} news: {title}",
    "{pub} · {h}h 前": "{pub} · {h}h ago",
    "看持仓 →": "View →",
    "看推荐 →": "Recommend →",
    "看持仓": "View",
    "看推荐": "Recommend",
    "看原文": "Read",
    "📅 未来 14 天关键日": "📅 Next 14 days",
    "财报": "Earnings",
    "持仓到期": "Expiry",
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
    # ── 包租公式 position_advice（4 觸發線 × 3 房東人設）
    "🟢 持仓健康 · {emoji} {style}": "🟢 持倉健康 · {emoji} {style}",
    "早收租派": "早收租派",
    "接货 Wheel": "接貨 Wheel",
    "死磕到期": "死磕到期",
    "剩余 {days} 天 · {n} 张 · 现在买回 ${bb} · 浮盈亏 {pct}%":
      "剩餘 {days} 天 · {n} 張 · 現在買回 ${bb} · 浮盈虧 {pct}%",
    "|Δ| {d}（风格违约线 {th}）": "|Δ| {d}（風格違約線 {th}）",
    "停用": "停用",
    "立即买回 ${bb}（{verb} ${amt}）": "立即買回 ${bb}（{verb} ${amt}）",
    "🚨 红线触发 · 财报跨期": "🚨 紅線觸發 · 財報跨期",
    "🚨 {date} 财报（剩 {n} 天）在到期前 — 红线 · 立即买回，不接货":
      "🚨 {date} 財報（剩 {n} 天）在到期前 — 紅線 · 立即買回，不接貨",
    "立即买回 ${bb}（避免财报 gap）": "立即買回 ${bb}（避免財報 gap）",
    "⚠️ 房客违约触发 · {emoji} {style}": "⚠️ 房客違約觸發 · {emoji} {style}",
    "⚠️ |Δ| {d} ≥ {th}（{style} 风格违约线）— Δ 是接货真风险，已亮起":
      "⚠️ |Δ| {d} ≥ {th}（{style} 風格違約線）— Δ 是接貨真風險，已亮起",
    "Roll 到下月（保持收租，不接货）": "Roll 到下月（保持收租，不接貨）",
    "止损平仓 ${bb}（亏 ${amt}）": "止損平倉 ${bb}（虧 ${amt}）",
    "Roll 到下月 / 接货转 CC（Wheel 阶段二）": "Roll 到下月 / 接貨轉 CC（Wheel 階段二）",
    "⏱️ 21 天换租线 · {emoji} {style}": "⏱️ 21 天換租線 · {emoji} {style}",
    "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 经验）— Wheel 派：盈利则关，亏损接货":
      "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 經驗）— Wheel 派：盈利則關，虧損接貨",
    "盈利状态 → 买回 ${bb} 锁 ${pnl}": "盈利狀態 → 買回 ${bb} 鎖 ${pnl}",
    "亏损状态 → 持到 expire 接货（Wheel 阶段二）":
      "虧損狀態 → 持到 expire 接貨（Wheel 階段二）",
    "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 经验）— 强制平仓，不论盈亏":
      "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 經驗）— 強制平倉，不論盈虧",
    "强制买回 ${bb}（gamma 风险不值剩余 theta）":
      "強制買回 ${bb}（gamma 風險不值剩餘 theta）",
    "📬 早收租达成 · {emoji} {style}": "📬 早收租達成 · {emoji} {style}",
    "📬 已达 {pct}% ≥ 锁利目标 {th}% — 早收租触发":
      "📬 已達 {pct}% ≥ 鎖利目標 {th}% — 早收租觸發",
    "💰 死磕到期 · 等 {n} 天 expire": "💰 死磕到期 · 等 {n} 天 expire",
    "持到 expire 吃满 ${sold}（OTM 归零最爽）":
      "持到 expire 吃滿 ${sold}（OTM 歸零最爽）",
    "ITM 状态 — 准备接货 ${cash}（{n} 股）": "ITM 狀態 — 準備接貨 ${cash}（{n} 股）",
    "OTM 状态 — 等 expire 自动归零": "OTM 狀態 — 等 expire 自動歸零",
    "📬 离 {th}% 锁利还差 {gap}%（当前 {cur}%）":
      "📬 離 {th}% 鎖利還差 {gap}%（當前 {cur}%）",
    "⚠️ 离 |Δ| {th} 违约线还差 {gap}（当前 {cur}）":
      "⚠️ 離 |Δ| {th} 違約線還差 {gap}（當前 {cur}）",
    "⏱️ 离 21 天换租线还差 {gap} 天（当前 {cur} 天）":
      "⏱️ 離 21 天換租線還差 {gap} 天（當前 {cur} 天）",
    "持续监控 · 让 theta 累积收益": "持續監控 · 讓 theta 累積收益",
    "持续监控 · 等时间衰减": "持續監控 · 等時間衰減",
    "📉 浮亏 ${amt}（> 50% 权利金，关注 Δ 是否同步上升）":
      "📉 浮虧 ${amt}（> 50% 權利金，關注 Δ 是否同步上升）",
    "持续监控": "持續監控",
    "Exp {exp} · {n} 张 · 剩 {d} 天 · {emoji} {style}":
      "Exp {exp} · {n} 張 · 剩 {d} 天 · {emoji} {style}",
    # Concentration card — 中性化文案
    "⚠️ 单点集中 · {tk} 占 {pct}%": "⚠️ 單點集中 · {tk} 佔 {pct}%",
    "💡 高度集中 · {tk} 占 {pct}%": "💡 高度集中 · {tk} 佔 {pct}%",
    "🏘 集中度 · {tk} 占 {pct}%": "🏘 集中度 · {tk} 佔 {pct}%",
    "几乎全部押在一个标的。这是你的策略选择 — 留意单点风险（大跌、IV 飙、财报暴雷）就行。":
      "幾乎全部押在一個標的。這是你的策略選擇 — 留意單點風險（大跌、IV 飆、財報暴雷）就行。",
    "超过七成在一个标的。包租公没有标准答案 — 集中收得多，分散更抗黑天鹅，看你的偏好。":
      "超過七成在一個標的。包租公沒有標準答案 — 集中收得多，分散更抗黑天鵝，看你的偏好。",
    "六到七成在单一标的。属于偏集中的策略，因人而异 — 看你的资金体量与投资目标。":
      "六到七成在單一標的。屬於偏集中的策略，因人而異 — 看你的資金體量與投資目標。",
    "💡 集中是策略选择，不是 bug — 关键看你能不能扛单点波动。":
      "💡 集中是策略選擇，不是 bug — 關鍵看你能不能扛單點波動。",
    # Legacy keys retained for safety (no longer used after 2026-05-19)
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
    # ── Morning brief v2 ──
    "包租公管家": "包租公管家",
    "持仓 P&L": "持倉 P&L",
    "今日 Theta": "今日 Theta",
    "未来 7 天到期": "未來 7 天到期",
    "个": "個",
    "今日 {n} 件事要看": "今日 {n} 件事要看",
    "持仓平稳，无紧急信号": "持倉平穩，無緊急信號",
    "{tk} 集中度": "{tk} 集中度",
    "跳到": "跳到",
    "跌到": "跌到",
    "隔夜 VIX {v} {verb} {p} ({c}%)": "隔夜 VIX {v} {verb} {p} ({c}%)",
    "VIX 跳涨 {pct}% 至 {v}": "VIX 跳漲 {pct}% 至 {v}",
    "卖权利金窗口期，扫一眼推荐": "賣權利金窗口期，掃一眼推薦",
    "{label} 进入 ITM": "{label} 進入 ITM",
    "昨天还安全，今天突破行权 — 留意指派": "昨天還安全，今天突破行權 — 留意指派",
    "{tk} {d} 天后财报，{label} 跨越": "{tk} {d} 天後財報，{label} 跨越",
    "留意 IV crush 风险": "留意 IV crush 風險",
    "昨天 {yp}%，突破 80% — 可考虑锁利": "昨天 {yp}%，突破 80% — 可考慮鎖利",
    "{label} 剩 {d} 天到期": "{label} 剩 {d} 天到期",
    "进入 7 天到期窗口，准备处理": "進入 7 天到期窗口，準備處理",
    "接近锁利窗口": "接近鎖利窗口",
    "{label} 距行权仅 {pct}%": "{label} 距行權僅 {pct}%",
    "gamma 风险大": "gamma 風險大",
    "剩 {d} 天": "剩 {d} 天",
    "浮亏 ${pnl}": "浮虧 ${pnl}",
    "考虑买回 / roll": "考慮買回 / roll",
    "盯紧，考虑止损": "盯緊，考慮止損",
    "浮盈 ${pnl} · 剩 {d} 天 · 接近锁利窗口": "浮盈 ${pnl} · 剩 {d} 天 · 接近鎖利窗口",
    "{tk} 新闻: {title}": "{tk} 新聞: {title}",
    "{pub} · {h}h 前": "{pub} · {h}h 前",
    "看持仓 →": "看持倉 →",
    "看推荐 →": "看推薦 →",
    "看持仓": "看持倉",
    "看推荐": "看推薦",
    "看原文": "看原文",
    "📅 未来 14 天关键日": "📅 未來 14 天關鍵日",
    "财报": "財報",
    "持仓到期": "持倉到期",
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
    if S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0, 0.0
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
    if S <= 0 or K <= 0:
        return max(K - max(S, 0.0), 0.0), 0.0, 0.0, 0.0
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
    """实时价 + 前收盘 — 并行 yfinance fast_info（per ticker ~500ms IO）"""
    out: Dict[str, Dict] = {}
    try:
        import yfinance as yf
    except ImportError:
        return {tk: {"price": 0.0, "prev": 0.0} for tk in set(tickers)}

    session = _get_yf_session()
    todo: List[str] = []
    for tk in set(tickers):
        if tk in _cache_prices:
            out[tk] = _cache_prices[tk]
        else:
            todo.append(tk)
    if not todo:
        return out

    def _one(tk: str) -> Tuple[str, Dict]:
        try:
            ticker_obj = yf.Ticker(tk, session=session) if session else yf.Ticker(tk)
            fi = ticker_obj.fast_info
            return tk, {"price": float(fi.last_price), "prev": float(fi.previous_close)}
        except Exception:
            return tk, {"price": 0.0, "prev": 0.0}

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
        for tk, quote in ex.map(_one, todo):
            out[tk] = quote
            if quote["price"] > 0:
                _cache_prices[tk] = quote
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


# ── Usage tracking (Supabase usage_events) ─────────────────────────
# 用 service_role 直写 Supabase REST，绕过 RLS。前端发 user_id/email，
# 服务端再加上推荐返回的元数据。任何失败都吞掉，不影响主请求。
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://nvavwcvxmzksadpbtafs.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "sb_publishable_hPltd-pP9xhaHKcd1jQO2w_91xAABws",  # 与 index.html 中 publishable key 一致
)
ADMIN_EMAIL_WHITELIST = {"hi@congyangwang.com", "avatar.wang@gmail.com"}

# 初始 coin 额度（per user）
COIN_INITIAL_GRANT = 1000


def _supabase_request(method, path, body=None, params=None, use_service_role=True, timeout=8):
    """通用 Supabase REST 调用。返回 (status, json|text)。失败抛异常。"""
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY
    if not key:
        raise RuntimeError("missing supabase key")
    url = SUPABASE_URL.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    data_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else None
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else None
        except Exception:
            return e.code, raw


def log_usage_event(user_id, user_email, event, metadata=None):
    """埋点入口。任何失败安静吞掉。"""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return  # 没配 key 就 noop，不影响主流程
    try:
        row = {
            "user_id": user_id or None,
            "user_email": (user_email or None),
            "event": str(event),
            "metadata": metadata or {},
        }
        # 2s timeout — usage 埋点不该把主请求拖久。Supabase 抖动时尽快放弃。
        _supabase_request("POST", "/rest/v1/usage_events", body=row, timeout=2)
    except Exception as e:
        try:
            print(f"[usage] log fail: {type(e).__name__}: {e}", flush=True)
        except Exception:
            pass


def _verify_admin_token(access_token):
    """用 Supabase /auth/v1/user 验 JWT，返回 (ok, email|err_msg)。"""
    if not access_token:
        return False, "missing token"
    url = SUPABASE_URL.rstrip("/") + "/auth/v1/user"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token}",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        email = (data.get("email") or "").lower().strip()
        if email in ADMIN_EMAIL_WHITELIST:
            return True, email
        return False, f"not whitelisted: {email}"
    except urllib.error.HTTPError as e:
        return False, f"auth/v1/user HTTP {e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def admin_stats(payload):
    """白名单管理员看用量。需要 access_token；服务端验 JWT。"""
    ok, info = _verify_admin_token(payload.get("access_token"))
    if not ok:
        return {"error": "unauthorized", "reason": info}
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"error": "missing SUPABASE_SERVICE_ROLE_KEY env"}

    # 拉最近 5000 行做内存聚合（量级足够撑相当长时间）
    limit = int(payload.get("limit", 5000))
    status, rows = _supabase_request(
        "GET", "/rest/v1/usage_events",
        params={
            "select": "id,user_id,user_email,event,metadata,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    if status >= 400 or not isinstance(rows, list):
        return {"error": f"supabase {status}", "detail": rows}

    from collections import Counter, defaultdict
    now = datetime.utcnow()
    win_24h = now - timedelta(hours=24)
    win_7d = now - timedelta(days=7)
    win_30d = now - timedelta(days=30)

    by_event_total = Counter()
    by_event_24h = Counter()
    by_event_7d = Counter()
    by_user = defaultdict(lambda: {"email": None, "total": 0, "last": None, "by_event": Counter()})
    by_day = defaultdict(int)         # YYYY-MM-DD → 总事件数
    by_day_recommend = defaultdict(int)
    rec_ok = 0
    rec_fail = 0
    fail_codes = Counter()
    goal_counter = Counter()
    risk_counter = Counter()
    tier_counter = Counter()
    candidates_buckets = Counter()

    for r in rows:
        ev = r.get("event") or ""
        uid = r.get("user_id") or "anon"
        email = r.get("user_email")
        meta = r.get("metadata") or {}
        ts_str = r.get("created_at") or ""
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            ts = now

        by_event_total[ev] += 1
        if ts >= win_24h:
            by_event_24h[ev] += 1
        if ts >= win_7d:
            by_event_7d[ev] += 1

        u = by_user[uid]
        if email:
            u["email"] = email
        u["total"] += 1
        u["by_event"][ev] += 1
        if u["last"] is None or ts > u["last"]:
            u["last"] = ts

        day = ts.strftime("%Y-%m-%d")
        if ts >= win_30d:
            by_day[day] += 1
            if ev == "recommend":
                by_day_recommend[day] += 1

        if ev == "recommend":
            if meta.get("ok") is True or meta.get("ok") == "true":
                rec_ok += 1
            elif meta.get("ok") is False or meta.get("error_kind"):
                rec_fail += 1
                code = meta.get("error_kind") or meta.get("error") or "unknown"
                fail_codes[str(code)[:40]] += 1
            if meta.get("goal"):
                goal_counter[str(meta["goal"])] += 1
            if meta.get("risk"):
                risk_counter[str(meta["risk"])] += 1
            if meta.get("top_tier") is not None:
                tier_counter[f"tier_{meta['top_tier']}"] += 1
            n = meta.get("candidates_n")
            if isinstance(n, (int, float)):
                if n == 0: candidates_buckets["0"] += 1
                elif n <= 3: candidates_buckets["1-3"] += 1
                elif n <= 7: candidates_buckets["4-7"] += 1
                else: candidates_buckets["8+"] += 1

    top_users = sorted(
        ({
            "user_id": uid,
            "email": u["email"],
            "total": u["total"],
            "last_seen": u["last"].isoformat() if u["last"] else None,
            "by_event": dict(u["by_event"]),
         } for uid, u in by_user.items()),
        key=lambda x: -x["total"],
    )[:25]

    return {
        "ok": True,
        "as_of": now.isoformat() + "Z",
        "sampled_rows": len(rows),
        "sample_limit_hit": len(rows) >= limit,
        "totals": {
            "all_time_in_sample": sum(by_event_total.values()),
            "last_24h": sum(by_event_24h.values()),
            "last_7d": sum(by_event_7d.values()),
            "unique_users_in_sample": len(by_user),
        },
        "by_event": {
            "total": dict(by_event_total),
            "last_24h": dict(by_event_24h),
            "last_7d": dict(by_event_7d),
        },
        "top_users": top_users,
        "by_day_30d": sorted(({"day": k, "total": v, "recommend": by_day_recommend.get(k, 0)}
                              for k, v in by_day.items()),
                             key=lambda x: x["day"]),
        "recommend_health": {
            "ok": rec_ok,
            "fail": rec_fail,
            "fail_codes": dict(fail_codes.most_common(10)),
            "by_goal": dict(goal_counter),
            "by_risk": dict(risk_counter),
            "by_top_tier": dict(tier_counter),
            "candidates_buckets": dict(candidates_buckets),
        },
    }


def _count_usage_event(user_id: str, event: str, key: str) -> int:
    """Supabase HEAD count 单事件次数。失败返回 0。"""
    url = (SUPABASE_URL.rstrip("/") + "/rest/v1/usage_events"
           + "?" + urllib.parse.urlencode({
                "select": "id",
                "user_id": f"eq.{user_id}",
                "event": f"eq.{event}",
           }))
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Prefer": "count=exact",
        "Range-Unit": "items",
        "Range": "0-0",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=6) as resp:
        cr = resp.headers.get("Content-Range") or ""
        if "/" in cr:
            tail = cr.split("/", 1)[1].strip()
            if tail.isdigit():
                return int(tail)
    return 0


def get_coin_balance(payload):
    """返回某用户当前 coin 余额。用 Supabase count head 算 used。
    扣费规则：recommend × 1 + brief_refresh × 5。
    不做 JWT 验证（低风险只读，最多被人探测某用户用了多少次）。"""
    user_id = (payload.get("user_id") or "").strip()
    if not user_id:
        return {"error": "missing user_id"}
    if not SUPABASE_SERVICE_ROLE_KEY:
        # 没配 service role 就退化为"满额"，不阻塞前端
        return {"ok": True, "total": COIN_INITIAL_GRANT, "used": 0,
                "remaining": COIN_INITIAL_GRANT, "note": "service_role missing"}
    key = SUPABASE_SERVICE_ROLE_KEY
    try:
        recommend_count = _count_usage_event(user_id, "recommend", key)
        brief_count = _count_usage_event(user_id, "brief_refresh", key)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    used = recommend_count + 5 * brief_count
    remaining = max(0, COIN_INITIAL_GRANT - used)
    return {
        "ok": True,
        "total": COIN_INITIAL_GRANT,
        "used": used,
        "used_recommend": recommend_count,
        "used_brief_refresh": brief_count,
        "remaining": remaining,
    }


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


def _fmt_strike(s):
    # 整数 strike 输出 "100"，小数 strike 输出 "100.5"；前后端必须产出同一字符串
    f = float(s)
    return str(int(f)) if f == int(f) else str(f)


def position_id(p):
    return f"{p['ticker']}_{p['type']}_{_fmt_strike(p['strike'])}_{p['expiry'].isoformat()}"


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
def portfolio_history(positions, state, prices, today, enriched=None):
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

    # 所有交易日 — 并行 fetch_history (yfinance per ticker IO)
    hist_tickers = list(set(p["ticker"] for p in positions))
    all_days = set()
    if hist_tickers:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(hist_tickers))) as ex:
            results = ex.map(lambda tk: fetch_history(tk, earliest - timedelta(days=5)),
                             hist_tickers)
            for h in results:
                all_days.update(h.keys())
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

    # 今日实时点 — 优先用 enriched（来自实时期权报价，与 hero P&L 同源）；
    # 没有 enriched 才走 BS 模型 fallback，避免和顶部 hero 数字对不上。
    today_str = today.isoformat()
    today_pnl = today_sold = 0.0
    today_per_pos = {}
    if enriched is not None:
        for e in enriched:
            # enriched 里 trade_date 是 isoformat 字符串
            if today < date.fromisoformat(e["trade_date"]): continue
            today_pnl += e["pnl"]
            today_sold += e["sold"]
            today_per_pos[e["id"]] = e["pnl"]
    else:
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


def position_advice(ps, lang: str = "zh", exit_style: str = "early_close"):
    """持仓侧栏"操作建议"卡片 — 按用户的 exit_style 用 4 触发线（包租公式）评估。

    跟 _exit_plan 的 4 触发线一一对应：
      1. 早收租 profit target — 50%（hold_to_expiry 停用）
      2. DTE 换租 — 21 天阈值（hold_to_expiry 停用，wheel_assign 改"盈利时关"）
      3. 房客违约 — |Δ| 阈值，早收租 0.30 / Wheel 0.45 / 死磕 dim
      4. 红线 — 财报跨期 / 占金超阈
    显示"你离哪条线最近"，最紧迫的状态决定 severity + status。
    """
    days = ps["days"]
    if days < 0 or ps["closed"]:
        return None
    is_call = ps["type"] == "call"
    pnl, pnl_pct = ps["pnl"], ps["pnl_pct"]
    money = ps["moneyness"]
    underlying, strike, mark = ps["underlying"], ps["strike"], ps["mark"]
    delta_abs = abs(float(ps.get("delta") or 0.0))
    shares = ps["contracts"] * 100
    buyback_total = mark * shares

    # 风格阈值
    delta_th = {"early_close": 0.30, "wheel_assign": 0.45, "hold_to_expiry": None}[exit_style]
    profit_th = None if exit_style == "hold_to_expiry" else 50
    dte_th = None if exit_style == "hold_to_expiry" else 21
    style_emoji = {"early_close": "🏠", "wheel_assign": "🏘️", "hold_to_expiry": "💰"}[exit_style]
    style_name = _T(lang, {
        "early_close": "早收租派", "wheel_assign": "接货 Wheel", "hold_to_expiry": "死磕到期"
    }[exit_style])

    facts, actions = [], []
    severity = "good"
    status = _T(lang, "🟢 持仓健康 · {emoji} {style}", emoji=style_emoji, style=style_name)

    # 基础事实行
    is_otm = (is_call and money > 0) or ((not is_call) and money < 0)
    money_label = _T(lang, "OTM 安全区") if is_otm else _T(lang, "ITM 风险区")
    facts.append(_T(lang, "{tk} 现价 ${px}，行权价 ${k}（距 {money}%，{label}）",
                    tk=ps['ticker'], px=f"{underlying:.2f}", k=f"{strike:.0f}",
                    money=f"{money:+.1f}", label=money_label))
    facts.append(_T(lang, "剩余 {days} 天 · {n} 张 · 现在买回 ${bb} · 浮盈亏 {pct}%",
                    days=days, n=ps['contracts'], bb=f"{buyback_total:,.0f}",
                    pct=f"{pnl_pct:+.1f}"))
    facts.append(_T(lang, "|Δ| {d}（风格违约线 {th}）",
                    d=f"{delta_abs:.2f}",
                    th=(f"{delta_th:.2f}" if delta_th is not None else _T(lang, "停用"))))

    pnl_amt = abs(pnl)
    buy_back_action = _T(lang, "立即买回 ${bb}（{verb} ${amt}）",
                          bb=f"{buyback_total:,.0f}",
                          verb=_T(lang, "锁利") if pnl >= 0 else _T(lang, "止损"),
                          amt=f"{pnl_amt:,.0f}")

    # 触发线优先级：红线 > 房客违约 > 21天换租 > 早收租 > 死磕状态
    triggered = []  # 用于记录已触发的触发线（影响 status）

    # ── 触发线 4：红线（财报跨期 / 必出）
    if ps.get("earnings_before_expiry"):
        eud = ps.get("earnings_days_until")
        if eud is not None and eud >= 0:
            severity = _max_sev(severity, "danger")
            status = _T(lang, "🚨 红线触发 · 财报跨期")
            facts.append(_T(lang,
                "🚨 {date} 财报（剩 {n} 天）在到期前 — 红线 · 立即买回，不接货",
                date=ps["earnings_date"], n=eud))
            earn_action = _T(lang, "立即买回 ${bb}（避免财报 gap）", bb=f"{buyback_total:,.0f}")
            if earn_action not in actions:
                actions.insert(0, earn_action)
            triggered.append("red")

    # ── 触发线 3：房客违约（|Δ| 阈值）
    if delta_th is not None and delta_abs >= delta_th:
        severity = _max_sev(severity, "danger")
        if "red" not in triggered:
            status = _T(lang, "⚠️ 房客违约触发 · {emoji} {style}",
                        emoji=style_emoji, style=style_name)
        facts.append(_T(lang,
            "⚠️ |Δ| {d} ≥ {th}（{style} 风格违约线）— Δ 是接货真风险，已亮起",
            d=f"{delta_abs:.2f}", th=f"{delta_th:.2f}", style=style_name))
        if exit_style == "early_close":
            for ac in [_T(lang, "Roll 到下月（保持收租，不接货）"),
                       _T(lang, "止损平仓 ${bb}（亏 ${amt}）",
                          bb=f"{buyback_total:,.0f}", amt=f"{pnl_amt:,.0f}")]:
                if ac not in actions: actions.append(ac)
        else:  # wheel_assign
            for ac in [_T(lang, "Roll 到下月 / 接货转 CC（Wheel 阶段二）"),
                       buy_back_action]:
                if ac not in actions: actions.append(ac)
        triggered.append("breach")

    # ── 触发线 2：21 天换租（DTE 强制关闭线）
    if dte_th is not None and 0 < days <= dte_th and "red" not in triggered and "breach" not in triggered:
        severity = _max_sev(severity, "warn")
        status = _T(lang, "⏱️ 21 天换租线 · {emoji} {style}",
                    emoji=style_emoji, style=style_name)
        if exit_style == "wheel_assign":
            facts.append(_T(lang,
                "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 经验）— Wheel 派：盈利则关，亏损接货",
                n=days, th=dte_th))
            if pnl_pct >= 0:
                actions.append(_T(lang, "盈利状态 → 买回 ${bb} 锁 ${pnl}",
                                  bb=f"{buyback_total:,.0f}", pnl=f"{pnl:,.0f}"))
            else:
                actions.append(_T(lang, "亏损状态 → 持到 expire 接货（Wheel 阶段二）"))
        else:  # early_close
            facts.append(_T(lang,
                "⏱️ 剩 {n} 天 ≤ {th} 天（Tasty 21d 经验）— 强制平仓，不论盈亏",
                n=days, th=dte_th))
            actions.append(_T(lang, "强制买回 ${bb}（gamma 风险不值剩余 theta）",
                              bb=f"{buyback_total:,.0f}"))
        triggered.append("dte")

    # ── 触发线 1：早收租（profit target）
    if profit_th is not None and pnl_pct >= profit_th and "red" not in triggered:
        if not triggered:
            status = _T(lang, "📬 早收租达成 · {emoji} {style}",
                        emoji=style_emoji, style=style_name)
            severity = _max_sev(severity, "good")
        facts.append(_T(lang, "📬 已达 {pct}% ≥ 锁利目标 {th}% — 早收租触发",
                        pct=f"{pnl_pct:.0f}", th=profit_th))
        ac = _T(lang, "买回 ${px}/股 锁利 ${pnl}", px=f"{mark:.2f}", pnl=f"{pnl:,.0f}")
        if ac not in actions: actions.insert(0, ac)
        triggered.append("profit")

    # ── 死磕状态（hold_to_expiry 且无触发）
    if exit_style == "hold_to_expiry" and not triggered:
        status = _T(lang, "💰 死磕到期 · 等 {n} 天 expire", n=days)
        facts.append(_T(lang, "持到 expire 吃满 ${sold}（OTM 归零最爽）",
                        sold=f"{ps.get('sold', 0):,.0f}"))
        if not is_otm:
            actions.append(_T(lang, "ITM 状态 — 准备接货 ${cash}（{n} 股）",
                              cash=f"{strike * shares:,.0f}", n=shares))
        else:
            actions.append(_T(lang, "OTM 状态 — 等 expire 自动归零"))

    # ── 离最近触发线还差多少（默认状态：未触发任何触发线）
    if not triggered and exit_style != "hold_to_expiry":
        gaps = []
        if profit_th is not None and pnl_pct < profit_th:
            gaps.append((profit_th - pnl_pct, _T(lang,
                "📬 离 {th}% 锁利还差 {gap}%（当前 {cur}%）",
                th=profit_th, gap=f"{max(0, profit_th - pnl_pct):.0f}",
                cur=f"{pnl_pct:.0f}")))
        if delta_th is not None and delta_abs < delta_th:
            gaps.append(((delta_th - delta_abs) * 100, _T(lang,
                "⚠️ 离 |Δ| {th} 违约线还差 {gap}（当前 {cur}）",
                th=f"{delta_th:.2f}", gap=f"{delta_th - delta_abs:.2f}",
                cur=f"{delta_abs:.2f}")))
        if dte_th is not None and days > dte_th:
            gaps.append((days - dte_th, _T(lang,
                "⏱️ 离 21 天换租线还差 {gap} 天（当前 {cur} 天）",
                gap=days - dte_th, cur=days)))
        gaps.sort(key=lambda x: x[0])  # 越接近触发越靠前
        if gaps:
            facts.append(gaps[0][1])
        actions.append(_T(lang, "持续监控 · 让 theta 累积收益") if pnl_pct >= 0
                       else _T(lang, "持续监控 · 等时间衰减"))

    # 严重亏损补提示
    if pnl_pct < -50 and "breach" not in triggered:
        severity = _max_sev(severity, "danger")
        facts.append(_T(lang, "📉 浮亏 ${amt}（> 50% 权利金，关注 Δ 是否同步上升）",
                        amt=f"{pnl_amt:,.0f}"))

    if not actions:
        actions.append(_T(lang, "持续监控"))

    return {
        "position_id": ps["id"], "label": ps["label"],
        "subtitle": _T(lang, "Exp {exp} · {n} 张 · 剩 {d} 天 · {emoji} {style}",
                       exp=ps['expiry'], n=ps['contracts'], d=days,
                       emoji=style_emoji, style=style_name),
        "type": severity, "status": status,
        "pnl": pnl, "pnl_pct": pnl_pct,
        "facts": facts, "actions": actions,
        "exit_style": exit_style,
    }


def get_suggestions(positions, lang: str = "zh", exit_style: str = "early_close"):
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

    # 集中度提示（中性化：集中是策略选择不是 bug，不再用 danger 红，只在极端时提）
    if top_concentration >= 60 and len(ticker_exposure) >= 2:
        if top_concentration >= 90:
            sev = "warn"
            status = _T(lang, "⚠️ 单点集中 · {tk} 占 {pct}%", tk=top_ticker, pct=f"{top_concentration:.0f}")
            advice = _T(lang, "几乎全部押在一个标的。这是你的策略选择 — 留意单点风险（大跌、IV 飙、财报暴雷）就行。")
        elif top_concentration >= 75:
            sev = "caution"
            status = _T(lang, "💡 高度集中 · {tk} 占 {pct}%", tk=top_ticker, pct=f"{top_concentration:.0f}")
            advice = _T(lang, "超过七成在一个标的。包租公没有标准答案 — 集中收得多，分散更抗黑天鹅，看你的偏好。")
        else:
            sev = "info"
            status = _T(lang, "🏘 集中度 · {tk} 占 {pct}%", tk=top_ticker, pct=f"{top_concentration:.0f}")
            advice = _T(lang, "六到七成在单一标的。属于偏集中的策略，因人而异 — 看你的资金体量与投资目标。")
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
                _T(lang, "💡 集中是策略选择，不是 bug — 关键看你能不能扛单点波动。"),
            ],
            "actions": [],
        })

    for ps in positions:
        adv = position_advice(ps, lang=lang, exit_style=exit_style)
        if adv: cards.append(adv)
    return cards


# ── 主计算入口 ────────────────────────────────────────────────────────────────
def compute(payload):
    positions_raw = payload.get("positions", [])
    state = payload.get("state", {})
    lang = payload.get("lang", "zh")
    exit_style = payload.get("exit_style") or "early_close"
    brief_refresh = bool(payload.get("brief_refresh"))
    # alias 旧值（兼容老 localStorage）
    exit_style = {"auto": "early_close", "wheel_purist": "hold_to_expiry"}.get(exit_style, exit_style)
    if exit_style not in ("early_close", "wheel_assign", "hold_to_expiry"):
        exit_style = "early_close"

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
    today = date.today()
    earliest = min(p["trade_date"] for p in positions) - timedelta(days=5)

    # 并行启动 prices + intraday — 两个都是 yfinance 串行 IO，独立无依赖
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(2, min(8, len(tickers)))) as ex:
        prices_fut = ex.submit(fetch_prices, tickers)
        intraday_futs = {tk: ex.submit(fetch_intraday, tk) for tk in tickers}
        prices = prices_fut.result()
        intraday = {tk: fut.result() for tk, fut in intraday_futs.items()}

    # Prefetch option chains for all active positions in parallel — so the
    # serial position_state loop below hits cache for every fetch_option_quote.
    # Without this, N positions = N serial Schwab/yfinance chain calls.
    active_chains = set()
    for p in positions:
        pid = position_id(p)
        if state.get(pid, {}).get("closed"):
            continue
        if (p["expiry"] - today).days <= 0:
            continue
        active_chains.add((p["ticker"], p["expiry"].isoformat()))
    if active_chains:
        with ThreadPoolExecutor(max_workers=min(8, len(active_chains))) as ex:
            list(ex.map(lambda args: fetch_chain(*args), active_chains))

    enriched = [position_state(p, today, state, prices, earliest) for p in positions]
    history = portfolio_history(positions, state, prices, today, enriched=enriched)
    suggestions = get_suggestions(enriched, lang=lang, exit_style=exit_style)

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

    morning_brief = _generate_morning_brief(
        enriched, prices,
        total_pnl - total_realized, total_realized, total_theta,
        state=state, lang=lang, force_refresh=brief_refresh,
    )

    # brief_refresh_charged: 仅当用户请求 brief_refresh 且本次真的走了 LLM（不是 cache / template
    # 兜底）才扣 5 金币。前端用这个判断 deduct，后端 handler 用它写 brief_refresh usage event。
    brief_refresh_charged = bool(
        brief_refresh and morning_brief and morning_brief.get("generated_by") == "llm"
    )

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
        "brief_refresh_charged": brief_refresh_charged,
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
                       is_short_put: bool = True,
                       exit_style: str = "early_close") -> Optional[dict]:
    """
    历史回测（POP 校准版 v2.0，跟 exit_plan 路径触发同步）：

    - 拉过去 12 个月日线（不够 6 月），每 3 天采样
    - 用 BS 反推 strike（|Δ(K)| ≈ delta_target），BS 算 premium
    - **v2.0：按 exit_style 路径模拟**
      - early_close / wheel_assign：日内重新定价，**当 premium 衰减到 50%
        就早平**；DTE 剩余 ≤ cutoff（30%/20% of orig DTE）也强制平
      - hold_to_expiry：照旧持到到期
    - 同时输出经验胜率 (win_rate) + 理论 POP + calibration_ratio
    - 新增 `early_close_rate`：路径模拟里多少 % 通过早平退场（vs 到期）
    """
    try:
        import yfinance as yf
        session = _get_yf_session()
        ticker_obj = yf.Ticker(ticker, session=session) if session else yf.Ticker(ticker)
        hist = ticker_obj.history(period="1y", interval="1d", auto_adjust=True)
        closes = hist["Close"].dropna().tolist()
        if len(closes) < 60:
            hist = ticker_obj.history(period="6mo", interval="1d", auto_adjust=True)
            closes = hist["Close"].dropna().tolist()
        if len(closes) < 60:
            return None

        wins, losses = 0, 0
        total_pnl_pct = 0.0
        total_theo_pop = 0.0
        early_closes = 0   # 多少次走早平
        sample_dte = max(3, min(sample_dte, 60))
        is_call = not is_short_put

        # 路径触发参数（仅 early_close / wheel_assign 启用）
        path_sim = exit_style in ("early_close", "wheel_assign")
        target_decay = 0.50  # premium 衰减到 entry × 50% → 早平
        if exit_style == "wheel_assign":
            dte_cutoff = max(5, int(sample_dte * 0.20))
        else:  # early_close
            dte_cutoff = max(7, int(sample_dte * 0.30))

        for i in range(20, len(closes) - sample_dte, 3):
            S = closes[i]
            rets = [math.log(closes[j] / closes[j-1]) for j in range(i-19, i+1)]
            mean = sum(rets) / len(rets)
            rv = math.sqrt(sum((r - mean) ** 2 for r in rets) / 19 * 252)
            if rv <= 0 or rv > 3:
                continue
            T = sample_dte / 365.0
            K = _strike_for_delta(S, T, rv, delta_target, is_call)
            if K is None or K <= 0:
                continue
            premium, _, _, _ = price_option(S, K, T, RISK_FREE, rv, is_call)
            if premium <= 0:
                continue
            try:
                d2 = (math.log(S / K) + (RISK_FREE - 0.5 * rv * rv) * T) / (rv * math.sqrt(T))
            except (ValueError, ZeroDivisionError):
                continue
            theo_pop = _ncdf(-d2) if is_call else _ncdf(d2)
            total_theo_pop += theo_pop

            # ── 路径模拟（仅 path_sim 时启用日内步进）
            exit_premium = None  # set if early-closed
            exit_day = None
            if path_sim:
                for d_offset in range(1, sample_dte):
                    T_remaining = (sample_dte - d_offset) / 365.0
                    if T_remaining <= 0:
                        break
                    S_t = closes[i + d_offset]
                    P_t, _, _, _ = price_option(S_t, K, T_remaining, RISK_FREE, rv, is_call)
                    if P_t <= 0:
                        continue
                    # 50% 早平
                    if P_t <= premium * target_decay:
                        exit_premium = P_t
                        exit_day = d_offset
                        break
                    # DTE cutoff（无论盈亏强制平 — early_close；wheel_assign 仅盈利时）
                    dte_remaining = sample_dte - d_offset
                    if dte_cutoff > 0 and dte_remaining <= dte_cutoff:
                        if exit_style == "wheel_assign" and P_t >= premium:
                            # wheel_assign 仅在盈利时强制 cutoff
                            continue
                        exit_premium = P_t
                        exit_day = d_offset
                        break

            # ── 计算 PnL
            if exit_premium is not None:
                # 早平：(entry - exit) per share
                pnl = (premium - exit_premium) / S
                early_closes += 1
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
            else:
                # 持到到期
                S_exp = closes[i + sample_dte]
                if is_short_put:
                    if S_exp >= K:
                        pnl = premium / S
                        wins += 1
                    else:
                        pnl = (premium - (K - S_exp)) / S
                        losses += 1
                else:
                    if S_exp <= K:
                        pnl = premium / S
                        wins += 1
                    else:
                        pnl = (premium - (S_exp - K)) / S
                        losses += 1
            total_pnl_pct += pnl

        n = wins + losses
        if n < 5:
            return None
        win_rate = wins / n * 100
        theo_pop_avg = total_theo_pop / n * 100
        calibration = (win_rate / theo_pop_avg) if theo_pop_avg > 0 else None
        early_rate = (early_closes / n * 100) if path_sim else None
        return {
            "win_rate": round(win_rate, 0),
            "avg_pnl_pct": round(total_pnl_pct / n * 100, 1),
            "n_trades": n,
            "theoretical_pop": round(theo_pop_avg, 0),
            "calibration_ratio": round(calibration, 2) if calibration else None,
            "window_months": 12 if len(closes) >= 220 else 6,
            "exit_style": exit_style,
            "early_close_rate": round(early_rate, 0) if early_rate is not None else None,
        }
    except Exception:
        return None


def _strike_for_delta(S: float, T: float, sigma: float, delta_target: float,
                      is_call: bool, max_iter: int = 30) -> Optional[float]:
    """
    给定 S, T, σ，二分反推 K 让 |Δ(K)| ≈ delta_target（短 call/put）。
    Short call delta 取值 0..1（实际 BS call Δ），短 put delta 取 |-Δ| 即 0..1。
    """
    if S <= 0 or T <= 0 or sigma <= 0 or delta_target <= 0 or delta_target >= 1:
        return None
    # call: K 越大 Δ 越小；put: K 越小 |Δ| 越小
    lo, hi = S * 0.3, S * 3.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        _, delta_mid, _, _ = price_option(S, mid, T, RISK_FREE, sigma, is_call)
        d = abs(delta_mid)
        if abs(d - delta_target) < 0.005:
            return mid
        if is_call:
            # call Δ 随 K↑ 而↓
            if d > delta_target:
                lo = mid
            else:
                hi = mid
        else:
            # put |Δ| 随 K↑ 而↑
            if d < delta_target:
                lo = mid
            else:
                hi = mid
    return (lo + hi) / 2


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
ALGORITHM_VERSION = "2.0"
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


def _dte_sweet_factor(days: int, target_days: int = None,
                       iv_rank_pct: Optional[float] = None) -> float:
    """
    DTE 甜蜜区加成：以 target_days 为中心，半宽随 target 自适应。
    target_days=None 时回退到 14 天固定峰值（兼容旧调用）。

    v2.0 新增 iv_rank_pct：IV 高时甜蜜区向短 DTE 滑（捕 IV crush 更快），
    IV 低时向长 DTE 滑（拉长 theta 收割期）。
      iv_rank ≥ 70：target 实际中心 × 0.70（往短走 30%）
      iv_rank ≤ 30：target 实际中心 × 1.30（往长走 30%）
      30-70：不动

    Returns 0.5 ~ 1.2 multiplier.
    """
    if days <= 0:
        return 0.5

    # IV-adaptive shift
    effective_target = target_days
    if effective_target and iv_rank_pct is not None:
        if iv_rank_pct >= 70:
            effective_target = max(5, int(round(effective_target * 0.70)))
        elif iv_rank_pct <= 30:
            effective_target = int(round(effective_target * 1.30))

    if not effective_target or effective_target <= 0:
        # 兼容路径：旧固定甜蜜区
        if days < 5:
            return 0.65 + 0.07 * days
        if days <= 21:
            return 1.0 + 0.2 * max(0, 1 - abs(days - 14) / 7)
        if days <= 35:
            return 1.0 - (days - 21) / 28
        return 0.5

    # 半宽：短 timeframe 用绝对值（≥5），长 timeframe 用百分比
    half_width = max(5.0, effective_target * 0.35)
    offset = abs(days - effective_target)

    if offset <= half_width:
        # 区内：1.0 - 1.2，距 target 越近越甜
        return round(1.0 + 0.20 * (1 - offset / half_width), 3)

    # 区外：线性衰减到 0.5（超出 2× half_width 之外彻底压到 0.5）
    excess = offset - half_width
    if excess >= half_width:
        return 0.5
    return round(1.0 - 0.5 * (excess / half_width), 3)


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


def _portfolio_context(ticker: str, underlying: float,
                        option_positions: list, avail_margin: float) -> Optional[dict]:
    """透明度面板：同 ticker 敞口 + -15% 情景。不影响 score，只展示数字。

    用户的库存里所有期权都是"卖出"立场（包租公定位）。这里聚合 same-ticker：
      - put 累计 collateral（被同时指派需要的现金）
      - -15% 单日情景下：还有几张 OTM put 会进入 ITM，累计 intrinsic loss
    """
    same = [p for p in (option_positions or [])
            if (p.get("ticker") or "").upper() == ticker.upper()
            and not p.get("closed")]
    if not same:
        return None

    puts = [p for p in same if p.get("type") == "put"]
    calls = [p for p in same if p.get("type") == "call"]

    put_collateral = sum(
        float(p.get("strike", 0) or 0) * 100 * int(p.get("contracts", 0) or 0)
        for p in puts
    )
    put_contracts = sum(int(p.get("contracts", 0) or 0) for p in puts)
    call_contracts = sum(int(p.get("contracts", 0) or 0) for p in calls)

    shock = 0.15
    stressed_price = underlying * (1 - shock)
    n_itm = sum(1 for p in puts if float(p.get("strike", 0) or 0) > stressed_price)

    # 浮亏估算：-15% 后 puts 的 intrinsic value 总和（保守上限，未扣已收权利金、未计时间价值）
    stress_loss = sum(
        max(0.0, float(p.get("strike", 0) or 0) - stressed_price) * 100 * int(p.get("contracts", 0) or 0)
        for p in puts
    )

    out = {
        "shock_pct": int(shock * 100),
        "stressed_price": round(stressed_price, 2),
        "put_contracts": put_contracts,
        "call_contracts": call_contracts,
        "put_collateral": round(put_collateral, 0),
        "puts_itm_at_shock": n_itm,
        "stress_loss_estimate": round(stress_loss, 0),
    }
    if avail_margin > 0 and put_collateral > 0:
        out["put_collateral_pct"] = round(put_collateral / avail_margin * 100, 1)
    return out


def _adjust_delta_band_by_iv(base_band: tuple, iv_rank_pct: Optional[float]) -> tuple:
    """根据 IV rank 自适应调整 short premium 的 delta 区间。
    高 IV (≥70): 向远 OTM 移（同等权利金下更安全）。
    低 IV (≤30): 向 ATM 移（否则收不到像样的权利金）。
    中段不动。温和位移：区间宽度 × 0.30。
    """
    if iv_rank_pct is None:
        return base_band
    lo, hi = base_band
    width = hi - lo
    if iv_rank_pct >= 70:
        shift = width * 0.30
        return (max(0.05, round(lo - shift * 0.5, 3)),
                max(0.10, round(hi - shift, 3)))
    if iv_rank_pct <= 30:
        shift = width * 0.30
        return (round(lo + shift * 0.5, 3),
                min(0.55, round(hi + shift, 3)))
    return base_band


def _peek_atm_iv(ticker: str, exp_str: str, underlying: float) -> Optional[float]:
    """快速取一个 ATM 期权的 IV（年化，0-1），用于 IV rank 预估。
    chain 结构：{(strike, 'call'|'put'): {iv, ...}}。失败返回 None。"""
    try:
        chain = fetch_chain(ticker, exp_str)
        if not chain:
            return None
        best = None
        best_dist = float("inf")
        for (strike, _opt_type), q in chain.items():
            iv = q.get("iv", 0)
            if not strike or strike <= 0 or iv <= 0:
                continue
            dist = abs(strike - underlying)
            if dist < best_dist:
                best_dist = dist
                best = iv
        if best is None:
            return None
        # iv 可能是百分数或小数，统一归一化到小数
        return best / 100 if best > 3 else best
    except Exception:
        return None


def _compute_skew_signal(ticker: str, exp_str: str, underlying: float) -> Optional[dict]:
    """Put/Call IV skew 信号（包租公 1.4）。

    取最接近 underlying 的 ATM put / ATM call 的 IV，算 put_iv / call_iv 比值：
      ratio > 1.15  → put skew（市场为下跌付溢价）→ short put 卖 vol 有 edge
      ratio < 0.90  → call skew（市场为上涨付溢价）→ short call / Covered Call 有 edge
      其他 → 中性，无明显 vol edge

    仅作 transparency 提示，不进 score（rent_score 已经隐含吃了 IV）。"""
    try:
        chain = fetch_chain(ticker, exp_str)
        if not chain:
            return None
        best_put = (None, float("inf"))  # (iv, |strike-underlying|)
        best_call = (None, float("inf"))
        for (strike, opt_type), q in chain.items():
            iv = q.get("iv", 0)
            if not strike or strike <= 0 or iv <= 0:
                continue
            dist = abs(strike - underlying)
            if opt_type == "put" and dist < best_put[1]:
                best_put = (iv, dist)
            elif opt_type == "call" and dist < best_call[1]:
                best_call = (iv, dist)
        put_iv, call_iv = best_put[0], best_call[0]
        if not put_iv or not call_iv:
            return None
        # 归一化到小数
        put_iv = put_iv / 100 if put_iv > 3 else put_iv
        call_iv = call_iv / 100 if call_iv > 3 else call_iv
        if call_iv <= 0:
            return None
        ratio = put_iv / call_iv
        if ratio > 1.15:
            bias = "put_skew"
        elif ratio < 0.90:
            bias = "call_skew"
        else:
            bias = "neutral"
        return {
            "put_iv": round(put_iv * 100, 1),
            "call_iv": round(call_iv * 100, 1),
            "ratio": round(ratio, 3),
            "bias": bias,
            "expiry": exp_str,
        }
    except Exception:
        return None


def _margin_bpr(strike: float, underlying: float, is_call: bool, mid: float) -> float:
    """
    Reg-T 保证金账户 BPR（Buying Power Reduction）估算，裸卖期权。
    Short Put : max(20% × underlying - OTM_amount + mid, 10% × strike + mid) × 100
    Short Call: max(20% × underlying - OTM_amount + mid, 10% × underlying + mid) × 100
    Covered Call (is_covered=True): BPR ≈ 0（有正股托底，margin 不占用）
    """
    otm_amount = max(0.0, strike - underlying) if is_call else max(0.0, underlying - strike)
    m1 = 0.20 * underlying - otm_amount + mid
    m2 = (0.10 * underlying + mid) if is_call else (0.10 * strike + mid)
    return max(m1, m2) * 100


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


def _earnings_factor(days_to_earnings: int, risk: str, intent: str = "premium") -> float:
    """财报因子（包租公 1.3）：按意图区分财报的利弊。

    CSP / Covered Call：财报前 IV 高 = 更多权利金 = 优势，不是风险。
      保守派 ≤3 天：轻微警惕（极端 gap down 可能）；其余中性。

    Pure premium / long_vol：双向 gamma 风险，保持扣分逻辑。
    """
    if intent in ("csp", "covered_call"):
        if risk == "conservative" and days_to_earnings <= 3:
            return 0.75  # 极短期 gap down 风险，轻微警惕
        return 1.0  # IV 高是优势，中性处理

    # premium / long_vol / long_leaps — 双向风险，保持原逻辑
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


# ──────────────────────────────────────────────────────────────────────
# 包租公算法 2.0 — 新增辅助函数（杠杆 ETF / 已实现波动率 / 压力测试 / 资金占用）
# ──────────────────────────────────────────────────────────────────────

# 已知杠杆 ETF（2x / 3x bullish & bearish + 单股杠杆产品）。
# CSP 在杠杆 ETF 上有隐藏陷阱：被指派后波动率衰减让回本极慢。
LEVERAGED_ETF = {
    # 3x 指数 ETF (bullish)
    "TQQQ", "SOXL", "SPXL", "UDOW", "TNA", "FAS", "NUGT",
    "LABU", "DPST", "CURE", "FNGU", "DFEN", "BNKU", "ERX", "RETL",
    # 3x 指数 ETF (bearish / inverse)
    "SQQQ", "SOXS", "SPXU", "SDOW", "TZA", "FAZ", "LABD", "DUST",
    "DRV", "FNGD", "JDST", "DRIP", "ERY", "BERZ",
    # 2x ETF
    "QLD", "SSO", "DDM", "UWM", "ROM", "USD", "UYG", "AGQ", "UCO",
    "QID", "SDS", "DXD", "TWM", "SKF", "SCO", "ZSL", "REW", "SSG", "BIB", "BIS",
    # 单股 2x bullish (Direxion / GraniteShares / T-Rex / Tradr)
    "NVDL", "TSLL", "TSLR", "MSFU", "AAPB", "AMDL", "AMZU",
    "GGLL", "METU", "NFXL", "AVGX", "MUU", "PLTU", "CONL", "MSTX", "MSTU", "BITX", "ETHU",
    # 单股 inverse / bearish
    "NVDS", "NVDQ", "TSLZ", "TSDD", "TSLS", "MSFD", "AAPD", "AMDS",
    "AMZD", "GGLS", "METD", "NFXS", "MSTZ", "BITI",
}


def _is_leveraged_etf(ticker: str) -> bool:
    return (ticker or "").upper() in LEVERAGED_ETF


def _realized_vol(ticker: str, window: int = 30) -> Optional[float]:
    """过去 window 个交易日的年化已实现波动率（小数，0-1+）。
    用 yfinance 历史价 close-to-close 对数收益率，年化 × √252。
    数据不足或失败返回 None — 调用方需有 fallback。
    """
    try:
        # 多取一些日历日 buffer：window=30 实际取 ~50 日历日（去掉周末/假期）
        start = date.today() - timedelta(days=int(window * 1.7) + 10)
        hist = fetch_history(ticker, start)
        if not hist:
            return None
        sorted_dates = sorted(hist.keys())
        prices = [hist[d] for d in sorted_dates[-(window + 1):]]
        if len(prices) < 5:
            return None
        log_returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0 and prices[i] > 0:
                log_returns.append(math.log(prices[i] / prices[i - 1]))
        if len(log_returns) < 3:
            return None
        n = len(log_returns)
        mean = sum(log_returns) / n
        var = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
        sigma_daily = math.sqrt(var)
        return sigma_daily * math.sqrt(252)
    except Exception:
        return None


def _stress_test(opt: dict, underlying: float, iv_pct: float,
                  is_call: bool, is_short: bool) -> dict:
    """情景压力测试：标的明日朝不利方向移动 5% / 10%，叠加 IV pump。
    short put：不利 = 跌；short call：不利 = 涨。
    返回 dict {adverse_5pct: {...}, adverse_10pct: {...}}。
    mtm_pnl_$ 正数为浮盈、负数为浮亏（房东视角：option 价上涨我亏钱）。
    """
    if not is_short:
        return {}
    try:
        mid = float(opt.get("mid") or 0)
        days = int(opt.get("days") or 1)
        strike = float(opt.get("strike") or 0)
    except (TypeError, ValueError):
        return {}
    if mid <= 0 or days <= 0 or strike <= 0:
        return {}
    T_new = max(1, days - 1) / 365.0
    iv_dec = iv_pct / 100 if iv_pct > 3 else iv_pct
    if iv_dec <= 0:
        return {}
    # 不利方向：short put → -1（跌），short call → +1（涨）
    adverse_sign = +1 if is_call else -1
    out = {}
    for adverse_pct, iv_pump_pct in [(0.05, 0.15), (0.10, 0.30)]:
        S_new = max(0.01, underlying * (1 + adverse_sign * adverse_pct))
        iv_new = iv_dec * (1 + iv_pump_pct)
        try:
            new_price, new_delta, _, _ = price_option(
                S_new, strike, T_new, RISK_FREE, iv_new, is_call)
            # short PnL = -(new_price - mid) * 100，房东侧
            mtm_pnl_dollar = -(new_price - mid) * 100
            collateral = strike * 100
            out[f"adverse_{int(adverse_pct * 100)}pct"] = {
                "stressed_underlying": round(S_new, 2),
                "stressed_iv_pct": round(iv_new * 100, 1),
                "new_mid": round(new_price, 3),
                "mtm_pnl_$": round(mtm_pnl_dollar, 2),
                "mtm_pnl_pct_of_collateral": round(
                    mtm_pnl_dollar / collateral * 100, 2),
                "new_delta": round(new_delta, 3),
            }
        except Exception:
            continue
    return out


def _capital_risk_check(candidates: list, option_positions: list,
                         avail_cash: float) -> None:
    """评估每个 short put 候选若被指派需要的现金，占用户可用现金的比例。

    Semantics（2.0.1 修正）：
      `avail_cash` = 用户在账户设置填的"可用保证金/现金"。
      绝大多数券商 dashboard 上的 Available to Trade / Buying Power **已经扣除**
      当前持仓占用，所以这里**不再叠加** existing short put commitments —
      那样会双重计算。

    in-place 给每个 candidate 加：
      capital_pct: 这一单抵押 / avail_cash × 100
      capital_risk: "veto" (>100%) / "warning" (>80%) / "ok" / "n/a" / "unknown"
      capital_commitments: 拆分明细
    """
    for c in candidates:
        if c.get("type") != "put":
            c["capital_risk"] = "n/a"
            continue
        contracts = int(c.get("suggested_contracts") or 1)
        this_commit = float(c.get("strike") or 0) * 100 * contracts
        c["capital_commitments"] = {
            "this_$": round(this_commit, 0),
            "available_$": round(avail_cash, 0),
            "suggested_contracts": contracts,
        }
        if avail_cash <= 0:
            c["capital_risk"] = "unknown"
            c["capital_pct"] = None
            continue
        pct = this_commit / avail_cash * 100
        c["capital_pct"] = round(pct, 1)
        if pct > 100:
            c["capital_risk"] = "veto"
        elif pct > 80:
            c["capital_risk"] = "warning"
        else:
            c["capital_risk"] = "ok"


def build_ladder(candidates: list, budget: float, size: int = 4,
                  min_size: int = 2) -> Optional[dict]:
    """从 recommend 已排序候选清单里构建一组 CSP strike 阶梯。

    思路（v2 #2，2 版加自适应）：
      - 用同一个到期日（候选最多的那个 expiry，保证可比性）
      - 从候选 pool 里按 |delta| 升序排序后均匀选 N 档（覆盖 prob_safe 范围）
      - **自动按 budget 自适应**：默认尝试 size 档，预算不够就降到 size-1、size-2…直到 min_size
      - 每档分配等量 contracts（units 单位）
      - 算总抵押 / 加权 prob_safe / 加权 EV / 加权年化等聚合指标

    用法约束：仅 CSP（short put）适用；call/long 直接返回 None。
    候选数 < min_size 直接返回 None。

    返回:
      None — 不可构建（candidates 太少 或 池子无 puts）
      dict — 含 rungs / 聚合数 / budget 信息 + requested_size / actual_size（说明是否缩减）
    """
    # 仅 short put（CSP）
    if not candidates:
        return None
    puts = [c for c in candidates if c.get("type") == "put"]
    if len(puts) < min_size:
        return None

    # 1. 选候选最多的 expiry（保证 strikes 都属于同一到期，方便比较 + 一次性下单）
    by_expiry = {}
    for c in puts:
        by_expiry.setdefault(c["expiry"], []).append(c)
    chosen_expiry, pool = max(by_expiry.items(), key=lambda kv: len(kv[1]))
    if len(pool) < min_size:
        return None

    # 2. 按 |delta| 升序（最安全 → 最激进）
    pool.sort(key=lambda c: abs(c.get("delta", 0)))

    def _select_n(n: int):
        """从 pool 里均匀挑 n 档，处理 indices 重叠"""
        if n == 1:
            return [pool[len(pool) // 2]]
        idx = sorted(set(
            int(round(i * (len(pool) - 1) / (n - 1))) for i in range(n)
        ))
        if len(idx) < n:
            # 候选重叠，补齐
            for i in range(len(pool)):
                if i not in idx:
                    idx.append(i)
                if len(idx) >= n:
                    break
            idx = sorted(idx[:n])
        return [pool[i] for i in idx]

    # 3. 自适应：从 requested size 往下降，找第一个 budget 能塞下的
    requested_size = size
    actual_size = None
    selected = None
    cost_per_unit = None

    if budget <= 0:
        # 没预算约束，直接用 requested
        actual_size = min(requested_size, len(pool))
        selected = _select_n(actual_size)
        cost_per_unit = sum(float(c.get("strike", 0)) * 100 for c in selected)
    else:
        # 有预算 — 从 requested 往 min_size 降
        for try_size in range(min(requested_size, len(pool)), min_size - 1, -1):
            try_selected = _select_n(try_size)
            cpu = sum(float(c.get("strike", 0)) * 100 for c in try_selected)
            if cpu <= 0:
                continue
            if budget >= cpu:
                # 这档能塞下，用它
                actual_size = try_size
                selected = try_selected
                cost_per_unit = cpu
                break
        if actual_size is None:
            # 连 min_size 档都装不下 — fallback 到 min_size 单位 1（is_affordable=False）
            if len(pool) < min_size:
                return None
            actual_size = min_size
            selected = _select_n(min_size)
            cost_per_unit = sum(float(c.get("strike", 0)) * 100 for c in selected)
            if cost_per_unit <= 0:
                return None

    units = max(1, int(budget // cost_per_unit)) if budget > 0 else 1
    is_affordable = (cost_per_unit * units <= budget) if budget > 0 else True
    was_shrunk = (actual_size < requested_size)

    # 4. 构造 rungs + 聚合
    rungs = []
    total_contracts = 0
    total_premium = 0.0
    total_collateral = 0.0
    sum_ps_weighted = 0.0   # 按 collateral 权重
    sum_ev_weighted = 0.0
    sum_ay_weighted = 0.0
    ev_data_count = 0

    for c in selected:
        contracts = units
        mid = float(c.get("mid") or 0)
        strike = float(c.get("strike") or 0)
        premium = mid * 100 * contracts
        collateral = strike * 100 * contracts
        sc = c.get("score_components") or {}
        ev_pct = sc.get("ev_annualized_pct")
        vrp = sc.get("vrp_ratio")
        ay = c.get("annualized_yield_pct") or 0
        ps = c.get("prob_safe_pct") or 0

        rungs.append({
            "ticker": c.get("ticker"),
            "strike": strike,
            "expiry": c.get("expiry"),
            "days": c.get("days"),
            "type": c.get("type"),
            "contracts": contracts,
            "mid": round(mid, 3),
            "delta": c.get("delta"),
            "prob_safe_pct": ps,
            "annualized_yield_pct": ay,
            "moneyness_pct": c.get("moneyness_pct"),
            "premium_total": round(premium, 2),
            "collateral_total": round(collateral, 2),
            "ev_annualized_pct": ev_pct,
            "vrp_ratio": vrp,
            "rent_score": c.get("rent_score"),
            "verdict_tier": (c.get("verdict") or {}).get("tier"),
            "verdict_stars": (c.get("verdict") or {}).get("stars"),
        })

        total_contracts += contracts
        total_premium += premium
        total_collateral += collateral
        sum_ps_weighted += ps * collateral
        if ev_pct is not None:
            sum_ev_weighted += ev_pct * collateral
            ev_data_count += 1
        sum_ay_weighted += ay * collateral

    if total_collateral <= 0:
        return None

    weighted_ps = sum_ps_weighted / total_collateral
    weighted_ay = sum_ay_weighted / total_collateral
    weighted_ev = (sum_ev_weighted / total_collateral) if ev_data_count else None
    portfolio_period_roc = total_premium / total_collateral * 100
    portfolio_annualized = (
        portfolio_period_roc * (365 / selected[0]["days"]) if selected[0].get("days") else None
    )

    return {
        "rungs": rungs,
        "size": len(rungs),
        "requested_size": requested_size,
        "actual_size": actual_size,
        "was_shrunk": was_shrunk,
        "expiry": chosen_expiry,
        "days": selected[0].get("days"),
        "units_per_rung": units,
        "total_contracts": total_contracts,
        "total_premium": round(total_premium, 2),
        "total_collateral": round(total_collateral, 2),
        "budget": round(budget, 2) if budget > 0 else None,
        "budget_used_pct": round(total_collateral / budget * 100, 1) if budget > 0 else None,
        "budget_remaining": round(budget - total_collateral, 2) if budget > 0 else None,
        "is_affordable": is_affordable,
        "min_budget_needed": round(cost_per_unit, 2),
        "weighted_prob_safe_pct": round(weighted_ps, 1),
        "weighted_ev_pct": round(weighted_ev, 2) if weighted_ev is not None else None,
        "weighted_annualized_yield_pct": round(weighted_ay, 1),
        "portfolio_annualized_pct": round(portfolio_annualized, 1) if portfolio_annualized else None,
    }


def _landlord_score(opt: dict, is_csp: bool, underlying: float,
                     iv_rank: Optional[dict], backtest: Optional[dict],
                     earnings_cross: bool, earnings_days_until: Optional[int],
                     risk: str, intent: str = "premium",
                     target_days: int = None,
                     realized_vol: Optional[float] = None,
                     is_leveraged_etf: bool = False,
                     is_willing_to_own: bool = False) -> dict:
    """
    包租公分（rent_score）2.0 — VRP-based 边际收益评分。

    v2.0 改动：
      - base 换成"年化 EV %"（用 realized vol 算 fair value，premium - fair = edge）
      - 替代原 period_roc × prob_safe^1.5 × iv_f 三项（VRP 已隐含 prob & IV-vs-history）
      - 新增 wto_f（willing_to_own）：CSP on 你愿接的标的 +8%，CC 上 -3%
      - 杠杆 ETF：不享受 wto bonus（vol decay 让长期持有不值得 wheel）
      - realized_vol 不可用时回退 v1.4 公式保证 backward compatibility
    返回 {"score": float, "components": {...}}。
    """
    period_roc = max(0, opt.get("period_roc_pct", 0))
    prob_safe  = max(0, min(100, opt["prob_safe_pct"])) / 100
    spread_pct = opt["spread_pct"]
    days       = opt["days"]
    abs_delta  = abs(opt["delta"])
    oi         = opt.get("oi", 0)
    volume     = opt.get("volume", 0)
    mid        = float(opt.get("mid") or 0)
    strike     = float(opt.get("strike") or 0)
    iv_pct     = opt.get("iv", 0)
    is_call    = (opt.get("type") == "call")

    # 1. 基底：用 realized vol 算 fair value，premium - fair = edge → 年化 EV %
    ev_annualized_pct = None
    vrp_ratio = None
    fair_value = None
    used_v2_base = False
    base = period_roc  # v1.4 fallback

    if (realized_vol is not None and realized_vol > 0
            and days > 0 and mid > 0 and strike > 0 and underlying > 0):
        try:
            T = days / 365.0
            fair_value, _, _, _ = price_option(
                underlying, strike, T, RISK_FREE, realized_vol, is_call)
            edge_per_share = mid - fair_value
            # 用 strike 作 collateral 基数（与 recommend() 的 collateral 计算一致）
            ev_annualized_pct = (edge_per_share / strike) * (365 / days) * 100
            # base = EV，但有 floor 防止接近 0 时 score 整段塌掉
            base = max(0.5, ev_annualized_pct)
            iv_dec = iv_pct / 100 if iv_pct > 3 else iv_pct
            if iv_dec > 0:
                vrp_ratio = round(iv_dec / realized_vol, 3)
            used_v2_base = True
        except Exception:
            base = period_roc

    # 2. 安全度：v2 base 已隐含尾部概率（fair_value 用了 N(-d2_RV)），不再重复
    safety = 1.0 if used_v2_base else (prob_safe ** 1.5)

    # 3. DTE 甜蜜区
    # v2.0：IV rank 高 → 甜蜜区滑向短 DTE（捕 IV crush），低 → 滑向长 DTE
    _iv_rank_for_dte = (iv_rank or {}).get("iv_rank")
    dte_f = _dte_sweet_factor(days, target_days=target_days,
                                iv_rank_pct=_iv_rank_for_dte)

    # 4. Delta 甜蜜区
    delta_f = _delta_sweet_factor(abs_delta)

    # 5. IV rank：v2 已被 EV/VRP 吸收，仅 v1.4 fallback 时启用
    iv_f = 1.0
    if not used_v2_base and iv_rank and "iv_rank" in iv_rank:
        ir = iv_rank["iv_rank"]
        if ir >= 70:   iv_f = 1.20
        elif ir >= 50: iv_f = 1.08
        elif ir <= 20: iv_f = 0.85
        elif ir <= 35: iv_f = 0.93

    # 6. 流动性
    liq_f, liq_breakdown = _liquidity_factor_v11(spread_pct, oi, volume)

    # 7. 财报跨期
    earnings_f = 1.0
    if earnings_cross and earnings_days_until is not None and earnings_days_until >= 0:
        earnings_f = _earnings_factor(earnings_days_until, risk, intent=intent)

    # 8. 回测胜率
    bt_f = 1.0
    if backtest and backtest.get("n_trades", 0) >= 5:
        wr = backtest["win_rate"]
        if wr >= 75: bt_f = 1.12
        elif wr >= 60: bt_f = 1.04
        elif wr < 45: bt_f = 0.85

    # 9. NEW — Willing-to-own bonus / penalty（杠杆 ETF 例外）
    wto_f = 1.0
    if is_willing_to_own and not is_leveraged_etf:
        if is_csp:
            wto_f = 1.08   # 你愿接的标的卖 put：被指派 = 拿到想要的股票
        elif is_call:
            wto_f = 0.97   # CC on 你心爱的股：你不想被叫走 → 轻微扣分

    score = base * safety * dte_f * delta_f * iv_f * liq_f * earnings_f * bt_f * wto_f

    components = {
        "period_roc": round(period_roc, 2),
        "safety": round(safety, 3),
        "dte_factor": round(dte_f, 2),
        "delta_factor": round(delta_f, 2),
        "iv_factor": round(iv_f, 2),
        "liquidity_factor": round(liq_f, 2),
        "liquidity_breakdown": liq_breakdown,
        "earnings_factor": round(earnings_f, 2),
        "backtest_factor": round(bt_f, 2),
        "wto_factor": round(wto_f, 2),
        "used_v2_base": used_v2_base,
    }
    if used_v2_base:
        components["ev_annualized_pct"] = round(ev_annualized_pct, 2)
        components["fair_value_per_share"] = round(fair_value, 3)
        if realized_vol is not None:
            components["realized_vol_pct"] = round(realized_vol * 100, 1)
        if vrp_ratio is not None:
            components["vrp_ratio"] = vrp_ratio
    if is_leveraged_etf:
        components["is_leveraged_etf"] = True
    if is_willing_to_own:
        components["is_willing_to_own"] = True

    return {"score": round(score, 2), "components": components}


def _make_verdict(opt: dict, is_short: bool, intent: str,
                  iv_rank: Optional[dict],
                  backtest: Optional[dict] = None, risk: str = "balanced",
                  is_csp: bool = False, underlying: float = 0,
                  is_leveraged_etf: bool = False) -> dict:
    """生成一句话推荐 verdict（包租公算法 2.0 — 房东视角，损失厌恶 + EV/资金/杠杆 ETF 三类新信号）"""
    pros, cons = [], []
    weight = 0  # 综合权重：正数 = 偏好，负数 = 不偏好

    # ── 2.0 新增：从 score_components 读 EV / VRP 信号
    sc = opt.get("score_components") or {}
    used_v2 = sc.get("used_v2_base", False)
    ev_pct = sc.get("ev_annualized_pct")
    vrp = sc.get("vrp_ratio")
    capital_risk = opt.get("capital_risk", "n/a")
    capital_pct = opt.get("capital_pct")

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

    # 财报处理 — 算法 1.3：按意图区分利弊
    earnings_veto = False
    if opt.get("earnings_warning"):
        ed = opt["earnings_warning"]
        if intent in ("csp", "covered_call"):
            # CSP/CC：财报前 IV 高 = 更多权利金 = 优势
            if risk == "conservative" and ed["days"] <= 3:
                cons.append(f"⚠️ {ed['date']} 财报在 3 天内，gap down 风险较高")
                weight -= 2
            else:
                pros.append(f"📊 {ed['date']} 财报前（剩 {ed['days']} 天），IV 偏高，权利金充裕")
                weight += 1
                # v2.0 #6 财报 IV crush 红利估算（仅当 capture > 0）
                crush = opt.get("earnings_crush_capture_$")
                if crush and crush > 0:
                    crush_pct = opt.get("earnings_crush_capture_pct", 0)
                    pros.append(f"💎 财报 IV crush 红利估 +${crush:.0f}/张 ({crush_pct:.1f}% 抵押)")
                    weight += 1
        else:
            # premium / long_vol：双向 gamma 风险
            if is_short and risk == "conservative":
                cons.append(f"🚫 {ed['date']} 财报跨期（剩 {ed['days']} 天）— 保守派不接此单")
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

    # ── 2.0 新增信号：EV / VRP（仅 v2 base 时启用）
    if is_short and used_v2 and ev_pct is not None:
        if ev_pct < 0:
            cons.append(f"⚠️ 年化超额收益 {ev_pct:.1f}% — IV 低于已实现 vol，正在亏卖"); weight -= 2
        elif ev_pct > 15 and vrp and vrp > 1.20:
            pros.append(f"💰 年化超额收益 {ev_pct:.1f}% (VRP {vrp:.2f}，IV 比真实 vol 高 20%+)"); weight += 2
        elif ev_pct > 5:
            pros.append(f"📊 年化超额收益 {ev_pct:.1f}%"); weight += 1

    # ── 2.0 新增信号：资金占用风险
    # 2.0.2：资金不够不再影响评分 / 不进 cons / 不顶 tier — 前端独立 banner 提示。
    # 设计意图：标的本身的"房源质量"和"你的钱够不够"是两码事，混在一起会让 5 星好标的
    # 因为用户保证金少而被打 2 星 + tier filter 一过滤就全部消失。
    # 资金信号改为独立 `capital_blocker` 字段（this/avail/max_contracts），前端渲染
    # "💰 你的现金只够 N 张" 单独 chip，不影响 verdict tier。
    capital_blocker = None
    if capital_risk == "veto":
        cc = opt.get("capital_commitments") or {}
        this_v = cc.get("this_$")
        avail_v = cc.get("available_$")
        sug = cc.get("suggested_contracts") or 1
        strike_v = opt.get("strike") or 0
        max_contracts = int(avail_v // (strike_v * 100)) if strike_v and avail_v else 0
        capital_blocker = {
            "needed_$": this_v,
            "available_$": avail_v,
            "suggested_contracts": sug,
            "max_contracts": max_contracts,
        }

    # ── 2.0 新增信号：杠杆 ETF 警告
    if is_leveraged_etf and is_short:
        cons.append("⚠️ 杠杆 ETF — 长期持有有波动率衰减损耗，wheel 回本慢")
        weight -= 1

    # 损失厌恶：cons 数量 ≥ pros 时再扣一分（包租公房东最讨厌"麻烦")
    if len(cons) > len(pros):
        weight -= 1

    # 综合评级（基于加权得分，越大越好）
    # 注：capital_blocker（资金不够）不参与 tier — 见 capital_risk 段落注释
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
        "capital_blocker": capital_blocker,
    }


def _adjust_profit_target_by_vrp(base_pct: float, vrp: Optional[float]) -> tuple:
    """VRP（IV/RV ratio）决定早平阈值：
      VRP 高 → IV crush 来得快，早平 30%
      VRP 低 → 卖在低 IV 期，等 vol expansion，target 拉高
    返回 (adjusted_pct, reason_key)
    """
    if vrp is None or vrp <= 0:
        return base_pct, "vrp_neutral"
    if vrp >= 1.30:
        return max(25, base_pct - 20), "vrp_high"   # 50 → 30
    if vrp >= 1.15:
        return max(35, base_pct - 10), "vrp_above"  # 50 → 40
    if vrp <= 1.00:
        return min(80, base_pct + 20), "vrp_low"    # 50 → 70
    if vrp <= 1.05:
        return min(70, base_pct + 10), "vrp_below"  # 50 → 60
    return base_pct, "vrp_neutral"


def _dte_cutoff_threshold(days: int, exit_style: str) -> int:
    """Tasty 经验：21 DTE 之前死磕 50% 才有意义；剩 ≤ 21 天 theta 已吃完 80%。
    包租公译法：'剩多少天强制换租客'。
    early_close: max(orig_dte * 0.3, 7)
    wheel_assign: max(orig_dte * 0.2, 5)  仅在盈利时触发
    hold_to_expiry: 0  仅到期日处理
    """
    if exit_style == "hold_to_expiry":
        return 0
    if exit_style == "wheel_assign":
        return max(5, int(days * 0.2))
    return max(7, int(days * 0.3))   # early_close


def _delta_breach_threshold(exit_style: str, kind: str) -> Optional[float]:
    """Delta 突破触发线（绝对值）：
    short premium 风险真正的来源是 ITM 接货 / 被叫走，不是 premium 涨多少。
    early_close: 0.30   一升就 roll
    wheel_assign: 0.45  愿意接货，宽容一点
    hold_to_expiry: None  不基于 delta 触发
    """
    if kind not in ("short_premium", "csp", "covered_call"):
        return None
    if exit_style == "early_close":
        return 0.30
    if exit_style == "wheel_assign":
        return 0.45
    return None  # hold_to_expiry


def _exit_plan(opt: dict, intent: str, is_csp: bool, risk: str,
               is_covered: bool = False, is_short: bool = True,
               exit_style: str = "early_close") -> dict:
    """
    包租公式出场计划 — 4 条事件触发线（不是 trader 的 take profit/stop loss 双阈值）。

    输出:
      kind: short_premium / csp / covered_call / leaps / long_other
      exit_style: early_close / wheel_assign / hold_to_expiry
      triggers: [{id, icon, kind, label_key, condition_key, condition_vars,
                  action_key, reason_key, reason_vars, active}]
      legacy 字段（保留兼容前端 renderExitPlan）:
        profit_target_pct / stop_loss_pct / stop_loss_disabled
        exit_at_price / stop_at_price / roll_trigger
        summary_key / summary_vars
    """
    mid = float(opt.get("mid") or 0)
    days = int(opt.get("days") or 0)
    strike = float(opt.get("strike") or 0)
    delta = float(opt.get("delta") or 0)
    underlying_px = float(opt.get("underlying") or 0)
    ticker = opt.get("ticker") or ""

    # v2 信号（可能没有）
    sc = opt.get("score_components") or {}
    vrp = sc.get("vrp_ratio")
    stress = opt.get("stress_components") or {}
    earnings_warn = opt.get("earnings_warning")
    capital_pct = opt.get("capital_pct")
    capital_risk = opt.get("capital_risk")

    # 推断策略类型
    if intent == "long_leaps":
        kind = "leaps"
    elif is_csp:
        kind = "csp"
    elif is_covered:
        kind = "covered_call"
    elif is_short:
        kind = "short_premium"
    else:
        kind = "long_other"

    # ── LEAPS / long_other 保留原矩阵（非租房场景，沿用 trader 双阈值）
    if kind in ("leaps", "long_other"):
        matrix = {
            "leaps": {
                "conservative": (50,  50),
                "balanced":     (100, 50),
                "aggressive":   (200, 50),
            },
            "long_other": {
                "conservative": (50,  50),
                "balanced":     (100, 50),
                "aggressive":   (150, 50),
            },
        }
        profit_pct, stop_pct = matrix[kind].get(risk, matrix[kind]["balanced"])
        exit_at_price = round(mid * (1 + profit_pct / 100.0), 2) if mid > 0 else None
        stop_at_price = round(mid * (1 - stop_pct / 100.0), 2) if mid > 0 else None
        return {
            "kind": kind,
            "exit_style": exit_style,
            "profit_target_pct": profit_pct,
            "stop_loss_pct": stop_pct,
            "stop_loss_disabled": False,
            "exit_at_price": exit_at_price,
            "stop_at_price": stop_at_price,
            "roll_trigger": None,
            "summary_key": f"exit_summary_{kind}",
            "summary_vars": {
                "profit_pct": profit_pct, "stop_pct": stop_pct,
                "exit_price": exit_at_price or 0, "stop_price": stop_at_price or 0,
            },
            "triggers": [
                {
                    "id": "leaps_profit", "icon": "📈", "kind": "profit",
                    "label_key": "exit_trig_leaps_profit",
                    "condition_key": "exit_cond_price_up",
                    "condition_vars": {
                        "target_px": exit_at_price or 0,
                        "profit_pct": profit_pct,
                        "entry_px": mid,
                    },
                    "action_key": "exit_act_lock_profit",
                    "reason_key": "leaps_target_base", "reason_vars": {},
                    "active": True,
                },
                {
                    "id": "leaps_stop", "icon": "🛑", "kind": "stop",
                    "label_key": "exit_trig_leaps_stop",
                    "condition_key": "exit_cond_price_down",
                    "condition_vars": {
                        "target_px": stop_at_price or 0,
                        "loss_pct": stop_pct,
                        "entry_px": mid,
                    },
                    "action_key": "exit_act_stop_loss",
                    "reason_key": "leaps_stop_base", "reason_vars": {},
                    "active": True,
                },
            ],
        }

    # ── 短卖三态（short_premium / csp / covered_call）：4 触发线

    # 1️⃣ 早收租 (profit target)：50% base，按 VRP 微调
    base_profit_by_risk = {"conservative": 35, "balanced": 50, "aggressive": 65}
    base_profit = base_profit_by_risk.get(risk, 50)
    if exit_style == "hold_to_expiry":
        # 死磕到期派 = 不主动早平
        profit_pct = 90
        profit_reason_key = "hold_expire"
    else:
        profit_pct, profit_reason_key = _adjust_profit_target_by_vrp(base_profit, vrp)
    profit_target_px = round(mid * (1 - profit_pct / 100.0), 2) if mid > 0 else 0
    profit_dollars = round((mid - profit_target_px) * 100, 0) if mid > 0 else 0

    # 2️⃣ DTE 换租截止
    dte_cutoff = _dte_cutoff_threshold(days, exit_style)

    # 3️⃣ 房客违约 (delta + 标的反向触发价)
    delta_thr = _delta_breach_threshold(exit_style, kind)
    # 触发标的价：用 stress -5% 的 stressed_underlying（不利方向参考）
    breach_px = None
    if stress.get("adverse_5pct"):
        breach_px = stress["adverse_5pct"].get("stressed_underlying")
    if breach_px is None and underlying_px > 0:
        # fallback：strike 旁边 2% 缓冲
        if kind == "covered_call":
            breach_px = round(strike * 0.98, 2)   # short call → 涨破
        else:
            breach_px = round(strike * 1.02, 2)   # short put → 跌破

    # 4️⃣ 红线（必出场）
    red_line_triggers = []
    if earnings_warn:
        red_line_triggers.append({
            "trigger": "earnings_cross",
            "vars": {"date": earnings_warn.get("date"), "days": earnings_warn.get("days")},
        })
    # 接货占现金 threshold：early_close 25% / wheel_assign 35% / hold 50%
    capital_thr = {"early_close": 25, "wheel_assign": 35, "hold_to_expiry": 50}.get(exit_style, 25)
    if capital_pct is not None and capital_pct > capital_thr:
        red_line_triggers.append({
            "trigger": "capital_exceeded",
            "vars": {"capital_pct": capital_pct, "threshold": capital_thr},
        })
    if capital_risk == "red":
        red_line_triggers.append({"trigger": "capital_red", "vars": {}})

    # ── 组装 triggers 数组
    triggers = []

    # 1. 早收租
    triggers.append({
        "id": "early_close_profit",
        "icon": "📬",
        "kind": "profit",
        "label_key": "exit_trig_early_rent",
        "condition_key": "exit_cond_premium_decay",
        "condition_vars": {
            "target_px": profit_target_px,
            "profit_pct": profit_pct,
            "profit_amt": profit_dollars,
            "entry_px": round(mid, 2),
        },
        "action_key": "exit_act_close_redeploy" if exit_style != "hold_to_expiry" else "exit_act_hold_to_zero",
        "reason_key": profit_reason_key,
        "reason_vars": {"vrp": vrp} if vrp is not None else {},
        "active": exit_style != "hold_to_expiry",
    })

    # 2. DTE 换租截止
    triggers.append({
        "id": "dte_cutoff",
        "icon": "⏱️",
        "kind": "dte_cutoff",
        "label_key": "exit_trig_dte_cutoff",
        "condition_key": "exit_cond_dte_left",
        "condition_vars": {
            "dte_threshold": dte_cutoff,
            "dte_original": days,
        },
        "action_key": "exit_act_force_close" if exit_style == "early_close" else "exit_act_close_if_profit",
        "reason_key": "tasty_21d_rule",
        "reason_vars": {},
        "active": exit_style != "hold_to_expiry" and dte_cutoff > 0,
    })

    # 3. 房客违约（Delta / 标的反向破位）
    breach_action = {
        "early_close": "exit_act_roll_or_stop",     # 不接货 → roll 到下月或止损
        "wheel_assign": "exit_act_roll_or_accept",  # 愿意接货 → roll 或准备接货
        "hold_to_expiry": "exit_act_hold_assign",   # 持有到期接货
    }.get(exit_style, "exit_act_roll_or_stop")
    triggers.append({
        "id": "tenant_breach",
        "icon": "⚠️",
        "kind": "breach",
        "label_key": "exit_trig_tenant_breach" if exit_style != "wheel_assign" else "exit_trig_prepare_assign",
        "condition_key": "exit_cond_delta_or_underlying",
        "condition_vars": {
            "delta_threshold": delta_thr,
            "underlying_breach_px": breach_px,
            "ticker": ticker,
            "side": "below" if kind != "covered_call" else "above",
        },
        "action_key": breach_action,
        "reason_key": "delta_real_risk",
        "reason_vars": {},
        "active": delta_thr is not None,
    })

    # 4. 红线
    triggers.append({
        "id": "red_line",
        "icon": "🚨",
        "kind": "red_line",
        "label_key": "exit_trig_red_line",
        "condition_key": "exit_cond_red_line",
        "condition_vars": {
            "events": red_line_triggers,
            "capital_threshold": capital_thr,
        },
        "action_key": "exit_act_immediate_close",
        "reason_key": "red_line_no_assign",
        "reason_vars": {},
        "active": True,  # 红线始终活跃
        "armed": len(red_line_triggers) > 0,  # 是否已经被触发
    })

    # ── 兼容字段（前端 renderExitPlan 暂时还在用）
    if exit_style == "hold_to_expiry":
        legacy_stop_pct = None
        legacy_stop_px = None
        legacy_summary = f"exit_summary_{kind}_hold_to_expiry"
        legacy_roll_trigger = "assigned_only"
    else:
        # 止损价用 breach_px 反推：标的跌到 breach_px 时 short put 大概的 premium
        # 简化：stress 给的 new_mid 已经是近似
        if stress.get("adverse_5pct") and stress["adverse_5pct"].get("new_mid"):
            legacy_stop_px = stress["adverse_5pct"]["new_mid"]
        elif mid > 0:
            legacy_stop_px = round(mid * 2.0, 2)
        else:
            legacy_stop_px = None
        # legacy stop_pct = 权利金涨多少
        legacy_stop_pct = round((legacy_stop_px / mid - 1) * 100, 0) if (legacy_stop_px and mid > 0) else 100
        legacy_summary = f"exit_summary_{kind}"
        legacy_roll_trigger = "delta_breach"

    return {
        "kind": kind,
        "exit_style": exit_style,
        "profit_target_pct": profit_pct,
        "stop_loss_pct": legacy_stop_pct,
        "stop_loss_disabled": legacy_stop_pct is None,
        "exit_at_price": profit_target_px,
        "stop_at_price": legacy_stop_px,
        "roll_trigger": legacy_roll_trigger,
        "summary_key": legacy_summary,
        "summary_vars": {
            "profit_pct": profit_pct,
            "stop_pct": legacy_stop_pct if legacy_stop_pct is not None else 0,
            "exit_price": profit_target_px,
            "stop_price": legacy_stop_px if legacy_stop_px is not None else 0,
        },
        "triggers": triggers,
        "dte_cutoff": dte_cutoff,
        "delta_breach_threshold": delta_thr,
        "underlying_breach_px": breach_px,
        "red_line_armed": [r["trigger"] for r in red_line_triggers],
    }


def _find_expiries(ticker: str, target_days: int, n: int = 3,
                   min_days: int = None, max_days: int = None):
    """找最接近 target_days 的到期日，可选范围过滤。"""
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
                if min_days is not None and days < min_days:
                    continue
                if max_days is not None and days > max_days:
                    continue
                scored.append((abs(days - target_days), e, days))
            except Exception:
                continue
        scored.sort()
        return [e for _, e, _ in scored[:n]]
    except Exception:
        return []


def scan_multi(req: dict) -> dict:
    """v2.0 #7 多 ticker 单次扫描 — 对 tickers 数组逐一调 recommend 后合并 + 排序。

    入参：
      req.tickers: ["TSLA", "NVDA", "GOOG"]  最多 5 个
      其他字段（direction/intent/timeframe/risk/exit_style/account/...）会原样
      传给每个 ticker 的 recommend 调用
    输出（同 recommend 形状，额外字段）:
      tickers_scanned: 实际扫描的 ticker 列表
      errors_per_ticker: {ticker: error_msg}（如有失败）
      candidates: 跨 ticker 合并后按 rent_score 排序的 top 15
    """
    tickers = req.get("tickers") or []
    lang = req.get("lang", "zh")
    if not isinstance(tickers, list) or not tickers:
        return {"error": _T(lang, "请提供 tickers 数组")}
    # 去重 + 标准化 + 限 5 个
    seen = set()
    clean = []
    for t in tickers:
        u = (t or "").upper().strip()
        if u and u not in seen and len(u) <= 6:
            clean.append(u)
            seen.add(u)
        if len(clean) >= 5:
            break
    if not clean:
        return {"error": _T(lang, "tickers 无效")}

    all_candidates = []
    errors_per_ticker = {}
    per_ticker_summary = []
    for tk in clean:
        sub_req = dict(req)
        sub_req["ticker"] = tk
        sub_req["tickers"] = None  # 避免递归
        try:
            r = recommend(sub_req)
        except Exception as e:
            errors_per_ticker[tk] = str(e)
            continue
        if r.get("error"):
            errors_per_ticker[tk] = r["error"]
            continue
        cands = r.get("candidates") or []
        for c in cands:
            c["origin_ticker"] = tk
            all_candidates.append(c)
        per_ticker_summary.append({
            "ticker": tk,
            "underlying": r.get("underlying"),
            "n_candidates": len(cands),
            "top_score": (cands[0].get("rent_score") or cands[0].get("score")) if cands else None,
            "realized_vol_30d_pct": r.get("realized_vol_30d_pct"),
            "is_leveraged_etf": r.get("is_leveraged_etf"),
        })

    # 跨 ticker 按 rent_score 排序
    all_candidates.sort(key=lambda c: -(c.get("rent_score") or c.get("score") or 0))

    return {
        "tickers_scanned": clean,
        "errors_per_ticker": errors_per_ticker or None,
        "per_ticker_summary": per_ticker_summary,
        "candidates": all_candidates[:15],
        "total_examined": len(all_candidates),
        "algorithm": {
            "name": ALGORITHM_NAME,
            "version": ALGORITHM_VERSION,
            "tagline": ALGORITHM_TAGLINE,
        },
        "criteria": {
            "direction": req.get("direction"),
            "intent": req.get("intent"),
            "timeframe": req.get("timeframe"),
            "risk": req.get("risk"),
            "exit_style": req.get("exit_style"),
        },
        "scan_mode": "multi",
    }


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

    # 账户 context（可选）
    account = req.get("account") or {}
    avail_margin = float(account.get("available_margin") or 0)
    # account_type: cash | margin_l2 | margin_l3 （legacy: margin → margin_l3）
    account_type = account.get("account_type", "cash")
    if account_type == "margin":
        account_type = "margin_l3"
    stock_map = {
        p["ticker"].upper(): int(p.get("shares") or 0)
        for p in (account.get("stock_positions") or [])
        if p.get("ticker")
    }
    option_positions = account.get("option_positions") or []

    # 拿当前价
    prices = fetch_prices([ticker])
    underlying = prices.get(ticker, {}).get("price", 0.0)
    if underlying <= 0:
        return {"error": f"无法拉到 {ticker} 实时价格"}

    # 2.0 新增：已实现波动率（30d） / 杠杆 ETF flag / willing_to_own 推导
    realized_vol_30d = _realized_vol(ticker, window=30)
    is_leveraged_etf = _is_leveraged_etf(ticker)
    # willing_to_own：先看用户手动 override，再 fallback 到自动推导
    #   自动推导：持有正股 或 已经在该 ticker 上有 short put（行动表态）
    #   手动 override：state._meta.willing_overrides[TSLA] = "on" | "off"
    held_shares = stock_map.get(ticker, 0)
    has_existing_short_put = any(
        (p.get("ticker") or "").upper() == ticker
        and p.get("type") == "put"
        and not p.get("closed")
        for p in (option_positions or [])
    )
    _willing_overrides = req.get("willing_overrides") or {}
    _override = _willing_overrides.get(ticker) or _willing_overrides.get(ticker.upper())
    if _override == "on":
        is_willing_to_own = True
    elif _override == "off":
        is_willing_to_own = False
    else:
        is_willing_to_own = bool(held_shares >= 100 or has_existing_short_put)

    # exit_style：包租公 3 个房东人设。兼容旧值 auto / wheel_purist
    #   early_close     早收租派：50% 早平 + delta 0.30 触发 roll + 不接货
    #   wheel_assign    Wheel 接货派：50% 早平 + delta 0.45 才止损 + 愿意接货转 CC
    #   hold_to_expiry  死磕到期派：持到 expire OTM，吃满租金（≈ 旧 wheel_purist）
    exit_style = req.get("exit_style", "early_close")
    _exit_style_aliases = {
        "auto": "early_close",
        "wheel_purist": "hold_to_expiry",
    }
    exit_style = _exit_style_aliases.get(exit_style, exit_style)
    if exit_style not in ("early_close", "wheel_assign", "hold_to_expiry"):
        exit_style = "early_close"

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

    timeframe_min = req.get("timeframe_min")
    timeframe_max = req.get("timeframe_max")
    target_exps = _find_expiries(ticker, timeframe, n=3,
                                  min_days=timeframe_min, max_days=timeframe_max)
    today = date.today()

    # 🔄 Roll 上下文（v2.0 #5）：当 req.roll_for 存在时，对候选施加约束:
    #   1) expiry 必须 ≥ 原 expiry + 14d（避免 roll 到太近的日期没意义）
    #   2) 同 type（put/call）
    #   3) 更 OTM 的 strike（short put → strike < 原；short call → strike > 原）
    #   4) 每个候选输出 roll_net_credit = (new_mid - current_mid) × 100
    roll_for = req.get("roll_for") or None
    roll_orig_strike = None
    roll_orig_type = None
    roll_current_mid = None
    if roll_for and isinstance(roll_for, dict):
        try:
            roll_orig_strike = float(roll_for.get("strike") or 0)
            roll_orig_type = (roll_for.get("type") or "").lower()
            roll_current_mid = float(roll_for.get("current_mid") or 0)
            roll_orig_expiry = roll_for.get("expiry")
            if roll_orig_expiry:
                _orig_exp_date = date.fromisoformat(roll_orig_expiry)
                _min_roll_exp = _orig_exp_date + timedelta(days=14)
                target_exps = [e for e in target_exps
                                if date.fromisoformat(e) >= _min_roll_exp]
            # 如果约束后无 expiry，再放宽到原 expiry 之后任意（用户可能 timeframe 选太短）
            if not target_exps and roll_orig_expiry:
                _orig_exp_date = date.fromisoformat(roll_orig_expiry)
                target_exps = _find_expiries(ticker, timeframe + 14, n=5,
                                              min_days=(timeframe + 7),
                                              max_days=(timeframe + 60))
                target_exps = [e for e in target_exps
                                if date.fromisoformat(e) > _orig_exp_date]
        except (TypeError, ValueError):
            roll_for = None
            roll_orig_strike = None
            roll_orig_type = None
            roll_current_mid = None

    # IV-adaptive delta band (仅对 short premium 策略生效；LEAPS 走自己的区间)
    iv_rank_for_band = None
    if is_short and target_exps and intent != "long_leaps":
        peek_iv = _peek_atm_iv(ticker, target_exps[0], underlying)
        if peek_iv is not None:
            r = _compute_iv_rank(ticker, peek_iv)
            if r and r.get("rank_pct") is not None:
                iv_rank_for_band = r["rank_pct"]
                delta_band = _adjust_delta_band_by_iv(delta_band, iv_rank_for_band)

    # Vol skew 信号（put_iv / call_iv），仅 short premium 策略需要
    skew_signal = None
    if is_short and target_exps and intent != "long_leaps":
        skew_signal = _compute_skew_signal(ticker, target_exps[0], underlying)

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

            # 🔄 Roll 约束：strike 必须更 OTM（put: 更低 / call: 更高）
            if roll_for and roll_orig_strike and roll_orig_type:
                if roll_orig_type == "put" and strike >= roll_orig_strike:
                    continue
                if roll_orig_type == "call" and strike <= roll_orig_strike:
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
            period_roc = 0.0
            if is_short and collateral > 0 and days > 0:
                annualized = (premium / collateral) * (365 / days) * 100
                period_roc = (premium / collateral) * 100  # 本期实际收益率（不年化）
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
                "period_roc_pct": round(period_roc, 2),
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
    #    v2.0：回测跟 exit_style 路径触发同步（50% 早平 + DTE cutoff）
    backtest = _backtest_strategy(
        ticker, sample_dte=min(max(timeframe, 5), 30),
        delta_target=sum(delta_band) / 2,
        is_short_put=(is_short and not is_call),
        exit_style=exit_style,
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

            # ── v2.0 #6 财报 IV crush 红利估算（仅短卖 CSP/CC）
            # 经验：财报后 ATM IV 跌约 40%（liquid name）。假设 crush 后剩 60%。
            # 用 BS 重新算 crush 后期权值，差额 = 你能赚到的"crush 红利"
            if is_short:
                try:
                    e_days = earnings_warning.get("days") or 0
                    if 0 < e_days < c["days"]:
                        iv_pre = (c.get("iv") or 0) / 100
                        iv_post = max(0.05, iv_pre * 0.60)  # 40% crush，floor 5%
                        days_after = c["days"] - e_days
                        T_after = max(1, days_after) / 365.0
                        price_post, _, _, _ = price_option(
                            underlying, c["strike"], T_after, RISK_FREE, iv_post, is_call)
                        crush_capture = (c["mid"] - price_post) * 100
                        if crush_capture > 0:
                            c["earnings_crush_capture_$"] = round(crush_capture, 2)
                            collateral = c["strike"] * 100 if c["strike"] else 1
                            c["earnings_crush_capture_pct"] = round(
                                crush_capture / collateral * 100, 2)
                except Exception:
                    pass

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

        # 包租公算法 2.0：rent_score 用 EV-based base + wto + 杠杆 ETF 例外
        earnings_days_until = (earnings_date - today).days if earnings_date else None
        if is_short:
            ls = _landlord_score(c, is_csp, underlying, iv_rank, backtest,
                                  earnings_cross, earnings_days_until, risk,
                                  intent=intent, target_days=timeframe,
                                  realized_vol=realized_vol_30d,
                                  is_leveraged_etf=is_leveraged_etf,
                                  is_willing_to_own=is_willing_to_own)
            c["rent_score"] = ls["score"]
            c["score_components"] = ls["components"]
            c["score"] = ls["score"]   # 排序统一用 rent_score

        # 2.0 新增：情景压力测试 -5% / -10%（仅 short premium 关心）
        if is_short:
            c["stress_components"] = _stress_test(c, underlying, c.get("iv", 0),
                                                    is_call, is_short)

        # 🔄 Roll 输出：net_credit = new_premium - cost_to_close_current（per share × 100）
        if roll_for and roll_current_mid:
            new_premium = c.get("mid") or 0
            net_credit = (new_premium - roll_current_mid) * 100
            c["roll_net_credit"] = round(net_credit, 2)
            c["roll_days_added"] = c["days"] - max(0, (date.fromisoformat(roll_for.get("expiry")) - today).days) if roll_for.get("expiry") else None
            c["roll_strike_delta"] = round(c["strike"] - roll_orig_strike, 2)

        # 标记 candidate 上的 meta 给 verdict 用
        c["is_leveraged_etf"] = is_leveraged_etf
        c["is_willing_to_own"] = is_willing_to_own

        # verdict 在 capital_risk_check 之后再算，所以这里先占位

        # 账户 context：保证金占比 + 张数建议 + Covered Call 检测 + BPR
        collateral = c["collateral_per_contract"]
        shares_held = stock_map.get(ticker, 0)
        is_covered_call = is_short and is_call and (shares_held >= 100)

        # BPR：仅 margin L3+ 裸卖才用 Reg-T BPR；L2/cash 用全额抵押
        if account_type == "margin_l3" and is_short and not is_covered_call:
            bpr = _margin_bpr(c["strike"], underlying, is_call, c["mid"])
            c["bpr_per_contract"] = round(bpr, 0)
            if bpr > 0:
                c["roc_on_bpr_pct"] = round(c["period_roc_pct"] * (collateral / bpr), 2)
        elif is_covered_call:
            c["bpr_per_contract"] = 0  # covered — no margin used

        # 资金占比 & 张数建议（L3+ 用 BPR，cash/L2 用全额 collateral）
        effective_capital = c.get("bpr_per_contract", collateral) if account_type == "margin_l3" else collateral
        if avail_margin > 0 and effective_capital > 0:
            c["margin_pct"] = round(effective_capital / avail_margin * 100, 1)
            c["suggested_contracts"] = max(1, int(avail_margin * 0.20 / effective_capital))

        # Covered Call 检测
        if is_short and is_call:
            c["is_covered"] = is_covered_call
            c["covered_contracts"] = shares_held // 100
            c["shares_held"] = shares_held

    # 2.0 新增：资金占用检查（依赖 suggested_contracts 已在第一轮算好）
    if is_short and not is_call:
        _capital_risk_check(candidates, option_positions, avail_margin)
    else:
        for c in candidates:
            c["capital_risk"] = "n/a"

    # 出场计划必须在 capital_risk_check 之后（红线触发要读 capital_pct / capital_risk）
    for c in candidates:
        # 不是每个 candidate 都标记 is_covered；用 ticker 持股推断
        ticker_held = stock_map.get((c.get("ticker") or "").upper(), 0)
        is_covered_for_c = bool(is_short and c.get("type") == "call" and ticker_held >= 100)
        c["exit_plan"] = _exit_plan(c, intent, is_csp, risk,
                                     is_covered=is_covered_for_c,
                                     is_short=is_short,
                                     exit_style=exit_style)

    # 2.0：verdict 在 capital_risk_check 之后算（这样能读到 capital_risk）
    for c in candidates:
        c["verdict"] = _make_verdict(c, is_short, intent, iv_rank,
                                      backtest, risk=risk, is_csp=is_csp,
                                      underlying=underlying,
                                      is_leveraged_etf=is_leveraged_etf)

    # 5. Score-verdict 统一（v2.0）：tier 由 rent_score 百分位驱动
    #    保留 _make_verdict 的 weight 用来生成 cons/pros 文案，但 tier/stars/label
    #    改成基于 candidate set 内 rent_score 排名。Veto 仍然硬封顶 2 星。
    if is_short:
        scored = [c for c in candidates if c.get("rent_score") is not None]
        if len(scored) >= 5:
            sorted_scores = sorted(c["rent_score"] for c in scored)
            n = len(sorted_scores)
            for c in scored:
                s = c["rent_score"]
                rank_below = sum(1 for x in sorted_scores if x < s)
                pct = (rank_below / n) * 100.0
                if pct >= 80: new_tier = 5
                elif pct >= 60: new_tier = 4
                elif pct >= 40: new_tier = 3
                elif pct >= 20: new_tier = 2
                else: new_tier = 1
                v = c["verdict"]
                # 保留 veto 硬封顶：earnings_veto。
                # 注：capital_risk == "veto" 不再封顶 tier — 资金不够是用户层面信号，
                # 不该让标的本身被打低星而被 tier filter 隐藏。
                if v.get("earnings_veto"):
                    new_tier = min(new_tier, 2)
                # 用 rent_score 绝对值兜底：极差的不该 5 星
                if s < 0.5:
                    new_tier = min(new_tier, 1)
                elif s < 2.0:
                    new_tier = min(new_tier, 3)
                # Apply
                v["tier"] = new_tier
                v["stars"] = "⭐" * new_tier
                v["score_percentile"] = round(pct, 1)
                # label / color 同步
                if new_tier == 5:
                    v["label"], v["color"] = "五星房源", "green"
                elif new_tier == 4:
                    v["label"], v["color"] = "推荐出租", "green"
                elif new_tier == 3:
                    v["label"], v["color"] = "一般房源", "yellow"
                elif new_tier == 2:
                    if v.get("earnings_veto"):
                        v["label"] = "谨慎 — 财报跨期"
                    else:
                        v["label"] = "谨慎出租"
                    v["color"] = "orange"
                else:
                    v["label"], v["color"] = "别租", "red"

    # 5b. 排序后保留 top 15
    candidates.sort(key=lambda x: (-x["verdict"]["tier"], -x["score"]))
    candidates = candidates[:15]

    # 6. Ladder builder（v2 #2）—— 仅 CSP 适用，req.ladder = {budget, size}
    ladder_proposal = None
    ladder_req = req.get("ladder") or {}
    if ladder_req and is_short and not is_call:
        try:
            ladder_budget = float(ladder_req.get("budget") or 0)
            ladder_size = int(ladder_req.get("size") or 4)
            ladder_size = max(3, min(5, ladder_size))
            if ladder_budget > 0:
                ladder_proposal = build_ladder(candidates, ladder_budget, ladder_size)
        except (TypeError, ValueError):
            ladder_proposal = None

    # Portfolio context — 同 ticker 敞口 + -15% 情景（不影响 score）
    portfolio_context = _portfolio_context(ticker, underlying, option_positions, avail_margin)

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
        "portfolio_context": portfolio_context,
        "skew_signal": skew_signal,
        "backtest_summary": backtest,  # win_rate / theoretical_pop / calibration_ratio
        # 2.0 transparency
        "realized_vol_30d_pct": round(realized_vol_30d * 100, 1) if realized_vol_30d else None,
        "is_leveraged_etf": is_leveraged_etf,
        "is_willing_to_own": is_willing_to_own,
        "exit_style": exit_style,
        "ladder_proposal": ladder_proposal,
        "roll_context": ({
            "ticker": ticker,
            "type": roll_orig_type,
            "strike": roll_orig_strike,
            "expiry": roll_for.get("expiry"),
            "current_mid": roll_current_mid,
        } if roll_for else None),
    }


# ── Anthropic SDK (LLM 包租公管家) ───────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_anthropic_client = None

def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        # 18s — JSON 输出比 prose 长，需要更多生成时间。
        # 用户 prod 总耗时 27-29s 说明 Vercel maxDuration ≥30s（Pro 计划）。
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=18.0)
        return _anthropic_client
    except Exception:
        return None


# ── Morning brief — 信号扩充 + 跨日 diff + 包租公管家 ────────────────

def _fetch_vix_quote() -> Optional[Dict]:
    """VIX 当前 + 前收盘。失败返回 None。"""
    try:
        import yfinance as yf
        session = _get_yf_session()
        t = yf.Ticker("^VIX", session=session) if session else yf.Ticker("^VIX")
        fi = t.fast_info
        return {"price": float(fi.last_price), "prev": float(fi.previous_close)}
    except Exception:
        return None


_news_cache: Dict[str, Tuple[list, float]] = {}  # ticker -> (items, fetched_at)

# 负面关键词 → 触发 news_alert focus card
_NEGATIVE_NEWS_KEYWORDS = (
    "downgrade", "loss", "lawsuit", "sec", "investigation", "bankrupt", "fraud",
    "miss", "cut", "warn", "recall", "subpoena", "delist", "fall", "plunge",
    "layoff", "lay off", "job cut", "fire", "fired", "restructur", "guidance cut",
    "merger", "acquir", "spinoff", "split",
    "降级", "亏损", "诉讼", "调查", "破产", "欺诈", "下调", "未达预期", "暴跌", "召回",
    "裁员", "解雇", "重组", "并购", "收购", "分拆", "拆分", "停牌",
)


def _fetch_position_news(positions: List[dict],
                          max_items_per_ticker: int = 3,
                          max_age_hours: int = 24,
                          cache_ttl: int = 600) -> List[Dict]:
    """抓持仓 ticker 的最近 24h 新闻（每 ticker 缓存 10 分钟）。失败返回 []。"""
    try:
        import yfinance as yf
        import time as _t
        now = _t.time()
        cutoff = now - max_age_hours * 3600
        session = _get_yf_session()
        tickers = sorted(set(p["ticker"] for p in positions
                            if not p.get("closed") and p.get("days", 0) >= 0))
        tickers = tickers[:6]  # 最多 6 个 ticker 避免 yfinance 慢

        # 分两批：cache 命中 + 需要拉的
        items_by_tk: Dict[str, list] = {}
        todo: List[str] = []
        for tk in tickers:
            if tk in _news_cache and (now - _news_cache[tk][1]) < cache_ttl:
                items_by_tk[tk] = _news_cache[tk][0]
            else:
                todo.append(tk)

        # 并行拉缺失的（per ticker ~500ms IO，6 个串行就 3s）
        if todo:
            def _one(tk: str):
                try:
                    t = yf.Ticker(tk, session=session) if session else yf.Ticker(tk)
                    return tk, (t.news or [])
                except Exception:
                    return tk, []
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(6, len(todo))) as ex:
                for tk, items in ex.map(_one, todo):
                    items_by_tk[tk] = items
                    _news_cache[tk] = (items, now)

        out: List[Dict] = []
        for tk in tickers:
            items = items_by_tk.get(tk, [])
            for n in (items or [])[:max_items_per_ticker]:
                # yfinance 新 schema 嵌套在 n['content']
                content = n.get("content") or n
                title = (content.get("title") or "").strip()
                publisher = ((content.get("provider") or {}).get("displayName")
                             or content.get("publisher") or "").strip()
                # link: 新 schema canonicalUrl / clickThroughUrl，旧 schema link
                link = ""
                ct_url = content.get("canonicalUrl") or content.get("clickThroughUrl")
                if isinstance(ct_url, dict):
                    link = ct_url.get("url", "")
                if not link:
                    link = content.get("link") or n.get("link") or ""
                pub_iso = content.get("pubDate") or ""
                pub_time = 0
                if isinstance(pub_iso, str) and pub_iso:
                    try:
                        pub_time = datetime.fromisoformat(pub_iso.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        pass
                if not pub_time:
                    pub_time = n.get("providerPublishTime") or content.get("providerPublishTime") or 0
                if pub_time < cutoff or not title:
                    continue
                out.append({
                    "ticker": tk,
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "hours_ago": max(1, int((now - pub_time) / 3600)),
                    "pub_time": int(pub_time),
                })
        # 按时间倒序，最近的在前
        out.sort(key=lambda x: -x["pub_time"])
        return out[:10]
    except Exception:
        return []


def _detect_news_alerts(news: List[Dict], lang: str) -> List[Dict]:
    """从新闻列表里挑出含负面关键词的，转为 events 加入 focus 优先列。"""
    alerts = []
    seen_titles = set()
    for n in news:
        title_lower = n["title"].lower()
        if not any(kw in title_lower for kw in _NEGATIVE_NEWS_KEYWORDS):
            continue
        if n["title"] in seen_titles:
            continue
        seen_titles.add(n["title"])
        alerts.append({
            "kind": "news_alert",
            "priority": 80,
            "position_id": None,
            "ticker": n["ticker"],
            "label": f"{n['ticker']} 新闻",
            "icon": "📰",
            "headline": _T(lang, "{tk} 新闻: {title}",
                           tk=n["ticker"],
                           title=(n["title"][:50] + "…" if len(n["title"]) > 50 else n["title"])),
            "detail": _T(lang, "{pub} · {h}h 前", pub=n["publisher"], h=n["hours_ago"]),
            "link": n.get("link") or "",
            "action": "open_news",
        })
        if len(alerts) >= 3:
            break
    return alerts


def _compute_concentration(positions: List[dict]) -> Dict:
    """最大单 ticker 占持仓暴露的百分比。"""
    active = [p for p in positions if not p.get("closed") and p.get("days", 0) >= 0]
    exposure = {}
    for p in active:
        tk = p["ticker"]
        exp = p.get("strike", 0) * p.get("contracts", 0) * 100
        exposure[tk] = exposure.get(tk, 0) + exp
    total = sum(exposure.values())
    if total <= 0:
        return {"top_ticker": "", "top_pct": 0, "n_tickers": len(exposure)}
    top_tk = max(exposure, key=exposure.get)
    return {
        "top_ticker": top_tk,
        "top_pct": exposure[top_tk] / total * 100,
        "n_tickers": len(exposure),
    }


def _compute_calendar_14d(positions: List[dict], today: date) -> List[Dict]:
    """未来 14 天 markers (财报红点 + 持仓到期金点)。"""
    end = today + timedelta(days=14)
    markers = []
    seen_earn = set()
    for p in positions:
        if p.get("closed") or p.get("days", 0) < 0:
            continue
        # 持仓到期
        try:
            exp_date = datetime.strptime(p["expiry"], "%Y-%m-%d").date()
            if today <= exp_date <= end:
                markers.append({
                    "offset": (exp_date - today).days,
                    "date": exp_date.isoformat(),
                    "type": "expiry",
                    "ticker": p["ticker"],
                    "label": p.get("label", ""),
                })
        except Exception:
            pass
        # 财报
        earn = p.get("earnings_date")
        if earn:
            try:
                earn_date = datetime.strptime(earn, "%Y-%m-%d").date()
                key = f"{p['ticker']}_{earn}"
                if today <= earn_date <= end and key not in seen_earn:
                    seen_earn.add(key)
                    markers.append({
                        "offset": (earn_date - today).days,
                        "date": earn_date.isoformat(),
                        "type": "earnings",
                        "ticker": p["ticker"],
                        "label": p["ticker"],
                    })
            except Exception:
                pass
    return markers


def _load_brief_snapshot(state: dict) -> dict:
    meta = state.get("_meta", {}) if isinstance(state, dict) else {}
    snap = meta.get("brief_snapshot", {})
    return snap if isinstance(snap, dict) else {}


def _make_brief_snapshot(positions: List[dict], market: dict, today: date) -> dict:
    pos_snap = {}
    for p in positions:
        if p.get("closed") or p.get("days", 0) < 0:
            continue
        pid = f"{p['ticker']}_{p['type']}_{_fmt_strike(p.get('strike',0))}_{p.get('expiry','')}"
        pos_snap[pid] = {
            "ticker": p.get("ticker", ""),
            "label": p.get("label", pid),
            "pnl_pct": p.get("pnl_pct", 0),
            "days": p.get("days", 0),
            "moneyness": p.get("moneyness", 0),
            "earnings_date": p.get("earnings_date"),
        }
    return {
        "date": today.isoformat(),
        "vix": (market.get("vix") or {}).get("price"),
        "positions": pos_snap,
    }


def _compute_position_changes(yesterday_snap: dict, positions: List[dict]) -> Dict:
    """对比 snapshot，找新开 / 平仓的持仓。
    返回 {added: [{label}], removed: [{label}], has_changes: bool}。
    用 pid 集合 diff —— pid 含 ticker/type/strike/expiry 结构性字段，编辑也算 (旧 pid 删 + 新 pid 加)。"""
    old_pos = (yesterday_snap or {}).get("positions") or {}
    if not isinstance(old_pos, dict):
        old_pos = {}
    old_pids = set(old_pos.keys())
    new_pids = set()
    new_labels = {}
    for p in positions:
        if p.get("closed") or p.get("days", 0) < 0:
            continue
        pid = f"{p['ticker']}_{p['type']}_{_fmt_strike(p.get('strike',0))}_{p.get('expiry','')}"
        new_pids.add(pid)
        new_labels[pid] = p.get("label", pid)
    added = [{"label": new_labels[pid]} for pid in (new_pids - old_pids)]
    removed = [{"label": (old_pos.get(pid) or {}).get("label", pid)}
               for pid in (old_pids - new_pids)]
    return {
        "added": added,
        "removed": removed,
        "has_changes": bool(added or removed),
    }


def _compute_diff_events(yesterday_snap, positions, market, lang):
    """对比昨天，找 since 昨天的"质变"事件（80% 跨越 / 进入 7 天窗口 / 新 ITM / 财报临近 / VIX 跳变）。"""
    events = []
    today_pos = {}
    for p in positions:
        if p.get("closed") or p.get("days", 0) < 0:
            continue
        pid = f"{p['ticker']}_{p['type']}_{_fmt_strike(p.get('strike',0))}_{p.get('expiry','')}"
        today_pos[pid] = p
    y_pos = yesterday_snap.get("positions", {}) if isinstance(yesterday_snap, dict) else {}

    for pid, p in today_pos.items():
        y = y_pos.get(pid)
        pct = p.get("pnl_pct", 0)
        days = p.get("days", 0)
        money = p.get("moneyness", 0)
        is_call = p.get("type") == "call"
        is_itm = (is_call and money < 0) or ((not is_call) and money > 0)
        label = p.get("label", "")

        if y and y.get("pnl_pct", 0) < 80 <= pct:
            events.append({
                "kind": "profit_threshold", "priority": 90,
                "position_id": pid, "ticker": p["ticker"], "label": label,
                "icon": "🎯",
                "headline": _T(lang, "{label} 已实现 {pct}% 权利金", label=label, pct=f"{pct:.0f}"),
                "detail": _T(lang, "昨天 {yp}%，突破 80% — 可考虑锁利", yp=f"{y.get('pnl_pct',0):.0f}"),
                "action": "view_position",
            })
        if y and y.get("days", 999) > 7 >= days >= 0:
            events.append({
                "kind": "dte_window", "priority": 70,
                "position_id": pid, "ticker": p["ticker"], "label": label,
                "icon": "⏱️",
                "headline": _T(lang, "{label} 剩 {d} 天到期", label=label, d=days),
                "detail": _T(lang, "进入 7 天到期窗口，准备处理"),
                "action": "view_position",
            })
        if y:
            y_money = y.get("moneyness", 0)
            y_is_itm = (is_call and y_money < 0) or ((not is_call) and y_money > 0)
            if is_itm and not y_is_itm:
                events.append({
                    "kind": "newly_itm", "priority": 95,
                    "position_id": pid, "ticker": p["ticker"], "label": label,
                    "icon": "🚨",
                    "headline": _T(lang, "{label} 进入 ITM", label=label),
                    "detail": _T(lang, "昨天还安全，今天突破行权 — 留意指派"),
                    "action": "view_position",
                })

    # 财报临近（不用 diff，直接判断 ≤5 天）
    for p in positions:
        if p.get("closed") or p.get("days", 0) < 0:
            continue
        earn_days = p.get("earnings_days_until")
        if earn_days is not None and 0 < earn_days <= 5 and p.get("earnings_before_expiry"):
            pid = f"{p['ticker']}_{p['type']}_{_fmt_strike(p.get('strike',0))}_{p.get('expiry','')}"
            events.append({
                "kind": "earnings_imminent", "priority": 100,
                "position_id": pid, "ticker": p["ticker"], "label": p.get("label", ""),
                "icon": "📅",
                "headline": _T(lang, "{tk} {d} 天后财报，{label} 跨越", tk=p["ticker"], d=earn_days, label=p.get("label", "")),
                "detail": _T(lang, "留意 IV crush 风险"),
                "action": "view_position",
            })

    # VIX 异动
    vix = market.get("vix") or {}
    if vix.get("prev", 0) > 0:
        chg = (vix["price"] - vix["prev"]) / vix["prev"] * 100
        if chg >= 20:
            events.append({
                "kind": "vix_spike", "priority": 85,
                "position_id": None, "ticker": "$VIX", "label": "VIX",
                "icon": "⚡",
                "headline": _T(lang, "VIX 跳涨 {pct}% 至 {v}", pct=f"{chg:.0f}", v=f"{vix['price']:.1f}"),
                "detail": _T(lang, "卖权利金窗口期，扫一眼推荐"),
                "action": "view_recommend",
            })

    events.sort(key=lambda e: -e["priority"])
    return events


def _danger_detail(p, lang):
    """距行权近的持仓 → actionable 细节（剩多少天 + 浮亏 + 建议）。"""
    parts = []
    days = p.get("days", 0)
    if days <= 7:
        parts.append(_T(lang, "剩 {d} 天", d=days))
    pnl = p.get("pnl", 0)
    if pnl < -50:
        parts.append(_T(lang, "浮亏 ${pnl}", pnl=f"{abs(pnl):,.0f}"))
    if days <= 3:
        parts.append(_T(lang, "考虑买回 / roll"))
    elif p.get("pnl_pct", 0) <= -30:
        parts.append(_T(lang, "盯紧，考虑止损"))
    return " · ".join(parts) if parts else _T(lang, "gamma 风险大")


def _rank_top_3_focus(events, positions, lang):
    """从 events 选 top 3，不足则补 ≥70% 利润 + 危险临近持仓。
    双重 dedup（pid + label）防止同 strike/expiry 重复出现。"""
    seen_pids = set()
    seen_labels = set()
    out = []

    def _try_add(item):
        pid = item.get("position_id") or f"_{item.get('kind','')}"
        lbl = item.get("label") or pid
        if pid in seen_pids or lbl in seen_labels:
            return False
        seen_pids.add(pid)
        seen_labels.add(lbl)
        out.append(item)
        return True

    for e in events:
        _try_add(e)
        if len(out) >= 3:
            return out[:3]

    # fallback 1: ≥70% 利润（锁利机会）
    actionable = [p for p in positions
                  if not p.get("closed") and p.get("days", 0) >= 0
                  and p.get("pnl_pct", 0) >= 70]
    actionable.sort(key=lambda p: -p.get("pnl_pct", 0))
    for p in actionable:
        pid = f"{p['ticker']}_{p['type']}_{_fmt_strike(p.get('strike',0))}_{p.get('expiry','')}"
        label = p.get("label", "")
        days = p.get("days", 0)
        pnl = p.get("pnl", 0)
        _try_add({
            "kind": "profit_opportunity", "priority": 50,
            "position_id": pid, "ticker": p["ticker"], "label": label,
            "icon": "🎯",
            "headline": _T(lang, "{label} 已实现 {pct}% 权利金",
                           label=label, pct=f"{p['pnl_pct']:.0f}"),
            "detail": _T(lang, "浮盈 ${pnl} · 剩 {d} 天 · 接近锁利窗口",
                         pnl=f"{pnl:,.0f}", d=days),
            "action": "view_position",
        })
        if len(out) >= 3:
            return out[:3]

    # fallback 2: 距行权 <5% 的危险持仓
    danger = [p for p in positions
              if not p.get("closed") and p.get("days", 0) >= 0
              and (((p.get("type") == "call") and p.get("moneyness", 100) < 5)
                   or ((p.get("type") == "put") and p.get("moneyness", -100) > -5))]
    # 按距到期升序（最紧迫的在前）
    danger.sort(key=lambda p: p.get("days", 999))
    for p in danger:
        pid = f"{p['ticker']}_{p['type']}_{_fmt_strike(p.get('strike',0))}_{p.get('expiry','')}"
        label = p.get("label", "")
        _try_add({
            "kind": "near_strike", "priority": 40,
            "position_id": pid, "ticker": p["ticker"], "label": label,
            "icon": "🚨",
            "headline": _T(lang, "{label} 距行权仅 {pct}%",
                           label=label, pct=f"{abs(p.get('moneyness',0)):.1f}"),
            "detail": _danger_detail(p, lang),
            "action": "view_position",
        })
        if len(out) >= 3:
            return out[:3]
    return out[:3]


def _build_focus_chips(positions, market, total_pnl, total_realized, total_theta, concentration, lang):
    chips = []
    chips.append({"label": _T(lang, "持仓 P&L"),
                  "value": f"${total_pnl:+,.0f}",
                  "tone": "up" if total_pnl >= 0 else "down"})
    if total_realized:
        chips.append({"label": _T(lang, "已实现"),
                      "value": f"${total_realized:+,.0f}",
                      "tone": "up" if total_realized >= 0 else "down"})
    if total_theta:
        chips.append({"label": _T(lang, "今日 Theta"),
                      "value": f"${total_theta:+,.0f}", "tone": "up"})
    for tk in ("SPY", "QQQ"):
        info = (market.get("indices") or {}).get(tk)
        if info and info.get("prev", 0) > 0:
            chg = (info["price"] - info["prev"]) / info["prev"] * 100
            chips.append({"label": tk, "value": f"{chg:+.1f}%",
                          "tone": "up" if chg >= 0 else "down"})
    if concentration.get("top_pct", 0) >= 60 and concentration.get("top_ticker"):
        chips.append({
            "label": _T(lang, "{tk} 集中度", tk=concentration["top_ticker"]),
            "value": f"{concentration['top_pct']:.0f}%",
            "tone": "neutral",
        })
    near_exp = sum(1 for p in positions
                   if not p.get("closed") and 0 <= p.get("days", 999) <= 7)
    if near_exp:
        chips.append({"label": _T(lang, "未来 7 天到期"),
                      "value": f"{near_exp} {_T(lang, '个')}", "tone": "neutral"})
    return chips[:6]


def _template_concierge(top_3, market, lang):
    """模板版管家（LLM 不可用时的兜底）— 返回 (prose, structured_brief)。
    structured_brief: {headline, sub?, items[], footer?}，items 来自 top_3_focus。"""
    parts = []
    vix = market.get("vix") or {}
    if vix.get("prev", 0) > 0:
        chg = (vix["price"] - vix["prev"]) / vix["prev"] * 100
        if abs(chg) >= 10:
            verb = _T(lang, "跳到") if chg > 0 else _T(lang, "跌到")
            parts.append(_T(lang, "隔夜 VIX {v} {verb} {p} ({c}%)",
                            v=f"{vix['prev']:.1f}", verb=verb,
                            p=f"{vix['price']:.1f}", c=f"{chg:+.0f}"))
    n = len(top_3)
    if n > 0:
        parts.append(_T(lang, "今日 {n} 件事要看", n=n))
    if not parts:
        headline = _T(lang, "持仓平稳，无紧急信号")
    else:
        headline = "，".join(parts) + "。"

    # 从 top_3_focus 派生 priority items（兜底也保证 priority list 有内容）
    items = []
    for e in (top_3 or [])[:4]:
        kind = e.get("kind", "")
        if kind in ("near_strike", "vix_spike", "earnings_imminent"):
            pri = "urgent"
        elif kind == "profit_opportunity":
            pri = "cashflow"
        elif kind in ("newly_itm", "news_alert"):
            pri = "root"
        else:
            pri = "watch"
        action = None
        cta = None
        if e.get("action") == "view_position" and e.get("position_id"):
            action = f"position:{e['position_id']}"
            cta = _T(lang, "看持仓")
        elif e.get("action") == "open_news" and e.get("link"):
            action = f"news:{e['link']}"
            cta = _T(lang, "看原文")
        elif e.get("action") == "view_recommend":
            action = "rec"
            cta = _T(lang, "看推荐")
        items.append({
            "priority": pri,
            "ticker": e.get("label") or e.get("ticker") or "",
            "title": e.get("headline") or "",
            "body": e.get("detail") or "",
            "action": action,
            "cta": cta,
        })

    brief = {"headline": headline, "items": items}
    # 拼 prose 用作 fallback / share view
    prose_parts = [headline]
    for it in items:
        prose_parts.append(f"{it.get('ticker','')} {it.get('title','')}：{it.get('body','')}".strip("：· "))
    prose = "\n\n".join([p for p in prose_parts if p])
    return prose, brief


def _generate_concierge_llm(top_3, market, total_pnl, total_theta, concentration,
                              positions, pos_changes, lang, use_premium_model=False):
    """调 Claude 生成结构化管家简报。失败返回 (None, None)。
    返回 (prose_text, structured_brief)：
      prose_text: 派生 prose（backward compat / share view）
      structured_brief: {headline, sub?, items[], footer?}
    positions: 完整活跃持仓列表（compact 格式塞进 prompt 让管家有全局视野）
    pos_changes: 自上次刷新的新开/平仓 diff，让管家能主动提到刚发生的动作。
    use_premium_model: True 走 Sonnet 4.6（用户付 5🪙 手动刷新），False 走 Haiku 4.5（自动刷新）。"""
    client = _get_anthropic_client()
    if not client:
        print(f"[concierge] llm_skip: no_client lang={lang}", flush=True)
        return None, None
    active = [p for p in (positions or [])
              if not p.get("closed") and p.get("days", 0) >= 0]
    print(f"[concierge] llm_call: lang={lang} top3={len(top_3)} "
          f"active={len(active)} changes={len(pos_changes.get('added',[]))+len(pos_changes.get('removed',[]))}",
          flush=True)

    signal_lines = []
    vix = market.get("vix") or {}
    if vix.get("prev", 0) > 0:
        chg = (vix["price"] - vix["prev"]) / vix["prev"] * 100
        signal_lines.append(f"VIX: {vix['prev']:.1f} -> {vix['price']:.1f} ({chg:+.0f}%)")
    signal_lines.append(f"Portfolio unrealized P&L: ${total_pnl:+,.0f}, today Theta: ${total_theta:+,.0f}")
    if concentration.get("top_pct", 0) >= 40:
        signal_lines.append(f"{concentration['top_ticker']} concentration: {concentration['top_pct']:.0f}%")

    # 全部活跃持仓 — 让 LLM 有全局视野，而不仅看 top 3
    # 每行带 pid=...，让 LLM 在 action 字段用真实 position_id（避免 bs 出 TSLA_put_415_4d 这种瞎拼）
    if active:
        signal_lines.append(f"\nAll active positions ({len(active)}) — 引用持仓时 action 用对应 pid:")
        for p in active:
            label = p.get("label", "")
            days = p.get("days", 0)
            pnl = p.get("pnl", 0)
            pnl_pct = p.get("pnl_pct", 0)
            delta = p.get("delta", 0)
            theta = p.get("daily_theta", 0)
            money = p.get("moneyness", 0)
            # 构造真实 position_id
            expiry = p.get("expiry")
            if hasattr(expiry, "isoformat"): expiry = expiry.isoformat()
            pid = f"{p.get('ticker','')}_{p.get('type','')}_{_fmt_strike(p.get('strike',0))}_{expiry}"
            # money 是 (spot - strike) / strike × 100：put 为正→ITM、负→OTM；call 反之
            is_itm = (p.get("type") == "call" and money < 0) or (p.get("type") == "put" and money > 0)
            if is_itm:
                money_tag = f" [ITM {abs(money):.1f}%]"
            elif abs(money) < 3:
                money_tag = f" [ATM {money:+.1f}%]"
            else:
                money_tag = f" [OTM {abs(money):.1f}%]"
            signal_lines.append(
                f"  - [pid={pid}] {label} · {days}d · ${pnl:+,.0f} ({pnl_pct:+.0f}%) · "
                f"Δ{delta:+.2f} · θ${theta:+.1f}{money_tag}"
            )

    # 持仓变化 — 让管家主动提到刚发生的动作
    added = pos_changes.get("added") or []
    removed = pos_changes.get("removed") or []
    if added or removed:
        signal_lines.append("\nRecent position changes (since last brief):")
        for it in added:
            signal_lines.append(f"  + 新开: {it.get('label','')}")
        for it in removed:
            signal_lines.append(f"  - 平仓/移除: {it.get('label','')}")

    if top_3:
        signal_lines.append("\nToday's top 3 focus:")
        for idx, e in enumerate(top_3[:3], 1):
            signal_lines.append(f"  {idx}. {e['icon']} {e['headline']} - {e['detail']}")
    else:
        signal_lines.append("\n(no urgent signals)")

    news = market.get("news") or []
    if news:
        signal_lines.append("\nRecent news on your tickers (24h):")
        for n in news[:6]:
            signal_lines.append(f"  - {n['ticker']} ({n['publisher']}, {n['hours_ago']}h): {n['title']}")

    lang_word = {"en": "English", "zh_tw": "繁體中文"}.get(lang, "简体中文")

    system_prompt = (
        f"你是「包租公管家」——给用美股期权赚租金的散户写早安顾问，{lang_word}回复，亲切像老友。\n"
        "**严格输出 JSON**（不要 markdown 代码块），schema:\n"
        "{\n"
        "  \"headline\": \"≤80 字核心结论，**用粗体**点关键 ticker+数字\",\n"
        "  \"items\": [  // 3-5 个\n"
        "    {\n"
        "      \"priority\": \"urgent|cashflow|root|watch\",\n"
        "      \"ticker\": \"ticker+strike+type 或空字符串\",\n"
        "      \"title\": \"10-18 字标题\",\n"
        "      \"body\": \"30-70 字解释，必带数字（DTE/PnL/距行权/Θ）\",\n"
        "      \"action\": \"rec | position:<pid> | null\",\n"
        "      \"cta\": \"按钮文案，没 action 就 null\"\n"
        "    }\n"
        "  ],\n"
        "  \"footer\": \"可选，一句话环境/心态\"\n"
        "}\n"
        "**priority 含义**：urgent=今天必动（距行权<3%、≤7d 到期且亏损、财报≤2d）；"
        "cashflow=守住别动（Theta 流入、≥70% 锁利、稳健 ITM 有缓冲）；"
        "root=结构性问题需中期审（长短期互锤、方向错配、ITM 但缓冲不够）；"
        "watch=平稳放着。\n"
        "**必有 1 个 urgent**（没紧急就放最值得关注的）；有显著盈利 → 必有 1 cashflow。\n"
        "**集中度是策略选择不是问题** — Wheel 蓝筹、长期看好单票的用户本来就偏集中。"
        "数据里给的集中度只作背景信息，不要因为单一百分比就归 root 或 urgent；"
        "只在叠加方向性风险时（重仓 ticker 财报临近 / 宏观事件 / 已 ITM 且缓冲薄）才提，措辞中性 — 不说\"过高\"\"分散\"。\n"
        "**action**：看持仓用 `position:<pid>`——**pid 必须从 `All active positions` 行里 `[pid=...]` 复制**，不要瞎拼或拼缩写；"
        "找新机会/调仓用 `rec`；无明确下一步 → null。\n"
        "**只用我给的数字**，别编。All active positions 给你做全局判断用，不要逐张列。"
        "Recent changes 有就挑 1 条最值得讲的体现在 headline 或 body。\n"
        "**时间表达硬约束**：天数严格直译。`{X}d` 写「剩 X 天到期」或「剩 X 天」。"
        "**禁止**用「明天/今天/快到了/迫在眉睫/马上」等模糊词替代具体天数 — 哪怕 X=1 也写「剩 1 天到期」。"
        "(English: \"X days to expiry\". 繁中：「剩 X 天到期」。)\n"
        "**\"已成定局\" 类终结措辞硬约束**：仅当 |Δ| ≥ 0.85 **且** 距 strike > 8% ITM 时才允许说"
        "「已成定局 / 接货定了 / 无法回头 / 认命 / 板上钉钉 / 翻盘无望」等终结性判断。"
        "其他情况一律用「概率偏高 / 接货风险大 / 准备应对」等留余地的措辞 — "
        "即使是 -50% 浮亏，只要 |Δ| < 0.85 就还有挣扎空间，不能宣判。"
    )

    user_prompt = "今早信号:\n" + "\n".join(signal_lines) + (
        f"\n\n严格 JSON 输出，items 3-5 个，{lang_word}。"
    )

    # 模型选择：付费手动刷新（brief_refresh）→ Sonnet 4.6 推理更准；自动 5min 刷新 → Haiku 4.5 省成本
    model_id = "claude-sonnet-4-6" if use_premium_model else "claude-haiku-4-5-20251001"

    # 把诊断信息暂存到 module-level dict，让响应能带回（不靠 Vercel logs）
    global _last_llm_diag
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model_id,
            max_tokens=1600,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
                # 用 assistant prefill 强制 JSON 起始，禁止 LLM 加 ```json``` 或 narrative
                {"role": "assistant", "content": "{"},
            ],
        )
        elapsed = time.time() - t0
        print(f"[concierge] llm_done: model={model_id} lang={lang} elapsed={elapsed:.2f}s", flush=True)
        _last_llm_diag = {"phase": "done", "model": model_id, "elapsed_s": round(elapsed, 2)}
        # prefill `{` 不会出现在 response.content 里，需要手动 prepend
        raw = (resp.content[0].text if resp.content else "")
        text = ("{" + raw).strip()
        if not text:
            _last_llm_diag = {"phase": "empty", "model": model_id, "elapsed_s": round(elapsed, 2)}
            return None, None
        prose, brief = _parse_concierge_json(text, lang)
        if not brief or not brief.get("items"):
            print(f"[concierge] llm_parse_fail: lang={lang} text_head={text[:120]!r}", flush=True)
            _last_llm_diag = {"phase": "parse_fail", "model": model_id,
                              "elapsed_s": round(elapsed, 2), "text_head": text[:200]}
            return None, None
        _last_llm_diag = {"phase": "ok", "model": model_id, "elapsed_s": round(elapsed, 2),
                          "items": len(brief.get("items") or [])}
        return prose, brief
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[concierge] llm_error: model={model_id} {type(e).__name__}: {e} elapsed={elapsed:.2f}s", flush=True)
        _last_llm_diag = {"phase": "error", "model": model_id, "error_type": type(e).__name__,
                          "error_msg": str(e)[:200], "elapsed_s": round(elapsed, 2)}
        return None, None


# 最后一次 LLM 调用的诊断信息（debug 用，回到响应里）
_last_llm_diag = None


def _parse_concierge_json(text, lang):
    """LLM 输出的 JSON 字符串 → (prose_text, structured_brief)。
    宽容解析：剥 markdown 代码块、找 outer {}、修复 truncated JSON。失败返回 (None, None)。"""
    s = text.strip()
    # 剥 markdown code fence
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    # 找第一个 {
    i = s.find("{")
    if i < 0:
        return None, None
    s = s[i:]
    # 优先尝试完整 JSON
    data = None
    try:
        data = json.loads(s)
    except Exception:
        # 修复 truncated JSON：max_tokens 截断常见，items 数组可能在某条 item 中间断
        # 策略：找最后一个完整 item（看 `},`），截到那里 + 补 `]}` 闭合
        try:
            # 找 "items": [ 的开始位置
            m = re.search(r'"items"\s*:\s*\[', s)
            if m:
                arr_start = m.end()
                # 从 arr_start 起，找出所有 top-level `}` 的位置（item 边界）
                depth = 0
                in_str = False
                escape = False
                last_close = -1
                for idx in range(arr_start, len(s)):
                    ch = s[idx]
                    if escape:
                        escape = False; continue
                    if ch == "\\" and in_str:
                        escape = True; continue
                    if ch == '"':
                        in_str = not in_str; continue
                    if in_str:
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            last_close = idx
                if last_close > 0:
                    repaired = s[:last_close+1] + "]}"
                    data = json.loads(repaired)
        except Exception:
            data = None
    if data is None:
        return None, None
    if not isinstance(data, dict):
        return None, None
    headline = (data.get("headline") or "").strip()
    sub = (data.get("sub") or "").strip() or None
    footer = (data.get("footer") or "").strip() or None
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return None, None
    items = []
    valid_pri = {"urgent", "cashflow", "root", "watch"}
    for it in raw_items[:6]:
        if not isinstance(it, dict):
            continue
        pri = (it.get("priority") or "watch").strip().lower()
        if pri not in valid_pri:
            pri = "watch"
        items.append({
            "priority": pri,
            "ticker": (it.get("ticker") or "").strip(),
            "title": (it.get("title") or "").strip(),
            "body": (it.get("body") or "").strip(),
            "action": (it.get("action") or None) or None,
            "cta": (it.get("cta") or "").strip() or None,
        })
    if not items or not headline:
        return None, None
    brief = {"headline": headline, "items": items}
    if sub: brief["sub"] = sub
    if footer: brief["footer"] = footer
    # 派生 prose
    prose_parts = [headline]
    if sub: prose_parts.append(sub)
    for it in items:
        seg = " ".join([s for s in [it.get("ticker"), it.get("title")] if s]).strip()
        if it.get("body"):
            prose_parts.append(f"{seg}：{it['body']}" if seg else it["body"])
        elif seg:
            prose_parts.append(seg)
    if footer: prose_parts.append(footer)
    prose = "\n\n".join(prose_parts)
    return prose, brief


def _generate_morning_brief(positions, prices, total_pnl, total_realized, total_theta,
                              state=None, lang="zh", force_refresh=False):
    """结构化早安简报 — 返回 dict（管家文 + top 3 + chips + 14 天日历 + snapshot）。
    Concierge 文本一天一次，缓存到 brief_snapshot；其它信号（top 3 / chips / 日历）每次重算。
    "今天" 用美东市场时区 — 服务器 UTC 早上 4 点已经是新一天，但盘前 4amET 用户还视为"昨晚"，
    用 UTC 会导致美东时间凌晨那段窗口看到的是真正昨天生成的 brief 但不刷新。
    force_refresh=True 时跳过 cache 强行重新调 LLM（用户花 5 金币手动刷新管家走这条路径）。"""
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        today = date.today()
    today_iso = today.isoformat()
    state = state if isinstance(state, dict) else {}

    # news 和 VIX 都是独立 IO（yfinance），并行启动省 ~500ms
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        news_fut = ex.submit(_fetch_position_news, positions)
        vix_fut = ex.submit(_fetch_vix_quote)
        news = news_fut.result()
        vix = vix_fut.result()
    market = {"indices": prices, "vix": vix, "news": news}
    concentration = _compute_concentration(positions)
    calendar = _compute_calendar_14d(positions, today)
    yesterday_snap = _load_brief_snapshot(state)
    diff_events = _compute_diff_events(yesterday_snap, positions, market, lang)
    # news_alert events 拼到 diff_events 前面（priority 80，比 VIX 跳变 85 低，比 dte 70 高）
    news_alerts = _detect_news_alerts(news, lang)
    diff_events = news_alerts + diff_events
    top_3 = _rank_top_3_focus(diff_events, positions, lang)
    chips = _build_focus_chips(positions, market, total_pnl, total_realized, total_theta,
                                concentration, lang)
    # 持仓变化（新开 / 平仓 / 编辑）— 触发重新生成 + 喂给 LLM 让它能主动提到
    pos_changes = _compute_position_changes(yesterday_snap, positions)

    # Concierge 一天一次：今天已生成过就复用，不重新调 LLM（避免跳动 + 省钱）
    # concierge_version: prompt 改了就 bump，让旧 cache 失效
    # bump 6: 修缓存中毒 — template fallback 不再被无条件缓存
    # bump 7: 持仓变化触发重新生成 + prompt 加全部活跃持仓 + Recent changes section
    # bump 8: LLM 输出结构化 JSON (concierge_brief)，前端渲染 priority list
    # bump 9: 缓存键从 UTC date 换成 America/New_York date — 旧 UTC snap 在
    #         美东时间凌晨那段窗口被错误复用（同 UTC 日期 → 命中昨天的文）。
    #         强制失效一次，确保用户今早登陆拿到真正"今天"的 brief。
    # bump 10: prompt 加时间表达硬约束（{X}d 必须直译为「剩 X 天」） + "已成定局"
    #          类终结措辞仅 |Δ|≥0.85 且 ITM>8% 才允许；ITM/ATM/OTM tag 带具体距 strike %；
    #          force_refresh（用户付 5🪙）走 Sonnet 4.6，自动刷新继续 Haiku 4.5。
    CONCIERGE_VERSION = 10
    cached_text = None
    cached_brief = None
    cached_by = None
    snap_by = yesterday_snap.get("generated_by")
    if (not force_refresh  # 用户付费手动刷新 → 强制重新调 LLM
            and yesterday_snap.get("date") == today_iso
            and yesterday_snap.get("concierge_text")
            and yesterday_snap.get("concierge_lang") == lang
            and yesterday_snap.get("concierge_version") == CONCIERGE_VERSION
            and snap_by != "template"  # template 兜底不算有效 cache，下次刷新会重试 LLM
            and not pos_changes["has_changes"]):  # 持仓有增删 → 强制重新生成
        cached_text = yesterday_snap.get("concierge_text")
        cached_brief = yesterday_snap.get("concierge_brief")  # 可能 None（旧 cache）
        cached_by = snap_by or "cached"

    if cached_text and cached_brief:
        concierge_text = cached_text
        concierge_brief = cached_brief
        by = cached_by
    else:
        concierge_text, concierge_brief = _generate_concierge_llm(
            top_3, market, total_pnl, total_theta,
            concentration, positions, pos_changes, lang,
            use_premium_model=force_refresh)
        by = "llm"
        if not concierge_text or not concierge_brief:
            concierge_text, concierge_brief = _template_concierge(top_3, market, lang)
            by = "template"

    snap_date = yesterday_snap.get("date")
    snap_lang = yesterday_snap.get("concierge_lang")
    snap_ver = yesterday_snap.get("concierge_version")
    n_items = len((concierge_brief or {}).get("items") or [])
    print(f"[concierge] brief: by={by} lang={lang} today={today_iso} "
          f"snap_date={snap_date} snap_lang={snap_lang} snap_ver={snap_ver} "
          f"snap_by={snap_by} want_ver={CONCIERGE_VERSION} items={n_items} "
          f"changes={'+' + str(len(pos_changes['added'])) + '/-' + str(len(pos_changes['removed']))}",
          flush=True)

    next_snap = _make_brief_snapshot(positions, market, today)
    # 只在 LLM 成功或复用 LLM cache 时才写 concierge_* 字段。
    # template 兜底不缓存，让下次 refresh（5min 后）重新尝试 LLM；
    # diff 用的 positions/vix snap 仍写入，跨日 diff 不受影响。
    if by != "template":
        next_snap["concierge_text"] = concierge_text
        next_snap["concierge_brief"] = concierge_brief
        next_snap["concierge_lang"] = lang
        next_snap["concierge_version"] = CONCIERGE_VERSION
        next_snap["generated_by"] = by

    return {
        "concierge_text": concierge_text,
        "concierge_brief": concierge_brief,
        "generated_by": by,
        "top_3_focus": top_3,
        "chips": chips,
        "calendar_14d": calendar,
        "today_date": today.isoformat(),
        "next_snapshot": next_snap,
        "_llm_diag": _last_llm_diag,  # 临时诊断字段：让用户能在响应里看 LLM 状态
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
                    "has_anthropic_key": bool(_os.environ.get("ANTHROPIC_API_KEY")),
                    "anthropic_key_len": len(_os.environ.get("ANTHROPIC_API_KEY", "")),
                    "anthropic_client_ready": _get_anthropic_client() is not None,
                }
            elif action == "scan_multi":
                # v2.0 #7 多 ticker 单次扫描 — 跨标的找最佳候选
                result = scan_multi(payload)
                self._send_json(200, result)
                try:
                    user_id = payload.get("user_id")
                    user_email = payload.get("user_email")
                    if user_id:
                        tks = payload.get("tickers") or []
                        meta = {"tickers": ",".join(tks[:5]), "intent": payload.get("intent")}
                        log_usage_event(user_id, user_email, "scan_multi", meta)
                except Exception as _e:
                    try: print(f"[usage] scan_multi log skip: {_e}", flush=True)
                    except Exception: pass
                return
            elif action == "recommend":
                result = recommend(payload)
                # 先把响应发给用户 — usage 埋点不该阻塞用户拿到结果。
                # serverless flush 语义不保证立即发送，但配合 log timeout=2s 双保险。
                self._send_json(200, result)
                try:
                    try: self.wfile.flush()
                    except Exception: pass
                    user_id = payload.get("user_id")
                    user_email = payload.get("user_email")
                    if user_id or user_email:
                        cands = result.get("candidates") or []
                        top_tier = None
                        if cands:
                            try:
                                top_tier = (cands[0].get("verdict") or {}).get("tier")
                            except Exception:
                                top_tier = None
                        meta = {
                            "ok": "error" not in result,
                            "ticker": payload.get("ticker"),
                            "goal": payload.get("intent"),
                            "risk": payload.get("risk"),
                            "direction": payload.get("direction"),
                            "timeframe": payload.get("timeframe"),
                            "candidates_n": len(cands),
                            "top_tier": top_tier,
                        }
                        if "error" in result:
                            meta["error_kind"] = result.get("error_kind") or "unknown"
                            meta["error"] = (result.get("error") or "")[:160]
                        log_usage_event(user_id, user_email, "recommend", meta)
                except Exception as _e:
                    try: print(f"[usage] recommend log skip: {_e}", flush=True)
                    except Exception: pass
                return
            elif action == "log_event":
                # 前端主动埋点：login / first_login / review 等
                ev = payload.get("event") or ""
                allowed = {"login", "first_login", "review", "morning_brief_view"}
                if ev not in allowed:
                    result = {"ok": False, "error": "event not allowed"}
                else:
                    log_usage_event(
                        payload.get("user_id"),
                        payload.get("user_email"),
                        ev,
                        payload.get("metadata") or {},
                    )
                    result = {"ok": True}
            elif action == "admin_stats":
                result = admin_stats(payload)
            elif action == "get_balance":
                result = get_coin_balance(payload)
            else:
                result = compute(payload)
                # brief_refresh 用户付费手动刷新管家：仅当真的走了 LLM 才记录扣费
                if result.get("brief_refresh_charged"):
                    try:
                        log_usage_event(
                            payload.get("user_id"),
                            payload.get("user_email"),
                            "brief_refresh",
                            {"cost": 5, "by": (result.get("morning_brief") or {}).get("generated_by"),
                             "lang": payload.get("lang") or "zh"},
                        )
                    except Exception as _e:
                        try: print(f"[usage] brief_refresh log skip: {_e}", flush=True)
                        except Exception: pass
            self._send_json(200, result)
        except Exception as e:
            self._send_json(500, {
                "error": str(e),
                "trace": traceback.format_exc(),
            })
