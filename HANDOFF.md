# HANDOFF.md — 最近上下文

> 本文件每次有较大改动后会更新。读完它你就接住了。
> **新 session 第一句话**：先读 `CLAUDE.md` 再读本文件，然后简单复述你看到了什么。

最后更新：2026-05-17（深夜 — 表单双轨 A 落地 + 出场计划重写 + 多账户管理）

### 🆕 这一轮（form A landing 后续，深夜连续迭代）

**总入口**：用户挑了 A 方案落地，然后连续追问"目标只是 UI 没意义吧"→"账户能不能算够不够"→
"出场计划看不懂"→"持仓也加"→"sell put 怎么只 $3.4k"→"被认成 CSP"→"按券商分多账户"。

**完成的事**（一长串提交，main 上）：

1. **A · Tab 切换落地** (`b48813d`) — `rec-form` 顶部 segment control，目标驱动 vs 策略驱动 tab。
   - 4 个 goal cards：💵 stable_rent / 🛡 max_safety / 📊 max_yield / 🎁 assign_stock
   - 每个 goal 反推 direction/intent/timeframe/risk → mutate `_recSelection`
   - mode 持久 `localStorage.rec_mode`
   - 数值输入按 goal 显示（仅 UI 预览不传后端）

2. **Goal 真正起作用** (`2e47136`) — 数值不再死的：
   - `max_safety` 硬 filter（前端过滤掉 prob_safe_pct < target）+ 0 个达标 fallback
   - `assign_stock` 按 `|strike - target|` 升序排序
   - 新增顶部 `goal-banner`：账户预算 + 目标对比 + 钱够不够
   - 单卡 `goal-progress` 加账户负担细节

3. **suggested_contracts 对齐** (`cecf35e`) — 之前 banner 用 100% margin 算"卖 5 张"，跟单卡"建议最多 2 张"不一致。
   - 后端 `suggested_contracts = floor(margin × 0.20 / BPR)` 是 20% 集中度上限
   - banner 改用 suggested → 三档清晰：达标 / 超过建议 / 账户不够

4. **出场计划文案重写** (`eab94ec`) — 用户报"锁利 $2.91 (30%) 看不懂"。
   - 推荐卡：单行 → vertical block 三行，把 mid → exit 价差和每张落袋 $ 写清
   - 持仓卡：新加 `renderPositionExitPlan(p)` compact 一行（默认 balanced = 锁利 50%）
   - 用 sentence-level i18n 模板（`exit_profit_action` / `pos_exit_profit` 等）解决词序问题

5. **Margin L2 / L3+ 拆分** (`2427ef5`) — Schwab CSP-only (Options Level 2) vs naked (Level 3+)。
   - 账户类型 segment 从 2 个变 3 个：cash / margin_l2 / margin_l3
   - 后端 `account_type == "margin_l3"` 才用 Reg-T BPR，否则全额抵押
   - 兼容旧值：'margin' → 'margin_l3'

6. **多账户管理** (`8182f65`) — 用户有 Schwab + Robinhood 等多家。
   - 数据模型变 `account_meta.accounts: [...]` 数组
   - 每个 account: `{ id, name, broker, type, available_margin, stock_positions }`
   - 8 家券商可选（Schwab / RH / IB / TT / Fidelity / E*Trade / TD / Webull / Other）
   - 账户设置 modal 重写成 cards list + "+ 添加账户"
   - `_getAccountMeta()` 返回**合并视图**（兼容旧调用方）：sum margin / 最允许 type / union stocks
   - 新 `_getAccountsList()` 给 modal UI 用
   - Backwards compat：旧 flat 格式自动转单条 default 账户
   - 简化：合并算法用"最允许"type — 已知不完美（Schwab L2 + RH L3 会按 L3 算，但实际 L2 部分得 CSP）

**待用户验证 / 反馈**：
- [ ] 多账户 modal 在桌面 / 手机两种宽度看下 layout（特别是 broker 下拉、type 3-segment）
- [ ] 输入数据 → 推荐 → banner 数字对得上单卡（suggested / BPR 一致）
- [ ] 持仓卡的 compact 出场建议位置 OK 不
- [ ] mixed accounts 推荐时是否需要按账户分组（暂未做）

### 🚧 本地 session 留下的事（2026-05-17 晚）

