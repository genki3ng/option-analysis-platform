# 包租公算法 Changelog

> 每个 ship 节点的简要说明 + 算法理念变迁。最新在前。

---

## v2.0 (2026-05-19) — 出场策略 / Roll / 多 ticker / 财报红利

**主题**：让"卖一张期权"的整个生命周期可控。从入场（v1.9 EV/VRP 评分）扩到 **出场（3 人设）、续命（Roll 建议）、规模化（多 ticker 扫描）、财报红利（IV crush 估算）**。

### Core changes

**1. 3 个出场人设 (`exit_style`)**
- 🏠 **早收租派 `early_close`**（默认）：50% 早平 + delta 一升就 roll + 接货红线
- 🏘️ **接货 Wheel 派 `wheel_assign`**：愿被指派转 CC，仅在标的暴跌 / 财报 / 破位时止损
- 💰 **死磕到期派 `hold_to_expiry`**：持到 expire，吃满租金
- Exit plan 输出 4 条事件触发线（早收租 / DTE 换租 / 房客违约 / 红线），按人设动态阈值

**2. 🔄 Roll 建议器**
- 持仓卡新增 🔄 按钮，点击触发"为这张找 Roll 候选"
- 后端 `req.roll_for` 约束：expiry ≥ 原 + 14d，strike 更 OTM
- 每个候选输出 `roll_net_credit`：新 premium - 平当前的成本（正=拿额外现金）

**3. 🔍 多 ticker 单次扫描**
- Ticker 输入框支持 `TSLA,NVDA,GOOG` 逗号分隔（最多 5 个）
- 后端 `scan_multi` action：逐一调 recommend → 合并 → 跨标的按 rent_score 排序
- 一次知道"哪个标的当前最值得卖"，省去手动切换

**4. 💎 财报 IV crush 红利估算**
- 跨财报候选额外算 `earnings_crush_capture_$`
- 用经验值 40% IV crush + BS 重算财报后期权价 → 差额 = 卖方红利
- Verdict pro 显示"💎 财报 IV crush 红利估 +$X/张"

**5. Score-verdict 统一**
- Tier（星级）改由 **rent_score 百分位** 驱动（≥80% 5星 / ≥60% 4星 / ...）
- 旧的 weight-based tier 仅作 cons/pros 文案，不再决定排序
- Veto 仍硬封顶（earnings / capital → ≤2 星）
- 绝对值兜底（rent_score < 0.5 → 1 星）防止极差候选靠百分位拿高星

**6. 回测跟 exit_plan 同步**
- `_backtest_strategy` 路径模拟：early_close / wheel_assign 走 50% 早平 + DTE cutoff
- hold_to_expiry 走旧的"持到到期"假设
- 输出新增 `early_close_rate`：多少 % 通过早平退场

**7. DTE 甜蜜区 IV 自适应**
- IV rank ≥70 → 甜蜜区中心 × 0.70（滑向短 DTE，捕 IV crush）
- IV rank ≤30 → 中心 × 1.30（滑向长 DTE，拉长 theta 收割）
- 30-70 不变

### Algorithm version: 1.9 → 2.0

---

## v1.9 (2026-05-19) — EV/VRP base + 资金硬上限 + 杠杆 ETF + 压测 + willing-to-own

**主题**：从"收多少租"升级到"真正赚多少 edge"。score base 从 `period_roc × prob_safe^1.5 × iv_f` 换成 **年化超额收益（EV vs 实际波动率）**。

### Core changes

**1. EV/VRP base 重写 `_landlord_score`**
- 公式：`EV_annualized = (mid − BS_fair_value_at_realized_vol_30d) / collateral × (365/days) × 100`
- 经济意义：你比"市场用真实波动率算出来的公平价"多收的边际，年化
- VRP（IV / RV）取代 IV Rank 作为核心信号
- 用 RV (30d) 当作"无信息基准"算 fair value
- backward compat：realized_vol 不可用时回退 v1.4 公式

**2. 风险三件套**
- **资金硬上限**：候选若被指派需要的现金 vs 用户填的 "available_margin"。> 100% veto → tier ≤ 2 + 显式 cons
- **压力测试**：每候选算标的 -5% / -10% + IV pump 15% / 30% 后的 MTM 浮亏（`stress_components`）
- **杠杆 ETF 警告**：~50 个名单（TQQQ / NVDL / SOXL 等），命中后屏蔽 wto bonus + verdict 加 con

**3. willing-to-own 因子 `wto_f`**
- 自动推导：持股 ≥100 或 已有该 ticker short put → willing=true
- 手动 override 在账户设置面板（v2 #4 后追加）
- CSP on willing：×1.08；CC on willing：×0.97
- 杠杆 ETF 例外：永远不享受 wto bonus

**4. UX：候选卡片信号 box**
- 候选卡 metrics 下方加 "📊 包租公 2.0 信号" box
- 6 行：年化超额收益 / VRP / 已实现波动率 / 压测 -5% / 压测 -10% / 接货占现金
- 每行带颜色（绿/金/红）+ ? hover tooltip 大白话解释

**5. UX：Wheel 阶梯 builder**
- 新 goal 卡 "🪜 搭阶梯组合"
- 输入接货总预算 → 自动 2-4 档 strike（按预算自适应）
- 卡片显示阶梯色阶（A+ 设计：3px 左色条 + 水平 fill 宽度）
- "一键加仓" 批量录入到持仓

**6. 期权小白指南扩容**
- 新分类"📊 包租公 2.0 信号（高阶）"
- 5 个词条：EV / VRP / RV / 压测 / 资金占用
- 每个含 desc + 实例 + care + 三语

### Algorithm version: 1.4 → 1.9

> 历史脚注：1.9 最早内部叫"2.0"，但回头看更像是一个大幅升级而非完整 major bump。
> 真正的 v2.0 是这之后把出场/Roll/多 ticker/财报红利一起加进来才完整（见上）。

---

## v1.4 (2026-05-18 之前)

详见 `HANDOFF.md` 历史条目。重点：
- `_landlord_score` 8 因子加权评分（年化租金 × 安全度 × DTE / Delta 甜蜜区 × IV rank × 流动性 × 财报因子 × 回测胜率）
- 财报因子按 intent 分别处理（CSP/CC 跨财报视为优势，premium 视为风险）
- IV-adaptive delta band（IV 高自动用更保守 delta）
- Vol skew 信号（put_iv / call_iv ratio）

---

## 设计哲学

包租公算法假设的用户画像：
- **"卖期权是一门生意，不是赌一把"** — Sharpe 比预期收益重要
- **"安全度压倒一切"** — BS prob_safe^1.5 系数 / 资金硬上限 / 压测透明
- **"愿意接货的标的才算 wheel-friendly"** — willing_to_own 是 CSP 评分核心
- **"标签不是黑话"** — sigbox + EDU 指南 + tooltip 三层解释每个数字

不优化的：
- 不预测方向（标的涨跌）
- 不模拟复杂多腿（spread / iron condor 是辅助提示，不主推）
- 不替用户决定（输出推荐 + 信号，最终下单还是人）
