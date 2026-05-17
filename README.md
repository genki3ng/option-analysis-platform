# 🏠 包租公 · Landlord

**把你的股票"租"出去，每周收"租金"** —— 期权新手友好的 Covered Call / CSP / Wheel 可视化工具 + 推荐引擎。

**Live:** https://trade.congyangwang.com
**App:**  https://trade.congyangwang.com/app

---

## 包租公算法 1.3

不是黑盒，是八个能讲清楚的因子。

```
包租公分 = 年化租金 × 安全度^1.5 × DTE 甜蜜区 × Delta 甜蜜区
       × IV rank × 流动性(spread×OI×vol) × 财报因子 × 回测胜率
```

| # | 因子 | 设计意图 |
|---|---|---|
| 01 | 年化租金        | `premium ÷ collateral × (365/days)` — 横向可比 |
| 02 | 安全度^1.5      | BS 真实 `N(d2)`，1.5 次幂强调损失厌恶 |
| 03 | DTE 甜蜜区 *(v1.3)* | **跟用户表单 timeframe 自适应** — 周收选 14d 峰值，月度选 30d 峰值 |
| 04 | Delta 甜蜜区 *(v1.3)* | **跟 IV rank 自适应** — IV 高时甜蜜区右移（用户能拿更多 premium），低时左移（求安全） |
| 05 | IV rank         | ≥70 给 1.20×；≤20 扣 0.85× |
| 06 | 流动性 *(v1.1+)* | spread × OI × volume 复合 — OI<10 → ×0.5；今日 0 成交 → ×0.65 |
| 07 | 财报因子 *(v1.2)* | **距财报天数衰减**（≤2/≤7/≤14/≤21/>21 五档），不再一刀切 |
| 08 | 回测胜率 *(v1.B)* | **12 个月窗口** + 二分查找精确 Δ + BS 真实 premium，输出 `theoretical_pop` + `calibration_ratio` |

**版本时间线**
- v1.0 → v1.1: 流动性从单一 spread% → spread × OI × volume 复合
- v1.1 → v1.2: 财报因子从「跨期就 ×0」→ 距财报天数衰减
- v1.2 → v1.3: DTE / Delta 甜蜜区跟用户 timeframe / IV rank 自适应
- v1.B (子批 B): POP 校准 + Exit plan 模板

**设计原则**
1. 稳定的周租 > 一次性的暴利
2. 损失厌恶（cons 多于 pros 再扣 1 分）
3. 保守模式真保守（≤5 天跨财报硬否决）
4. 一个数字（包租公分）就够，但展开可见每项贡献