**JOBhakdi 大佬整合 hold 着**
- 用户提过想把 https://x.com/JOBhakdi 加进 `📖 大佬策略模板`，但没定怎么加
- 现有 5 个预设见 `index.html` 第 6632 行 `REC_PRESETS`
- 当时讨论的整合粒度：轻（加 X 链接 + bio）/ 中（金句库）/ 重（接 X API 自动拉信号）
- 用户说"先算了"，等他自己想清楚再问

（持仓卡 v1 的 3 方案被拒事已经无效：云端 session 后续做了 v2/v3 → 方案 H 已上线）

### 🆕 早安简报升级 落地（branch `claude/enhance-feature-Efdp9`）

**用户选了"方案 D 混搭" + LLM 加持**。设计：A 骨架 + B 14 天日历 + C 管家人格化（LLM 真生成）。

**已落地（在分支上）**：

**后端 `api/state.py`**：
- 新增 `_get_anthropic_client()` —— lazy load anthropic SDK + env var
- 新增 `_fetch_vix_quote()` —— yfinance `^VIX` 当前 + 前收盘
- 新增 `_compute_concentration(positions)` —— 最大单 ticker 占保证金 %
- 新增 `_compute_calendar_14d(positions, today)` —— 未来 14 天财报点 + 到期点
- 新增 `_load_brief_snapshot(state)` / `_make_brief_snapshot(...)` —— 跨日 diff 基础
- 新增 `_compute_diff_events(yesterday, positions, market, lang)` —— 找 since 昨天的"质变"事件：
  - profit_threshold（80% 跨越）
  - dte_window（进入 7 天窗口）
  - newly_itm（昨天 OTM 今天 ITM）
  - earnings_imminent（≤5 天）
  - vix_spike（≥20% 跳涨）
- 新增 `_rank_top_3_focus(events, positions, lang)` —— 选 top 3，不足补 ≥70% 利润 / 距行权 <5%
- 新增 `_build_focus_chips(...)` —— 健康 chips：P&L / 已实现 / Theta / SPY / QQQ / 集中度 / 7d 到期数
- 新增 `_template_concierge(top_3, market, lang)` —— LLM 失败兜底
- 新增 `_generate_concierge_llm(top_3, market, total_pnl, total_theta, conc, lang)`
  —— Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) 生成 ≤80 字管家摘要
- 重构 `_generate_morning_brief(positions, prices, total_pnl, total_realized, total_theta, state, lang)`
  返回 dict：`{ concierge_text, generated_by, top_3_focus, chips, calendar_14d, today_date, next_snapshot }`
- `compute()` 主入口：传 `total_theta` 和 `state`
- 三语 dict（TRANS_EN / TRANS_TW）补 ~25 条新文案

**前端 `index.html`**：
- `.morning-brief` CSS 完全重写（管家 hero + focus list + chips + 14d 日历）
- HTML `<div id="morning-brief">` 改成空 container，JS 动态构造
- 新 `renderMorningBrief(brief)` 接受 dict，按 dismiss state 判断显示
- helper：`_mbRenderFocusItem` / `_mbRenderChip` / `_mbRenderCalendar` /
  `_mbFocusPosition(pid)` (点"看持仓"滚到对应卡 + 短暂金色描边) /
  `_mbOpenRec()` (点"看推荐"打开 rec 表单) /
  `_mbSaveSnapshot(snap)` —— 通过 `saveStateMap` 写 `state._meta.brief_snapshot`
- 三语 dict 补：包租公管家 / 今日要关注 / 📅 未来 14 天关键日 / 财报 / 持仓到期 / 看持仓 → / 看推荐 →

**预算**：anthropic Haiku ~$0.001/用户/天 (= $0.36/年)。失败自动 fallback 到模板版本。

**依赖**：
- `requirements.txt` 加 `anthropic>=0.40.0`
- Vercel 项目要配 `ANTHROPIC_API_KEY` env var（用户去自己配）

**清理**：删 `morning-preview.html` + vercel.json `/morning-preview` 路由 + builds entry

**接下来用户要做的**：
1. ⚠️ Rotate 之前在 chat 里发的 API key（已暴露），创建新 key 命名 `baozugong-vercel-prod`
2. Vercel `option-analysis-platform-web` Settings → Environment Variables → 加 `ANTHROPIC_API_KEY` = 新 key（环境 = Production）
3. Vercel auto-deploy 后验证 `/app` 早安简报，应该看到「☀️ 包租公管家 · 今日…」段
4. 验证：dismiss 后今天不再出现 / 第二天再开应该有跨日 diff（今日是首日，明天起 diff 生效）

