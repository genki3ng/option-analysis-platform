# 🏠 包租公 · Landlord

**把你的股票"租"出去，每周收"租金"** —— 期权小白也能上手的 Covered Call / CSP / Wheel 可视化工具。

**Live:** https://trade.congyangwang.com
**Intro:** https://trade.congyangwang.com/intro

## Stack
- **Frontend:** vanilla HTML/CSS/JS, Chart.js via CDN
- **Backend:** Python serverless function (`/api/state`)
- **Market data:** yfinance (实时 chain) + Massive API (30 天历史价位)
- **Deploy:** Vercel

## 核心功能

- 📊 实时持仓监控（Greeks、P&L、损益曲线）
- 🎯 AI 期权推荐（5 步问答 + 5 大佬策略预设）
- ☀️ 每日早安 Brief（市场 / 持仓 / 风险预警）
- 📝 Trade Journal 笔记 + 公开分享链接
- 📚 25 个期权术语小白指南（ITM/OTM/Wheel/LEAPS）
- 🔗 跨设备同步（File System Access API）
- 🌍 简中 / 繁中 / English · ☀️ 白天 / 🌙 夜间

## 隐私

- 数据全存浏览器 localStorage
- Vercel function 是无状态的（不存任何 PII）
- 其他人打开同一网址 → 看到他们自己的数据

## ⚠️ 免责

**仅供学习研究，不构成投资建议。** 期权交易有亏损全部本金甚至更多的风险。