详见首页 [`/#algo`](https://trade.congyangwang.com/#algo)。

---

## ⚙️ 核心功能

### 推荐 & 决策辅助
- 🏠 **包租公推荐指数** — 五星 tier 排序 + 完整包租公分拆解 + 数据源降级 pill
- 📊 **加仓预览** — 选候选合约时先看「加进组合后」的集中度 / Greeks / 保证金 / 收益变化
- ⚖️ **候选对比** — 勾 2-5 个候选浮 pill → 弹表 12 指标横向对比，绿/红高亮最优最差
- 🛡 **POP 校准** — 历史模拟胜率 vs BS 理论 PoP，比值 < 0.95 弹"理论偏乐观"警示
- 🎯 **Exit plan 自动生成** — 按 risk × kind 矩阵给出锁利 / 止损 / Roll 触发条件
- 📚 **5 大佬策略预设** — 一键填表（价值哥 LEAPS / 死多头 / Wheel CSP / 周收权利金 / 区间震荡）

### 持仓监控
- 📈 **实时持仓监控** — Greeks、P&L、损益曲线、距行权温度计
- 🔁 **Wheel 闭环提示** — 100+ 股 / CSP 被指派后自动建议"卖 covered call"
- 📐 **简洁 / 完整双密度模式** — 一键切换信息密度
- 📝 **Trade Journal** 笔记 + 公开分享链接

### 早安简报 v2 *(包租公管家 + LLM)*
- ☀️ **包租公管家** — Claude Haiku 4.5 生成 ≤80 字人格化早安摘要
- 🎯 **今日要关注 Top 3** — 跨日 diff 找质变事件（80% 利润 / 进 7d 窗口 / 新 ITM / 财报临近 / VIX 跳涨）
- 📅 **未来 14 天关键日历** — 财报点 + 到期点
- 💚 **健康 chips** — 总 P&L / 已实现 / 每日 Theta / SPY/QQQ / 集中度 / 7d 到期数

### 账户 & 同步
- 🔐 **Google OAuth 登录** — Supabase + RLS，只有你能读自己那行
- ☁ **多设备实时同步** — postgres_changes 订阅，A 设备改 B 设备秒到
- 📥 **本地降级** — 不登录纯 localStorage，依然可用
- 💾 **一键导出 JSON 备份**
- 📊 **账户元数据** — 总现金 / 已持仓股数 / 风险偏好等跨设备同步

### 通用
- 📚 **25 个期权术语小白指南**（ITM/OTM/Wheel/LEAPS/Theta 衰减/Vol skew…）
- 🌍 **三语**：简中 / 繁中 / English
- 🌙 **白天 / 夜间**（默认夜间）

---

## 🛠 Stack

- **Frontend:** vanilla HTML/CSS/JS（不打包不构建），Chart.js via CDN，Supabase JS via CDN
- **Backend:** Python serverless function (`/api/state.py`)，无框架
- **Market data:** Schwab Market Data API（主，实时）→ Yahoo via curl_cffi → yfinance（兜底）
- **Auth + DB:** Supabase（Postgres + RLS + Realtime + Google OAuth）
- **LLM:** Anthropic Claude Haiku 4.5（早安简报 concierge，~$0.001/用户/天）
- **Deploy:** Vercel（GitHub auto-deploy on main）
- **Analytics:** Vercel Web Analytics + Speed Insights
- **Domain:** trade.congyangwang.com（Cloudflare DNS）

## Routes

| URL | 内容 |
|---|---|
| `/` | 首页（产品介绍 + 算法方法论 + 隐私） |
| `/app` | 应用面板（持仓 / 推荐 / 复盘 / 早安简报） |
| `/api/state` | Python serverless API |
| 其他任意路径 | 兜底回首页（避免 404，老分享链接也能落地） |

---

## 🔒 隐私

- **不登录**：数据全存浏览器 localStorage，永不上传服务器
- **登录后**：数据加密存储在 Supabase（Postgres），RLS 策略兜底——**只有你能读写自己那行**，连我们也看不到
- **后端无 PII**：Vercel function 完全无状态，每次请求处理完即释放，不存任何身份信息
- **不卖数据、不投放广告、不做用户画像 — 永远**
- 隐私问题：hi@congyangwang.com

详见 [`/#privacy`](https://trade.congyangwang.com/#privacy) 区块。

---

## 🎨 设计语言

整站遵循 Linear（留白 + 排版）/ Vercel（模块结构）/ Stripe（信息拆解）。
显式回避紫蓝渐变、三栏 feature grid、icon-in-colored-circle 等 AI 模板气味。
单色暖金 `#E6B86A` 作为唯一强调色。
2026-05 完成两轮深度精修：backdrop blur 玻璃感、focus ring 键盘可达、伪元素分隔线、cubic-bezier 自然减速曲线。

---

## 📂 Repo 结构

```
.
├── index.html      ← 主 app（~10000 行，包含 CSS / JS / i18n / Supabase）
├── intro.html      ← 落地页（产品介绍 + 算法 + 隐私）
├── api/state.py    ← 唯一后端文件（~2500 行）
├── scripts/
│   └── schwab_auth.py  ← 一次性脚本，Schwab refresh_token 过期时本地跑
├── requirements.txt
├── vercel.json
├── CLAUDE.md       ← 给 Claude session 的长期项目说明
├── HANDOFF.md      ← 短期 session 间协作的记账本
└── README.md
```

## ⚠️ 免责

**仅供学习研究，不构成投资建议。** 期权交易有亏损全部本金甚至更多的风险。所有数据 / 推荐基于市场数据 + 数学模型，无法预测未来。决策前请自行验证 / 咨询持牌顾问。