### 🆕 并行：子批 C 落地 A — 顶部 Tab 切换（Commit `b48813d`）

**预览页地址**（参考）：https://trade.congyangwang.com/form-dual-preview

3 个 UX 方向 × 桌面+手机：
- **A · 顶部 Tab 切换** ← **用户选了这个，已落地到 `/app` 推荐表单**
- B · 入口卡片 Picker — 备选
- C · 一句话提问 + chips — 备选

**A 落地实现细节**（`index.html`）：

HTML：
- `rec-form` 顶部加 `.rec-mode-tabs` segment control（两个 `.rmt-tab`）
- ticker row 提到 tabs 之下（不再算"第 1 步"，去 `1.` 前缀）
- 新 `#rec-goal-mode` 容器（默认 `hidden`）：4 个 `.goal-card` + 数值输入 + 倒推预览
- 原 preset / direction / intent / timeframe / risk 包进 `#rec-strategy-mode`
- direction/intent/timeframe/risk 的 label 序号 2-5 → 1-4

CSS：`.rec-form .rmt-tab` / `.goal-card` / `.rec-goal-num` / `.rec-goal-preview`

JS：
- 新 `REC_GOALS` dict：4 个 goal 反向映射到 `_recSelection`（direction/intent/timeframe/risk）
- `_recMode` 持久到 localStorage `rec_mode`（默认 `strategy`）
- `switchRecMode(mode)` 切 hidden 状态
- `applyGoal(key)` 选中 + 倒推 + 写 `rec_last_choice` + 渲染 num input + preview hint
- `showRec()` 末尾绑定 tab/goal 点击 + 恢复 mode + 恢复 goal 高亮

数值输入目前**仅做 UI 预览**（"每月目标 / 安全度下限 / 目标接货价"），不传后端。下一步可以接到后端做"严格命中目标"过滤。

i18n：`zh_tw` + `en` dict 各补 ~24 条。

**待用户验证**：
- 桌面 / 手机两个视口都顺
- goal 4 卡片点击 → 反推参数显示对不对
- 切换 tab 来回，submit 走的还是 _recSelection（不变）
- 把目标驱动设为默认是否合适？现在默认 strategy。

**清理 TODO（用户拍板后）**：
- 删 `form-dual-preview.html` + vercel.json 路由

### 📋 上一个 session：子批 B 落地（POP 校准 + Exit plan 模板）

**Commit `fb344ea` → main**（用户授权 prod 验证）

**做了什么**：

POP 校准（重写 `_backtest_strategy`）：
- 窗口 6 月 → **12 个月**（不够回退 6 月），采样 5 天 → **3 天**
- 用 `_strike_for_delta()` 二分查找让 |Δ(K)|≈delta_target（数值验证 Δ
  误差 <0.005），不再用 `offset = rv·√T·0.85` 粗估
- premium 用 BS 算（不再 `offset×0.3`）
- 同时输出 `win_rate` (历史) + `theoretical_pop` (BS N(d2) 均值) +
  `calibration_ratio = empirical/theoretical` + `window_months`
- 后端响应顶层加 `backtest_summary` 字段
- 前端加 `.calib-pill`：ratio < 0.95 → warn "理论可能偏乐观"；
  ratio > 1.05 → ok "该方向历史更稳"

Exit plan（新 `_exit_plan`）：
- 矩阵 `risk × kind` 5×3 矩阵：
  - csp / covered_call：30/None, 50/None, 75/None（不止损 = 接货/被叫走）
  - short_premium 裸卖：30/100, 50/200, 75/300
  - leaps：50/50, 100/50, 200/50
  - long_other：50/50, 100/50, 150/50
- 输出 `profit_target_pct / stop_loss_pct / exit_at_price / stop_at_price
  / roll_trigger / summary_vars`
- 每个 candidate 都有 `c.exit_plan`
- 前端 `renderExitPlan()`：暖金 inline 行在 acctBar 下方，3 段 segment

