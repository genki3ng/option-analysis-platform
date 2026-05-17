# 🏠 包租公 · Landlord

**把你的股票"租"出去，每周收"租金"** —— 期权新手友好的 Covered Call / CSP / Wheel 可视化工具。

**Live:** https://trade.congyangwang.com
**App:**  https://trade.congyangwang.com/app

---

## 包租公算法 1.1

不是黑盒，是八个能讲清楚的因子。

```
包租公分 = 年化租金 × 安全度^1.5 × DTE 甜蜜区 × Delta 甜蜜区
       × IV rank × 流动性(spread×OI×vol) × 财报因子 × 回测胜率
```

| # | 因子 | 设计意图 |
|---|---|---|
| 01 | 年化租金        | `premium ÷ collateral × (365/days)` — 横向可比 |
| 02 | 安全度^1.5      | BS 真实 `N(d2)`，1.5 次幂强调损失厌恶 |
| 03 | DTE 甜蜜区      | 14d = 峰值 1.20×，7-21d 周租周期 |
| 04 | Delta 甜蜜区    | 0.22 = 峰值 1.15×，0.15-0.30 奶牛区 |
| 05 | IV rank         | ≥70 给 1.20×；≤20 扣 0.85× |
| 06 | 流动性 (v1.1)   | spread × OI × volume 复合 — OI<10 → ×0.5；今日 0 成交 → ×0.65 |
| 07 | 财报因子        | 保守 = ×0 硬否决；平衡 = ×0.55；激进 = ×0.78 |
| 08 | 回测胜率        | 过去 6 个月模拟，≥75% +12%，<45% -15% |

### v1.1 vs v1.0
- 流动性从单一 spread% 升级为 **spread × OI × volume** 复合
- 单看 spread 会被骗：纸面 5% spread + OI=0 = 挂单一天不成交
- OI 分档：≥1000 → 1.10×，≥500 → 1.00×，≥50 → 0.85×，&lt;10 → 0.50×
- Volume 分档：≥200 → 1.05×，≥50 → 1.00×，0 → 0.65×（价格 stale）

**设计原则**
1. 稳定的周租 > 一次性的暴利
2. 损失厌恶（cons 多于 pros 再扣 1 分）
3. 保守模式真保守（财报跨期直接否决）
4. 一个数字（包租公分）就够，但展开可见每项贡献

详见首页 [`/#algo`](https://trade.congyangwang.com/#algo)。

---

## Stack

- **Frontend:** vanilla HTML/CSS/JS, Chart.js via CDN
- **Backend:** Python serverless function (`/api/state`)
- **Market data:** Schwab Market Data API（主，实时） → Yahoo via curl_cffi → yfinance（兜底）
- **Deploy:** Vercel（custom domain via Namecheap CNAME）

## Routes

| URL | 内容 |
|---|---|
| `/` | 首页（产品介绍 + 包租公算法 1.0 方法论） |
| `/app` | 应用面板（持仓、推荐指数、复盘） |
| `/api/state` | Python serverless API |
| 其他任意路径 | 兜底回首页（避免 404，老分享链接也能落地） |

## 核心功能

- 📊 **实时持仓监控** — Greeks、P&L、损益曲线、距行权温度计
- 🏠 **包租公推荐指数** — 五星 tier 排序 + 完整包租公分拆解
- 📚 **5 大佬策略预设** — 一键填表（价值哥 LEAPS / 死多头 / Wheel CSP / 周收权利金 / 区间震荡）
- ☀️ **每日早安 Brief** — 市场 / 持仓 / 风险预警
- 📝 **Trade Journal** 笔记 + 公开分享链接
- 📚 **25 个期权术语小白指南**（ITM/OTM/Wheel/LEAPS…）
- 🔗 **跨设备同步**（File System Access API → Google Drive 文件夹）
- 🌍 简中 / 繁中 / English · ☀️ 白天 / 🌙 夜间（默认夜间）

## 设计语言

整站遵循 Linear（留白 + 排版） / Vercel（模块结构） / Stripe（信息拆解）。
显式回避紫蓝渐变、三栏 feature grid、icon-in-colored-circle 等 AI 模板气味。
单色暖金 `#E6B86A` 作为唯一强调色。

## 隐私

- 数据全存浏览器 localStorage
- Vercel function 是无状态的（不存任何 PII）
- 其他人打开同一网址 → 看到他们自己的数据

## ⚠️ 免责

**仅供学习研究，不构成投资建议。** 期权交易有亏损全部本金甚至更多的风险。所有数据 / 推荐基于市场数据 + 数学模型，无法预测未来。