三语 i18n 完整：出场计划/锁利/止损/不止损/被指派接货/被叫走持股 + 三个
结构化 key (exit_roll_dte7_delta50 / historical_below_theory /
historical_above_theory)。

**未做 / 待验证**：
- [ ] 用户 prod 验证 exit-plan inline + calib-pill
- [ ] 子批 C（表单双轨模式）— 待做

---

### 📋 更早一个 session：Wheel 闭环提示 debug（Batch 4 中点）

**分支**：`claude/batch-4-midpoint-6gjJE` → **已合 main**（cherry-pick `4cae7fd`）
**原 feature commit**：`4d69f2c`

**症状**：用户报"账户设置里存了 ≥100 股，但 Wheel 闭环提示不出来"。

**根因（3 个独立 bug）**：
1. **`_getAccountMeta` cloud-empty 不 fallback localStorage** —— 已登录 +
   cloud ready 时只读云端，云端无 `_meta.account` 就返回 `{}`，把
   localStorage 里的数据完全忽略。早期未迁移的用户彻底失效。
2. **登录后 account_meta 没人帮搬到云端** —— `_migrateLocalPrefsToCloud`
   只迁 `_PREF_KEYS`（lang/theme/density/rec_*），`account_meta` 不在 list。
3. **`close_reason='expired_itm'` 全 codebase 没人写** —— `submitClose` 只
   set `'manual'`，路径 2（CSP 到期被指派 → 进 Wheel 下半场）功能上是死的。

**修法**（一个 commit 三处改 index.html）：
1. `_getAccountMeta` (8587): 云端无 `_meta.account` 时退回 localStorage
2. 新增 `_migrateLocalAccountToCloud` (8738) + 在 `_onSignedIn` (8529) 调用
3. `renderWheelHints` (8213) 加 path B：`!p.closed && p.days<=0 &&
   p.underlying<p.strike` 时自动认作"30 天内被指派"（前端推断，不污染
   close_reason 写入）

**未做 / 待验证**：
- [ ] 用户在 prod 验证 Wheel hint 现在能出来了
- [ ] 三个浏览器矩阵（Mac Chrome / iPhone Safari / Android）测同步迁移
- [ ] 子批 B（POP 校准 + Exit plan）— 待做
- [ ] 子批 C（表单双轨模式）— 待做

---

### 上一个 session：UX 按钮 / 推荐模组 / 账户设置 重设计 + 删「复用上次」

**做了什么**（commit `586ba35`，branch main）：
- 全局按钮 B 风格：10px 圆角 + 1.5px 描边 + `scale(1.03)` hover + `cubic-bezier(0.16,1,0.3,1)` 过渡
- 账户设置 modal 重写：`.am-*` scoped CSS，补 `position:fixed` 居中，去掉外借样式
- 推荐模组（rec-form）紧凑化：section 间距 22→14px，opt-btn padding 缩减，timeframe 3→4 列
- rec-form sticky header（h4）+ sticky footer（submit-row），负 margin 补齐 padding 穿模
- 点击「找出最佳」后自动滚到 `.algo-badge`（加载中先滚到 #rec-result）
- **删「复用上次」功能**：移除 `.rerun-btn` CSS / HTML 按钮 / `renderRerunBtn` / `rerunLastRec` / DOMContentLoaded 监听 / submitRec 内调用 / zh_tw+en i18n 条目
- 保留 `rec_last_ticker` / `rec_last_choice` localStorage 写入（仍用于表单预填）
- 建预览页 `buttons.html`（`/buttons`）和 `rec-redesign.html`（`/rec-redesign`）已保留在 repo

---

### 持仓卡片重设计（方案 H · E+G 综合）

**分支**：`claude/redesign-holdings-visual-hierarchy-qAsag` → 已合 main

**做了什么**：
- 用户说原持仓卡"视觉一致性 / 主次不分明、要素过多"，要求重设计
- 走 CLAUDE.md 第 9 节"设计类任务必须先做预览页"流程：
  - 建 `positions-preview.html`（路由 `/positions-preview`）
  - v1：3 个方向 A/B/C（紧凑 / 分层 / 标签化） — 用户全否
  - v2：4 个新方向 D/E/F/G（紧凑行 / iOS / 仪表盘 / 双列） — 用户全否，但点出"E 和 G 综合一下"+"完整模式要保留当前版的所有信息量"
  - v3：方案 H（E + G 综合，含完整 / 简洁两种模式） — 用户选定
- 落地到 `/app` 的 `renderPosition()` + .pos 系列 CSS

**方案 H 设计要点**（commit `606d1d1`）：
- 双列布局：左 PnL 大字 hero (26px) + 完整模式下 Theta block；右 horizontal 双进度条 + inline greeks
- 状态用文字色（不再用 chip 背景抢戏）
- 顶部加 `.pos-more` ⋯ 按钮：点击复制 OCC code（旧 .pos-occ DOM 已删）
- 胶囊按钮：`.primary` 黑底白字「平仓」+ `.ghost`「编辑」+ `.ghost.del-btn`「删除」
- 损益曲线 + 笔记按钮归入 `.pos-extras` 容器
- 简洁模式新规则：藏 `.pos-meta` / `.pos-theta-row` / `.pos-stats .full-only` (Mark+$P) / `.pos-extras` / `.pos-actions .del-btn`
- 完整模式 = 当前版的全部信息量（PnL+Theta+副标+进度条+Δ/IV/θ+Mark/$P+损益曲线+笔记+删除）
- 简洁模式 = 上面除了"完整 only"的字段
- `renderClosedPos` 未动，仍用旧 `.pos-hero` 双格 grid（保留旧 CSS 兼容）

**预览页保留**（reference）：https://trade.congyangwang.com/positions-preview

**测试矩阵未跑**：用户已确认方向 OK，但 Mac Chrome / iPhone Safari / Android 实测要他做。

---

### 📦 Batch 4 进行中（推荐引擎进阶 backlog）

Batch 4 是用户 priority table 的最后一波，分 3 个子批做：
- **子批 A ✅ 已上线**（`d09ab02`）：long_vol 下架 + Vol skew 信号 + Wheel 闭环提示
- **子批 B 待做**：历史 POP 校准 + Exit plan 模板（~2 天）
- **子批 C 待做**：表单双轨模式（目标 vs 策略，UX 大改，~1 天）

子批 A 验证清单：
- [ ] /app 推荐结果里出现 Vol skew pill（put_skew/call_skew，中间值不显示）
- [ ] 持仓列表上方出现 Wheel 闭环提示 — **2026-05-17 已 debug** `4cae7fd`，
      三种触发：账户设≥100 股 / 手动 expired_itm / put 已过期未平仓且 ITM
- [ ] intent 下拉只剩 4 项：收权利金 / CSP / Covered Call / LEAPS（"做多波动率"已下架）
- [ ] [推荐 Covered Call →] 按钮一键预填 rec form (covered_call/neutral/21d/balanced)
### ⚠️ 新 session 必看：CLAUDE.md 顶部 3 条铁律

1. **开场必报模型**（用户期望 Opus 4.7 1M Max，不是就暂停问用户）
2. **任务中独立检查**（不要说"我记得"，主动 git pull + 看 HANDOFF）
3. **收尾必更新 HANDOFF.md**（再 commit + push 再宣告完成）

详见 `CLAUDE.md` 顶部"Session 必读"区块。

### 🎨 旧规约：设计类任务必须先做预览页

任何涉及 UI / 视觉 / 布局 的任务，**不要直接改 index.html / intro.html**。
先建临时预览页（如 `buttons.html` → `/buttons`），同屏展示 2-4 个方案 × 桌面+手机两个视口，
让用户选完再改正式页面，然后删预览页。

详见 `CLAUDE.md` 第 9 节。

---

## 1. 最近 12 个 commit（按新到旧）

```
7af714e style: round 2 — premium polish (backdrop blur, focus rings, gradients)
c982da7 style: UI polish — Linear/Vercel-inspired refinements
4b9b15c fix(mobile): 16px font-size 规则不再套用到 select
41299d1 fix(mobile): 移动端推荐 modal 难看 — 根因是缺 viewport meta
197b60a docs: HANDOFF — 偏好云同步 + 简洁模式入主线，更新 backlog
06772eb feat: 简洁模式 toggle（持仓卡 + 推荐卡）
66d80cc feat: 偏好设置（lang/theme/tier_filter/rec_last_*）云端同步
9ff7d00 docs: 授权 — 部署/合并 main 不再单独问
69d26f9 docs: HANDOFF 更新 — 算法 1.2 + Massive 移除 + 数据源 pill
f773187 feat: 推荐列表顶部加数据源降级 pill
0fc47de remove: Massive API（30 天历史价位带特性弃用）+ Schwab 错误日志
8103520 algo 1.2: 财报因子改成距财报天数衰减
```

## 2. 本 session（cloud / 2026-05-17）做了什么

### UI 打磨（`claude/polish-ui-design-T1D8m` → main，2 个 commit）

**Round 1（`c982da7`）— Linear/Vercel 风格视觉精修**
- border tokens: `--line`/`--line-2` 稍亮，暗色模式边框更清晰
- `--accent-light: #F0C778` 变量，收拢全部硬编码
- 移除 pos 卡 / rec 按钮 / compare pill 的 `translateY(-1px)` hover 浮起效果
- `pos-hero` 加上下 hairline border，区块分层清晰
- `pos-bar` 滑块：白圆 → accent 描边圆
- `rec-rank`：粗体大号数字 → compact badge tag
- 推荐卡加 3px 包租公分视觉条（随 verdict 颜色，short 策略才显示）
- `kmet` 指标格加 border
- `morning-brief` / `info-card` / `algo-badge` 去掉 border-left 金色（减少滥用）

**Round 2（`7af714e`）— 精致感更深的改动**
- `modal-backdrop`: `backdrop-filter: blur(10px) saturate(140%)` — 玻璃感
- `:focus-visible` 全局 focus ring（3px accent 光晕，键盘only）
- Summary 顶部数据区：28px 数字 + cv11/tnum font features + 伪元素分隔线 + 顶部极淡金线
- `rec-btn-large` + `compare-pill`：linear-gradient + inner highlight + 暖金阴影晕
- 品牌 mark drop-shadow 微光（hover 增强）
- 所有卡片 transition 改 `cubic-bezier(0.16, 1, 0.3, 1)` — 自然减速曲线
- 所有 modal shadow 加 inset highlight（配 backdrop blur）
- `morning-brief` radial-gradient 暖色 / `algo-badge` 细微纵向 gradient
- `pos-actions` 按钮改用 `--accent-tint` 变量（清理硬编码 rgba）

---

### 之前的 session（cloud / 2026-05-17）

分支 `claude/product-suggestions-TzFsz` 合到 main 后又追加了 2 个 feature commit。

**追加 D. 偏好云同步**（`66d80cc`）
- state._meta.prefs 命名空间，存 lang/theme/density/rec_tier_filter/rec_last_ticker/rec_last_choice
- 新 _savePref / _applyCloudPrefs / _migrateLocalPrefsToCloud 三个 helper
- 接入 setLang / toggleTheme / setTierFilter / rec form submit / toggleDensity
- realtime 推送也会触发 _applyCloudPrefs，跨设备 lang/theme 实时生效

**追加 E. 简洁模式 toggle**（`06772eb`）
- 全局 data-density="simple|full"，CSS 接管隐藏次要字段
- 简洁下藏：pos-meta/pos-occ/pos-stats、rec-compare-check
- 保留：pos-row1/hero/bar/time/actions、推荐卡所有主体
- pos-toolbar 多 📐 按钮；prefs 入 density，跨设备同步
- 默认 full，首次切换后会上云

**算法 1.2 验证 A/B（一次性脚本，不入 repo）**：
NVDA balanced 跨财报 → 1.1 是 0.55，1.2 是 0.75 (+36%)；NVDA conservative
跨财报 → 1.1 全归零 10 个候选都看不到，1.2 救活全 10 个评分到 0.60。
SPY/TSLA 无财报场景两版本 score 完全一致，零回归。

---

## 2bis. 之前的 cloud session（同日早上）做了什么

分支 `claude/product-suggestions-TzFsz`，3 个 commit：

**A. 包租公算法 1.2 — 财报因子距离衰减**（`8103520`）
- 原 1.1：cross 就 ×0（保守）/ 0.55 / 0.78 — 一刀切，误杀大量 14+ 天后到期合约
- 新 1.2：按距财报天数衰减（≤2/≤7/≤14/≤21/>21 五档），保守模式仅 ≤5 天硬否决
- 风险偏好做基线调整：conservative ×0.80，aggressive ×1.15
- `_earnings_factor()` 是纯函数，单测过 — 见 commit 信息

**B. 删 Massive + 清 Schwab print 日志**（`0fc47de`）
- 用户说 Massive 已弃用 → 全删：MASSIVE_KEY、fetch_massive_option_history、
  _build_occ_symbol、_cache_occ_hist、_wheel_friendly_factor / _make_verdict
  的 price_band 参数、recommend 富集循环、renderPriceBand JS、.price-band CSS、
  intro 三语 6 处文案、README 一处。
- print(f"[schwab] {err}") 4 处删掉。错误仍存 _schwab_last_err，
  通过 debug_env action 可查（不在标准响应里裸露）。

**C. 数据源降级 pill**（`f773187`）
- fetch_chain 三个分支（schwab/yahoo/yfinance）每条 quote 都标 source
- 新 _summarize_data_source()：取出现最多的源做 primary，
  非 schwab 即 is_fallback=true（unknown 不算 fallback）
- 响应 data_source 多 3 字段：primary, is_fallback, sources
- 前端 renderRecResult 在 summary 下面渲染暖金 pill：
  「📡 ⚠️ 当前为延迟数据源 (yahoo)」+ 副标说明，仅 is_fallback 时出现
- 三语 dict 补 2 条新文案

**已知未做**：
- 验证未在生产 curl（沙盒网络可能受限），用户需要在 Mac 上拉 trade.congyangwang.com/app 看 pill 是否生效
- iOS Safari、Android 三浏览器矩阵未测

---

## 2ter. 更早一个 session 主要做了什么

**主题 A — 4 个功能 + 包租公分修复**（commit `a4432f4`, `84ec1dd`）
- 📊 加仓预览（modal，集中度 / Greeks / 保证金 / 收益）
- ⚖️ 候选对比（checkbox + 浮 pill + 表格 modal）
- 📱 手机 UX 优化（header 压缩 / 卡片防溢出 / bottom-sheet modal）
- 💡 买入期权场景的"包租公分不适用"提示

**主题 B — Supabase 云同步 + Google 登录**（commit `4354462`～`a973cbb` 一连串）
- 加 Supabase JS SDK + RLS 表 `user_data`
- Google OAuth（用户在 Google Cloud Console 配的 OAuth client + Supabase Auth Provider）
- 实时双向同步（postgres_changes 订阅）
- 首次登录迁移向导（页面内 modal，因 confirm() 被 OAuth 后 Safari 拦截）
- 删掉 File System Access sync 老代码（~454 行）
- 用户菜单：✏️ 改昵称 / 📥 重新导入本地数据 / 💾 导出 JSON 备份 / 🚪 登出
- 主要 bug 修复：
  - `?code=` 在 `load` 时被我手动清掉导致 PKCE 失败（iOS Safari race）
  - storageKey 漂移导致 localStorage 残留 `sb-baozugong-auth-code-verifier`
  - PKCE flow 显式开启（更 Safari 友好）
  - 加可见诊断面板（`?debug=auth` 触发 / 自动在 OAuth 回来后 5 秒未登上时弹）
  - 持仓选择 selectedIds race（手机刷新后清空）→ `_onSignedIn` 末尾重置 + 选择也同步到 cloud

**主题 C — 其他**
- intro 页隐私区块重写（围绕新的云架构）
- Vercel Web Analytics + Speed Insights 接入 index.html + intro.html
- 联系邮箱 `hi@congyangwang.com` 上 intro 页（隐私区块底部 + footer）

---

## 3. 用户的 setup 状态（已完成）

✅ Supabase 项目 `nvavwcvxmzksadpbtafs` 已建
✅ Google OAuth client 已配（Test users 已加自己邮箱 — production publishing 还没做）
✅ `user_data` 表 + RLS 已建
✅ Supabase Site URL = `https://trade.congyangwang.com` + Redirect URL = `/app`
✅ 用户在 Mac Chrome 已成功登录（数据已同步上云）
✅ Vercel GitHub auto-deploy 已配（push 到 main 自动部署）

❌ Vercel Analytics 还没在 Dashboard 启用 — 需要用户去 https://vercel.com/genki3ngs-projects/option-analysis-platform-web/analytics 点 Enable
❌ Google OAuth consent screen 的 Support Email 还没换成 `hi@congyangwang.com`（建议改）
❌ Supabase Support Email 同上
❌ Google OAuth 还在 "Testing" 状态（不影响 Test users，但其他人登不了）

---

## 4. 待办 / 进行中

**用户上一次报的最后一个问题**：手机刷新后持仓勾选丢失 → 已修（commit `ca2d251`），用户还没回报最新测试结果。**新 session 接手时先问用户**：「ca2d251 修了手机刷新后勾选丢失的 bug，最新部署应该已经修好，你还有什么不对的吗？」

**之前留下的 backlog（用户没有明确说要立刻做）**：
- ~~简洁模式 toggle~~ ✅ 06772eb 已做
- ~~把"⭐过滤 / 语言 / 主题 / 表单上次的值"也同步到云端~~ ✅ 66d80cc 已做
- Iron Condor / Spread builder
- 真实历史 IV 接入（已弃 Massive，需找别的源 — 比如 yfinance historical IV / CBOE）
- 跨 ticker 相关性分析
- 大佬交易信号（X subscriber post）接入
- 移动端持仓表单 Wizard 化（来自更早 backlog）
- Trade Journal 分享 + LLM 摘要（来自更早 backlog）

---

## 5. 已知问题 / 风险点

1. **Schwab refresh_token 有效期 7 天**。**用户 2026-05-16 重新生成过**，下次到期 ~2026-05-23。
   过期表现：`/api/state` 返回 `schwab_last_err: "expired"` 或类似，候选数据缺失。
   修法：用户本地跑 `python3 scripts/schwab_auth.py`，生成新 token，贴给我（或他们手动更新 Vercel env）。

2. **Google OAuth 还在 Testing 状态**：非 Test users 看到 "Access blocked" 警告页。
   产品 launch 前需要走 Google verification 流程（要 privacy policy URL / app screenshot 等，估计 1-2 周）。

3. **Vercel @vercel/python legacy builder env propagation 偶发不稳**：症状是 `debug_env` 显示 schwab_env_keys 为空。
   兜底方案：用 Vercel REST API + inline env 重发部署（前历史有完整脚本）。

4. **iOS Safari ITP 7 天清 localStorage**：用户 7 天不访问，localStorage 数据被清。**已登录用户不影响**（数据在云端），未登录用户可能丢。

---

## 6. 用户的"测试矩阵"

每次较大改动后用户会试这些：
- Mac Chrome：基本功能 + 推荐 + 预览 + 对比
- iPhone Safari：登录 + 同步 + UI 触感
- Android（Edge / Chrome）：登录 + 同步

凡是涉及 auth / 数据流的改动，**都要至少在脑里跑一遍三个浏览器的边界情况**。

---

## 7. 接手新 session 的开场白模板

> 你好。先读 `CLAUDE.md` 再读 `HANDOFF.md`，然后简单复述一下你看到了什么、当前我们在干什么。
> 我有 X 问题想处理，你看怎么搞。

---

## 8. 给 Claude 自己留的话

如果用户说"延续上次"或类似，不要假装记得；直接说"我读 HANDOFF + CLAUDE 看到这些 [复述]，对吗？"然后让用户确认或补充。

不要往这两个文件里加水（"我们一起完成了..."这种废话）。每次更新这两个文件只增加**事实**和**对后续 session 有用的信息**。

---

## 9. ⚠️ Public repo 注意事项

本 repo 是 **public**。任何提交都会被全世界看到，包括 git 历史（即使后来 commit 删掉了，rebase 重写之前的版本也能在 GitHub fork / Wayback Machine 找到）。

**永远不要 commit 的东西**：
- Schwab 三件套（CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN）
- Vercel personal token
- Supabase **service_role** key（注意是 service_role，不是 publishable）
- 用户的实际持仓数据 / 邮箱 / 电话
- 任何形式的 `.env` 文件

**已经在 `.gitignore` 防御**：
- `.env*` / `*token*.txt` / `*secret*.txt` / `*credentials*.json` / `*refresh_token*` 等

**正确做法**：
- 凭证存 Vercel env vars（dashboard 或 API 设置）
- 写一次性脚本要凭证 → 用 `getpass` 或 `os.environ.get` 读，**不要 hardcode**
- 临时 debug 用 token？跑完立刻让用户 rotate 那个 token

**RLS 是 Supabase 安全唯一防线**（publishable key 公开是设计）。改 Supabase schema / policy 一定要测：未登录用户能不能读到别人数据？应该是 NO。
