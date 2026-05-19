# HANDOFF.md — 最近上下文

> 本文件每次有较大改动后会更新。读完它你就接住了。
> **新 session 第一句话**：先读 `CLAUDE.md` 再读本文件，然后简单复述你看到了什么。

最后更新：2026-05-19（cloud — 持仓卡出场建议去重复 💰 logo + 解释出场逻辑）

### ✅ 这一轮（2026-05-19 cloud · 出场建议重复 logo 修复）

**主题**：用户截图反馈持仓卡出场建议行有重复的 💰 emoji（`📍 出场建议 💰 💰 死磕到期...`）。同时要求解释「出场建议」整套逻辑及 why。

**根因**（`index.html:8166` `renderPositionExitPlan`）：渲染结构为
`📍 出场建议 [styleEmoji ep-style-mini] [tag-pill][primary.icon primary.text] [· secondary]`。

- `styleEmoji` 当前风格 emoji：🏠 / 🏘️ / 💰
- `primary.icon` 主触发线 emoji：🚨/⚠️/📬/⏱️ + hold_to_expiry 默认分支的 💰

当 user 是 `hold_to_expiry` 派且没触发红线/违约/锁利/DTE → fallback 分支 primary.icon = 💰，跟 styleEmoji 重叠。
其他两种风格（🏠 early_close / 🏘️ wheel_assign）的 styleEmoji 跟 primary.icon 候选集不重叠，没有此 bug。

**修复**（`index.html:8200-8202` + `8234-8235`，3 处）：
1. hold_to_expiry 默认分支 `primary.icon` 从 `'💰'` 改为 `''`
2. tag-pill 映射：原靠 `primary.icon === '💰' ? '死磕'`，改成 `style === 'hold_to_expiry' ? '死磕'`（因为 icon 已空，得用 style 兜底；移动端的"死磕"标签照常显示）
3. ep-body 渲染：`${primary.icon} ${primary.text}` 改成 `${primary.icon ? primary.icon + ' ' : ''}${primary.text}`（避免空 icon 留前导空格）

**没改的**：
- 后端 `position_advice` / `_exit_plan` 4 触发线逻辑不变
- 早收租派 / Wheel 派的渲染不变（本来就没重复）
- 副信息（🤝 跌穿 $strike 接 ticker / 📤 升破 $strike 卖出 ticker）不变
- i18n 字典不动（"exit_hold_expire_pos" 文本本来就含"死磕到期"）

**`ALGORITHM_VERSION` 未碰**（纯前端 UI 去重，跟算法无关）。

**出场建议逻辑速查**（写给下个 session）：
- 入口 `renderPositionExitPlan(p)` 仅对 short premium 持仓显示，对应后端 `position_advice`
- 4 触发线优先级：🚨 红线（财报跨期）> ⚠️ 违约（|Δ| ≥ 阈值）> 📬 锁利（profit% ≥ 50）> ⏱️ DTE（剩 ≤ 21d 且盈利）
- 风格门：early_close 全开 / wheel_assign 全开但 deltaTh 抬到 0.45 / hold_to_expiry 只留红线（其余 None）
- 都没触发：hold_to_expiry → "死磕到期 · 剩 N 天 · 持到 expire"，其他 → "离 50% 锁利还差 X%"
- 副信息：未触发 delta/红线时显示 Δ vs 阈值；hold_to_expiry 且非红线 → 显示接货/卖出预期

---

### 上一轮 (2026-05-19 cloud · renderAll selectedIds null 崩溃)

**用户报错**：`刷新失败：Cannot read properties of null (reading 'has')`

**根因**：3 个路径会把 `selectedIds = null`（`_onSignedIn` line 13001 / cloud realtime sub line 13506 / import line 11682），都依赖紧接着的 `refresh()` 重新初始化。但 `refresh` 是 async，在 await fetch 几秒窗口里如果用户切语言（`setLang` → `renderAll(window._currentData)`）/ 排序 / 勾选 / `togglePos` → 调到 `renderAll`，里面 `selectedIds.has(p.id)` 直接抛 — footer 显示 "刷新失败" prefix（line 13814）。

**修复** (`index.html:12584-12591`)：`renderAll` 入口加 null guard，用 `loadSelection` 兜底（行为跟 refresh 路径 line 13798-13804 一致：cloud → localStorage → 默认全选）。

```js
function renderAll(d) {
  if (selectedIds === null) {
    selectedIds = loadSelection((d.positions || []).map(p => p.id));
  }
  ...
}
```

**没改的**：3 个 `selectedIds = null` 重置点都保留 — 那是设计上让下次 refresh 用真实 cloud selection 初始化；guard 只是 race 兜底。

---

### 上一轮（2026-05-19 cloud · 包租公管家付费刷新功能）

**主题**：用户要求"管家每天早上才更新一次，但市场一天可能在变幻"——给管家加 refresh 按钮，一次 5 金币。

**后端实现**（`api/state.py`）：
1. `_generate_morning_brief(..., force_refresh=False)` — 新参数，True 时跳过 cache 命中条件强行调 LLM
2. `compute(payload)` — 读 `payload.brief_refresh` 透传给上面；response 加 `brief_refresh_charged: bool`（仅在用户请求 + 真走了 LLM 时才 True，template fallback 不算）
3. `do_POST` handler — `compute` 分支后，`brief_refresh_charged=True` 时写一条 `brief_refresh` usage_event（metadata: cost=5, by=llm, lang）
4. `get_coin_balance` 重写 — 抽出 `_count_usage_event` helper，分别 count `recommend`（×1）和 `brief_refresh`（×5），相加 = used，1000 - used = remaining

**前端实现**（`index.html`）：
1. `.morning-brief .mb-refresh` 新样式 — pill 按钮，position absolute 在 close × 左侧（top:9px right:38px）；disabled 状态变灰；refreshing 时图标旋转
2. 手机 `@media (max-width: 600px)` — 只显示图标 + cost label 隐藏，避免和标题挤
3. `_deductCoin(n=1)` — 支持参数；扣完调 `_updateMbRefreshButton` 同步按钮 disabled 状态
4. `_loadCoinBalance` 末尾同步调 `_updateMbRefreshButton`
5. 新 `_mbRenderRefreshBtn` / `_updateMbRefreshButton` / `refreshMorningBrief` 三函数；后者：confirm → POST with `brief_refresh: true` + user_id/email → 检查 `d.brief_refresh_charged` → 真扣才 `_deductCoin(5)` + 重 reconcile；LLM 失败 alert "管家暂时打盹，本次未扣金币"
6. 注入到 `renderMorningBrief` 两个模式（mode-priority 和老 prose）
7. i18n — zh_tw / en 各加 7 个 key（刷新管家、需要 5🪙、花 5🪙 让管家重新查…、刷新中、生成失败、刷新失败 prefix）

**安全考虑**：
- share view 不渲染按钮（接收方不该花分享者的钱）
- 未登录用户按钮 hide（无账户无 coin 概念）
- 余额不足按钮 disabled，tooltip 提示"需要 5🪙"（用户选项 B）
- 后端 brief_refresh_charged 只在 by="llm" 时为真 — template fallback 不扣费，用户重试不亏

**没改的**：
- 现有自动 5 分钟 refresh 流程不变（仍走 cache 路径）
- recommend 1 coin 流程不变

---

### 上一轮（2026-05-19 cloud · 集中度从"紧急"降级到中性提示）

**主题**：用户质疑"管家算法把集中度给到紧急"不对 — 集中度本质是策略选择（Wheel 蓝筹 / 长期看好单票的用户本来就偏集中），因人而异、偏中性，不该当 alert 报警。

**改前**（`api/state.py`）：
- 复盘卡阈值 ≥75% 标红 `danger` 🚨"集中度过高"+ 文案"全员指派"；60-75% `warn` ⚠️"考虑换 ticker 分散"
- 早安管家 LLM prompt 强制 "**集中度 ≥40% → 必有 1 root**"，root 定义包含"集中度爆"
- focus chip ≥40% tone="warn" 黄边框

**改后**（4 处改动）：
1. **复盘卡阈值 + sev 全降一级 + 文案中性化** (`state.py:1680-1709`)
   | 集中度% | sev | emoji | 文案语气 |
   |---|---|---|---|
   | <60 | (无卡) | — | — |
   | 60-75 | `info` 中性 | 🏘 集中度 | "因人而异，看你的资金体量与投资目标" |
   | 75-90 | `caution` 黄 | 💡 高度集中 | "没有标准答案，看你的偏好" |
   | ≥90 | `warn` 橙 | ⚠️ 单点集中 | "这是你的策略选择，留意单点风险就行" |

2. **i18n 字典补新 key**（`TRANS_EN` line 145-160 / `TRANS_TW` line 330-340）— 旧 6 个 key 保留（向后兼容，标 legacy 注释）

3. **LLM prompt** (`state.py:4756-4764`) — 删 `集中度 ≥40% → 必有 1 root`；root 定义去掉 "集中度爆"；加一段："集中度是策略选择不是问题 — Wheel 蓝筹用户本来就偏集中，只在叠加方向性风险（财报临近/宏观/ITM 缓冲薄）才提，措辞中性，不说'过高'/'分散'"

4. **focus chip** (`state.py:4583-4588`) — 阈值 40%→60%，tone "warn"→"neutral"（前端 `_mbToneClass` 不识别 neutral → 无边框颜色，纯中性 chip）

**没改的**：
- `_compute_concentration()` 计算逻辑不变
- `signal_lines` 喂给 LLM 的集中度数据点仍 ≥40% 就给（作为背景信息，LLM 自行判断是否值得提）
- 加仓预览 modal 里的"20% 集中度上限"是独立逻辑（建议张数计算，不是 alert），不动

**版本号**：未碰 `ALGORITHM_VERSION`（CLAUDE.md 明确："以后如果版本号要更新，要询问我"）。

---

### 上一轮（2026-05-19 cloud · 窄屏 header 徽章重叠 bug）

**主题**：用户截图反馈窄屏（Pixel/Galaxy ~320-360 CSS px 视口）顶部 4 个徽章（user-badge / coin-badge / lang-selector / theme-toggle）挤成一团甚至重叠。

**根因**（`index.html:212-267` + `4256-4267`）：4 个徽章都用 `position: absolute` 固定像素偏移 — user-badge `left:0 max-width:110`，coin-badge `left:124`，lang-selector `right:38`（width ≈ 84），theme-toggle `right:0 width:30`。在 320 CSS px 视口下，coin 末端 = 124+~80 = 204，lang 起点 = 320-38-84 = 198，**实际重叠 6px**。

**修复**（`index.html:4380-4390`）：在已有 `@media (max-width:480px)` 块里追加窄屏徽章缩水规则 — user-badge max 110→96 / padding 8→7 / avatar 22→20，coin-badge left 124→104 / padding 14→8，lang-selector right 38→34 / button padding 7→5 min-width 28→22，theme-toggle 30→28。新算下来 320px 视口 coin 末端 160，lang 起点 190，留 30px 余量。

**没改的**：桌面与 480-720px 之间的尺寸保持原状（那里本就够宽）。

---

### 上一轮（2026-05-19 cloud · sug-card status 竖排 bug）

**主题**：用户截图反馈"操作建议"卡片里的告警状态（如 `⚠️ 房客违约触发 · 🏠 早收租派` / `⏱️ 21 天换租线 · 🏠 早收租派`）在移动端被挤成每个字一行的竖向排列。

**根因**（`index.html:4030-4038`）：`.sug-head .row2` 是 flex 行，`.status { flex: 1 }`（= `1 1 0%`，basis 0），同行的 `.sub`（"Exp 2026-05-22 · 3 张 · 剩 3 天 · 🏠 早收租派"）默认 `flex: 0 1 auto`。中文无 word boundary，flex 收缩时 `.status` 收到 min-content = 单字宽，`.sub` 抢走主流剩余空间 → status 文本逐字向下堆叠成竖条。

**修复**：`.row2` 加 `flex-wrap: wrap`；`.status` 改 `flex: 1 1 100%` + `min-width: 0`（永远独占一行）；`.arr` 加 `margin-left: auto` + `flex-shrink: 0` 保持右贴。所有 sug 卡片现在统一布局：row1 标题 + pnl tag / row2 告警状态独占 / row3 sub 元数据 + ▶。

**不修复**：用户截图里 TSLA $415 Put 显示 `-623.8%` — 是 fake data 跟 live quote 错配的极端百分比，HANDOFF round 4 已记为非 bug。

---

### 上一轮（2026-05-19 cloud · UI/UX QA round 4）

**主题**：用户要求"更小心"。先 grep 确认每个函数 + selector 存在再写脚本，每张截图视觉验证后才下结论。Round 3 报的 "pos-card-expanded" 其实**不是一个 feature** — `.pos` 卡片本来就一直展开。

**真 bug 修复（2 处）**：

1. **复盘 modal 表头 "持仓" 中文** (`index.html:10359`) — `t('持仓')` 调用但 zh / zh_tw / en 任何字典都没有这个 key（只有 '持仓明细'）。EN 模式 review 表头第一列显示中文。补 zh_tw "持倉" + en "Position"。

2. **每日 Theta 负值显示 "+$-13"** (`index.html:9035` + `9064`) — 两处都用 `+$${fmt(p.daily_theta, 0)}` 硬编码 `+` 前缀。深 ITM short put 的 theta 可能短期为负，渲染出 "+$-13" 怪异格式。改用 `signed(p.daily_theta, 0, '$')` + `colorOf()` 动态颜色，正负值都正确显示（`$X` / `$-X`）。

**Round 1/2/3 修复在 round 4 截图全验证生效**：
- ✓ "Set account to show capital usage" 英文
- ✓ "Tue 5/19 · 14:24" brief 标题英文
- ✓ rec ticker placeholder 英文 "Try SPY, TSLA, NVDA, META for high liquidity"
- ✓ "Short premium: lower Δ = safer" 风险偏好 hint 英文
- ✓ "+ Add stock" 账户 modal 按钮英文（动态渲染时也翻译）

**深层 surface 截图栈**：`/tmp/qa-shots-4/<vp>/{01..13}.png` — 26 张，覆盖 review modal / edit modal (inline) / close dialog / roll suggestion (复用 rec modal pre-fill TSLA+CSP) / brief reopened / 小白指南 / EN data / 繁中 data。

**false positive 排除**：
- 推荐 modal STRATEGY INTENT 的 "Premium income" vs "Cash-Secured Put" 高度看似不齐 — CSS `align-items: stretch` 实际生效，是文字行数不同的视觉错觉，**非 bug**。
- AAPL "-5,583%" / TSLA "+3,303%" 极端百分比 — fake data 跟 live quote 错配产生的，**非 bug**。
- 移动版 review table META $580 Put wrap 3 行 — 是窄屏 natural wrap，**非 bug**。

**剩余 backlog**：
- 候选卡片渲染（2×2 出场计划 + sigbox 信号 + verdict 列表） — 必须真跑 recommend 后端返回有效候选才能看到，需要真账号 OR 后端 mock。
- payoff diagram modal — 需要点击 "Payoff Diagram" 按钮触发，脚本没覆盖。
- compare candidates modal — 需要勾选多个候选再点对比，更复杂。

---

### 上一轮（2026-05-19 cloud · UI/UX QA round 3）

**主题**：重写 Playwright 脚本修 modal backdrop intercept 问题（用 `hideRec()` JS 调用替 Escape，显式 backdrop 清理），扫 16 个 surface × 2 viewport = 30 张截图，发现 round 1/2 没看到的 6 处 i18n leak — 都在动态渲染或 placeholder 上。

**真 bug 修复（6 处 i18n leak）**：

1. **`rec-ticker` placeholder "TSLA · 或多个 TSLA,NVDA,GOOG"** (`index.html:5181`) — 推荐表单 ticker 输入框 placeholder 硬编码中文，EN 模式下灰字仍中文。加 `data-i18n-placeholder` + 3 套字典。

2. **`occ-input` placeholder "例如: TSLA260515P00385000"** (`index.html:4988`) — 加期权 modal 的 OCC paste 框 placeholder。同上修。

3. **`journal-input` placeholder "记下你的想法..."** (`index.html:9901`) — 持仓笔记 textarea placeholder。同上修。

4. **`+ 加正股` button**（账户设置 stock 行） — 虽有 `data-i18n` 但模板字符串渲染时 inner text 还是中文，setLang 之前打开过 modal 就漏。修：button 内层改 `${t('+ 加正股')}` 即时翻译。

5. **`updateAddPreview` 兜底 hint "填写完所有必填字段后这里会显示预览"** (`index.html:11848`) — 函数动态 `innerHTML` 写入硬编码中文 span，覆盖了原 `data-i18n`。修：包 `${t(...)}` 即时翻译。

6. **`时间` 标签** (`index.html:8992`) — 持仓卡 `.pos-time` 显示 "时间 left X/Y days" 中英混搭，因为 `t('时间')` 调用但 zh_tw / en 字典都缺 key。**最显眼的 leak**（每张持仓卡都有）。补 zh_tw "時間" + en "Time"。

**截图栈**：`/tmp/qa-shots-3/<vp>/{01..16}.png`（30 张完整）。比 round 2 多出：pos-card-expanded（脚本绕开 click intercept）、compact toggle、6/7/8-rec modal 三种 goal 模式、09 add modal with preview、10 review、11 morning brief（实际渲染了 pos cards，showMorningBrief 不存在）、12 account modal、13 edu（无 modal）、14 EN data、15 繁中 data、16 light theme data。

**验证 round 1/2 已生效**：
- 手机 "Sign in" 按钮不再截断（mobile 01）✓
- 推荐 modal sticky padding 让最后一行 `EXIT STYLE` 完整可见（mobile 05）✓
- brief 标题 "Tue 5/19 · 13:53" 英文显示（mobile 01）✓
- 推荐表单 "Short premium: lower Δ = safer" 风险偏好 hint 英文 ✓
- 账户 modal "⚙ Set account to show capital usage" 英文 ✓

**未做 backlog**：
- pos-card 展开（点击展开 Greeks 和 exit_plan 详情）— playwright 脚本仍没找到正确点击元素，需要进一步研究 `.pos` 卡片实际 onclick handler 委托
- review modal、edu / options 101 modal — JS 函数名跟 playwright 脚本里的猜测不一样，需要 grep 真实函数名再加
- agent 静态扫报的 ld-mrung-head / exit-plan.compact baseline 类 — 仍需要候选卡片渲染（需要真跑 recommend 返回有效候选）

---

### 并行 session（2026-05-19 晚 · 用户报 4 bugs 一轮修复）

1. **🔍 找出最佳 按钮无反应** — `submitRec()` 在 `_savePref('rec_last_ticker', ticker)` 抛 `ReferenceError`（v2.1 多 ticker 改动把 `ticker` 重命名 `rawTicker` 漏一处）。整个 async 函数 reject，前端无反应。改回 `rawTicker`。
2. **管家今早未更新** — `_generate_morning_brief` 缓存键用 `date.today()`（UTC），美东凌晨用户登录时 UTC 已新一日，cache 命中 → 复用昨晚 22-23 点的 brief。改用 `America/New_York` 时区做"今天"。
3. **持仓选择同步后下次登录全部 unchecked** — `loadSelection` 把空 `[]` 当 truthy 返回 `Set([])`；strike 格式漂移导致 cloud ids 不匹配现持仓时 `selectAll-cleanup` 把 Set 清空。改：cloud / localStorage 都需要 length > 0；0 match fallback 默认全选；`saveSelection` 加 null guard。
4. **lang-selector 高亮 pill 高度不足** — `align-items: center` 让按钮只占内容高度，gold 背景没填满 34px pill。parent 改 `align-items: stretch`，button 加 `display: flex; align-items: center; justify-content: center`。

---

### 上一轮（2026-05-19 cloud · UI/UX QA round 2）

**主题**：Round 1 只在空状态扫，agent 报的"带数据组件 baseline 问题"看不到。这轮用 Playwright 在 navigate 前注入 4 个假持仓（TSLA / AAPL / NVDA / META），让 pos card / brief modal / chart / rec modal-with-data 都真渲染再截图。

**真 bug 修复**（2 处 i18n leak）：

1. **`_mbFormatTime` 硬编码"周X"** (`index.html:11685`) — 包租公管家 brief 标题在 EN 模式下显示 "5/19 周二 13:33"，中英混搭。改为按 `_lang` 切换：en → `Tue 5/19 · 13:33`，zh_tw → `5/19 週二 · 13:33`，zh → `5/19 周二 · 13:33`

2. **风险偏好 hint i18n 缺 key** (`index.html:10399/10393`) — `_RISK_BANDS.default.hint = '卖期权：Δ 越低越安全，权利金越少'` 被 t() 包裹但 **dict 没这个 key**，所以 EN/繁中模式下 `t()` 回退到原文（中文）。LEAPS 那条同样。补 2 个 key × 3 套字典 = 6 词条。

**复用 round 1 截图栈**：`/tmp/qa-shots-2/<vp>/{01-positions-loaded, 02-chart, 03-fullpage, 06-rec-modal-with-data, 07-rec-modal-scrolled-bottom}.png`。还有 8 个 surface 在 Playwright 脚本里但 pos-card click 被 modal backdrop intercept，留 backlog。

**已部署的 round 1 修复验证**：`padding-bottom: 84px` / `'设置账户可显示资金占比'` 翻译 / `'登录': 'Sign in'` 都在 prod ✓。截图里看到的中文 banner 是 Playwright run 跟 Vercel deploy 撞窗口，不是 fix 失效。

**round 2 backlog（带数据 baseline）**：agent 报的 `.ld-mrung-head` / `.exit-plan.compact` / `.edit-form` 等问题需要点开 pos card / 跑推荐有候选返回 / 触发 ladder builder 才能看到，本轮没截到。

---

### 并行 session（2026-05-19 cloud · 包租公式 exit_plan 全链路收尾）

接住候选卡片 2×2 网格 ship 后，3 项收尾全做完：
- **小白指南扩 5 词条**：新分类 🚪 出场触发线（房东人设 / 早收租 / 21 天换租 / 房客违约 / 红线）
- **renderPositionExitPlan 重写**：读 `_recSelection.exit_style`，选**最紧迫**触发线作 primary（红线>delta>DTE>profit gap），显示当前 vs 阈值；header 迷你 emoji 显示风格（🏠/🏘️/💰）；三语 7 新 key
- **position_advice 重写**：函数签名加 `exit_style`，整段重写为 4 触发线评估；每条按风格生成不同 actions；三语字典各加 ~40 模板；前端 body 带 `exit_style: _recSelection.exit_style || 'early_close'`

**v2 exit 路线全链路完成**：候选卡片 → 持仓卡片 → 侧栏 → 小白指南。

---

### 上一轮（2026-05-19 cloud · 包租公算法 v2.0 publish · 3 wave 收尾）

**7 件套**（参见 `CHANGELOG.md` 完整版）：
1. Score-verdict 统一（tier 改 rent_score 百分位驱动）
2. 回测同步 exit_plan（`_backtest_strategy` 路径模拟 50% 早平 + DTE cutoff，新增 `early_close_rate`）
3. DTE IV 自适应（IV ≥70 × 0.70 滑短 / ≤30 × 1.30 滑长）
4. 3 出场人设 UI（🏠 早收租派 / 🏘️ 接货 Wheel / 💰 死磕到期 — 替代 auto / wheel_purist 双选）
5. 🔄 Roll 建议器（持仓卡按钮，更长 DTE + 更 OTM strike + net credit）
6. 🔍 多 ticker 扫描（逗号分隔 `TSLA,NVDA,GOOG` 自动 scan_multi action）
7. 💎 财报 IV crush 红利（跨财报候选 verdict pro）

**ALGORITHM_VERSION**: 1.9 → 2.0；intro.html hero 更新；CHANGELOG.md 创建。

并行 ship 了包租公式 exit_plan 4 触发线渲染（候选卡片 2×2 网格 + 动作行，三语 i18n 补 40+ key）。
未做留下一轮：`position_advice` 还是固定阈值；`renderPositionExitPlan` 单行还是旧叙事；小白指南没补 5 个新词条。

---

### 上一轮（2026-05-19 cloud · UI/UX QA round 1）

**主题**：用户要求做 UI/UX 视觉 QA — "最容易出现的就是偏移或者不对齐"。装 Playwright Chromium 跑 3 viewport (desktop 1440 / tablet 768 / mobile 390) 截 6 个表面 = 18 张截图，配合 CSS 静态 agent 扫，定真假 bug。

**真 bug 修复（5 大类 + 7 个改动）**：

1. **i18n 漏翻** — EN/繁中模式下仍显示中文的 5 处：
   - `index.html:7387` ticker 空状态提示
   - `index.html:10163` 账户摘要"保证金/正股/修改"
   - `index.html:10165` 账户未设置提示"⚙️ 设置账户可显示资金占比"
   - `index.html:11842` 页脚"更新于 X · 自动每 30 秒刷新"
   - `index.html:5033` 推荐表单"目标数值"label（data-i18n 但 dict 缺 key）
   - 修：6 个新 i18n key × 3 套字典 = 18 个新词条；JS 调用全部用 `t()` 包

2. **手机推荐 modal sticky 底栏遮挡内容** — Cancel/Find Best 浮在 viewport 底部，把 "MONTHLY TARGET" 输入框压在底栏后面
   - 修：`.rec-form.modal` 加 `padding-bottom: 84px`（≥ 底栏 ~68px 高度），让最后一行表单内容能滚到底栏上方

3. **手机 "Sign in with Google" 按钮被截成 "Sign in wit..."** — `.user-badge` 在 mobile 是 `max-width: 110px / .name max-width: 64px / font-size: 11px`，"Sign in with Google" 字面宽度 ~95px，超 64px 限制
   - 修：登录按钮文案改用短 key `'登录'`（zh: 登录 / zh_tw: 登入 / en: Sign in）；原长 `'Google 登录'` 保留用于信息文案

4. **首页"包租公推荐指数"黄卡 → 箭头贴文字** — `.rec-btn-large` `padding: 16px 18px` + 箭头 `::after right: 18px` 导致长文案跟箭头贴住
   - 修：padding 改 `16px 38px 16px 18px` 给箭头留 20px

5. **3 处 baseline / 居中对齐** （agent 静态扫验证后的安全改）：
   - `.welcome-grant align-items: baseline` → `center`（大数字 + 小标签不再下沉）
   - `.rec-form h4 .x` 加 `line-height: 1`（20px 关闭 X 不再相对 14px 标题偏低）
   - `.lang-selector` flex 加 `align-items: center`（11px 字符不再浮在 34px 容器顶）

**没碰的 agent 建议**：agent 一共报了 16 条 CSS 改进，验证后**6-8 条值得改但需要带数据视觉验证**（如 `.ld-mrung-head` / `.exit-plan.compact` / `.edit-form` 等需要有持仓数据才能看到效果）。空状态截图看不到。等用户登录有数据后再回来扫这批。

**audit agent 命中率（UI 路线）**：CSS 静态报 16 / 已验真改 3，截图视觉发现 5 个静态扫漏掉的（i18n / sticky 遮挡 / 按钮截断 / 箭头贴边）。结论：**静态扫 + 真截图缺一不可**。

**部署**：本 commit push 后 Vercel 自动 build；建议用户在手机上 hard-refresh `/app` 验证：① 切英文模式 → 看页脚 / ticker 空提示 / 推荐 modal 都是英文；② 推荐 modal 拉到底 → MONTHLY TARGET 输入框完全可见；③ 顶部"Sign in" 按钮不再截断

---

### 上一轮（2026-05-19 cloud · v2 #3 + #4 收尾 — wheel_purist 出场风格 UI + per-ticker willing toggle）

**v2 #3 wheel_purist 出场风格 UI**：rec form 加新 row "5. 出场风格"（在风险偏好之后）：⚙️ 自动锁利（默认 50% / 200%）+ 🪜 持到到期。CSS 复用 risk row 2 列 grid。`_recDefaults.exit_style = 'auto'`。`submitRec` 传 body.exit_style。Backend 早已就绪。

**v2 #4 per-ticker willing_to_own 手动 toggle**：账户设置 modal 加"🎯 愿意接货清单"section：列表每行 ticker + 🟢想接/🔴不接 toggle + × 移除；添加 input + 两按钮（🟢/🔴）；数据存 `state._meta.willing_overrides = {TSLA:'on', AMD:'off'}`（CLAUDE.md §4.2 reserved namespace）；即时持久化；submitRec 带 body.willing_overrides；backend recommend() override 优先于自动推导；UX 解决两类盲区（想买没建仓 / 历史持股不想加）；不在列表的 ticker 沿用自动推导。

**v2 路线全 4 项完成**：#1 surface 字段 ✅ #2 ladder ✅ #3 wheel_purist ✅ #4 willing toggle ✅

---

### 上一轮（2026-05-19 cloud · QA P2 round 3）

**主题**：P0/P1 ship 完后清理 P2 杂项。原 audit 报"i18n 348 个 key 缺失"经详细核对**严重夸大**——绝大多数 key 实际存在，只是少数 zh_tw value 还是简体副本。

**真 P2 #1 — zh_tw 5 个未翻译副本**（i18n agent 1 round）：
- `wheel_hint_assigned_body` / `wheel_hint_hold_body` / `wheel_hint_source_assigned` / `wheel_hint_source_hold` — 简体字"下半场/卖/张/账户/来自"残留
- `+ 加正股` 用繁体习惯改成 `+ 新增正股`
- 修：surgical 改 5 个 value，再次扫确认整个 zh_tw dict 100% 干净

**真 P2 #2 — goal modal 数值空值兜底**：
- `submitRec` 里 `value: numEl ? (parseFloat(numEl.value) || 0) : 0` — 用户清空输入 → parseFloat 返回 NaN → `|| 0` 静默继续 → banner 显示 "$0 / 月" / "0% 安全度" 等无意义数字
- 修：检查 `goalDef.numLabel` + `Number.isFinite` + `> 0`；不通过 alert 提示并 focus，submit 阻断；新增 i18n key `'请输入'` 三语

**audit 误报（i18n 部分）**：
- 后端 TRANS_EN / TRANS_TW 完全对称 108/108，agent 报的"完全完整"反而是对的 ✓
- 前端字典所谓"缺 164/184"实际是把"未翻译副本"也算成"缺失"，真缺失约 5 个量级
- `_T()` fallback 到 zh key 是预期行为（无翻译就显示中文），无 bug

**P2 安全 review**（无修复方案）：
- `_verify_admin_token` 无本地 JWT 签名验证 — 完全依赖 Supabase /auth/v1/user 回调，没有 JWT_SECRET 无法本地验。已记 backlog

**QA 三轮总览**（这条 thread）：
- **P0 round 1**（commit 68fe683）：BS 边界 guard + position_id 小数 strike 一致化
- **P1 round 2**（commits 5ae6b83 + adba1f8 → rebased a8b4443）：`_meta` 计数 + recommend log 阻塞 + selectedIds null + 模块级 JSON.parse
- **P2 round 3**（本 commit）：5 个 zh_tw 繁中瑕疵 + goal 数值校验

**audit agent 命中率**：
- 前端 JS audit：6 报 / 实 2 真 bug（#4 事件重复绑定 / #7 goal 残留都是误报）
- 后端 Python audit：12 报 / 实 3 真 bug（多数 P0 边界条件误报）
- i18n audit：348 报 / 实 ~6 处（"缺"=未翻译副本，不是真缺）
- 数据一致性 audit：10 报 / 实 1 真 bug（state._meta 计数）

**结论**：agent 适合"广撒网定位嫌疑点"，但**每条都需要人盯代码验证**才能定真假。盲目按 agent 报告修会引入新 bug。

---

### 上一轮（2026-05-19 cloud · QA P1 round 2）

**主题**：接 P0 round 1 之后把 P1 池 9 条逐条验证 + 修。验证后 5 条是 agent 误报（详见末），4 条是真 bug，全修。

**真 P1 #2 — state 计数未排除 `_meta`**（commit a8d65bb 已 ship）：
- state._meta 用作偏好 namespace（selection / brief_snapshot / welcome_seen / account），用户登录后几乎立刻就有
- 5 处 `Object.keys(state).length` 被污染。最危险是 `_migrateLocalToCloud` 的"云端非空"门 → 纯新用户被误判 → 本地持仓被静默跳过迁移
- 修：新增 `_stateRealKeys(s)` helper 过滤 `_meta`，6 处统一调用

**真 P1 #4 — `recommend` usage log 阻塞响应**（本 commit）：
- 原流程：`result = recommend(payload)` → `log_usage_event(...)`（同步调 Supabase, timeout=5s）→ `_send_json`
- Supabase 抖动 → 用户多等最多 5s 才看到推荐结果
- 修：调换顺序 → 先 `_send_json` + `wfile.flush()` 把响应发出去，再做埋点，最后 `return` 跳过末尾的 send；`log_usage_event` 内部 timeout 从 5s 降到 2s 双保险

**真 P1 #8 — `selectedIds.add` null deref**（本 commit）：
- 初始 `let selectedIds = null`，首次 refresh 完才赋 `new Set()`
- `addRecToPositions` / `submitAdd` 在 refresh 跑完前被触发 → `null.add(...)` NPE
- 修：两处 `selectedIds.add(newId)` 前加 `if (selectedIds)` 守卫

**真 P1 #9 — 模块级 `JSON.parse` 无 try/catch**（本 commit）：
- Line 9275：`const _recSelection = { ...localStorage.getItem('rec_last_choice') ? JSON.parse(...) : _recDefaults }` 不在 try/catch 里
- localStorage 损坏（扩展 / 早期版本残留 / 跨域写入）→ 模块加载阶段抛 → **整个 app 启动失败**
- 修：包成 IIFE + try/catch，失败回退到 `_recDefaults`，spread 顺序保证用户已存的字段优先

**agent 误报（5 条）**：
- #1 `showRec` 事件重复绑定：`.onclick = fn` 是赋值不是 addEventListener，替换不堆叠 ✗
- #3 三级 fallback 静默吞：实际有 `chain_stats` + `_summarize_data_source` + `schwab_last_err` 透出 ✗
- #5 `is_willing_to_own` UI undefined：前端整个文件根本没 grep 到这个字段，agent 给的行号错了 ✗
- #6 cache 跨日污染：30min TTL 已经覆盖所有合理边界（after-hours 不影响、跨日开市远超 30min）✗
- #7 goal 切换数值残留：已在 b4bfb59 正确修过，"同 goal 保留用户输入"是 intentional ✗

**下一阶段**：P2 杂项（重点是 i18n — zh_tw 缺 164 个 key、en 缺 184 个，wheel_hint_* / lesson_* / 账户管理类批量缺）。需要用户判断优先级。

---

### 上一轮（2026-05-19 cloud · v2 #2 ladder builder）

**主题**：v2 路线第 2 项 — 用户给 ticker + 接货总预算，算法返回多档 strike 阶梯组合（灵感来自"他的国"实盘 NVDL 6 档 / TQQQ 4 档）。

**Backend**（`api/state.py`）：
- 新 `build_ladder(candidates, budget, size=4)`：
  - 仅 CSP；选候选最多的 expiry；按 |delta| 升序均匀挑 size 档；按 budget 等量分配 contracts
  - 聚合：总抵押 / 总 premium / 加权 prob_safe / 加权 EV / 组合年化
  - `is_affordable` / `min_budget_needed` 标志
  - 每个 rung 含 ticker/strike/expiry/days/type/contracts/mid/delta/prob_safe/EV/VRP
- `recommend()` 增加 `req.ladder = {budget, size}` 触发；仅 short put 适用
- 响应顶层增加 `ladder_proposal`

**Frontend**（`index.html`）：
- 新 goal card "🪜 搭阶梯组合"，REC_GOALS.build_ladder（默认 \$100k）
- 提交时若是 ladder goal，`body.ladder = {budget, size:4}`
- `renderLadderProposal(d)` 渲染在候选列表顶部（goalBanner 后）：
  - 4 KPI（总抵押 / 总 Premium / 加权 prob_safe / 加权超额收益）
  - 桌面表格（Strike/Δ/张/Mid/Premium/Prob/EV），每行 data-rung=r0..r3 控色阶（A+ 方案）：
    - 3px 左色条 + 水平 fill 宽度（35%→100%）+ Strike 文字色（绿→金→红）
    - 最安全 / 激进 标签
  - 手机：表格 → mini 卡（同色阶处理）
  - is_affordable=false → 红色 warning
- `_ladderAddAll()`：confirm 模态列每档明细 + 总计 → 批量加入 positions（跳过逐张 prompt）

**UX 流程**（用户视角）：
1. 进推荐表单 → 切到"目标驱动"mode → 选 "🪜 搭阶梯组合"
2. 输入预算 (默认 \$100k) → 输入 ticker → 找出最佳
3. 顶部出现 ladder 卡片 + 4 个候选个体卡 (含阶梯里的 4 档)
4. 点 "一键加仓" → 确认 → 批量录入 4 张持仓

**按 §9 流程**：建预览页 v2-ladder.html 给 A/B/C/A+ 4 个变体 → 用户选 A+（A 表格 + C 色阶融合）→ 套到 index.html → 删预览。

**i18n 三语补 29 个 key**：goal 文案 + ladder 卡标签 + 警告 + alert 文案。

**待用户验证**：
- [ ] hard-refresh `/app` 进推荐表单切目标驱动 → 看到 "🪜 搭阶梯组合" goal card
- [ ] 选它 → 输入 ticker + 预算 → 提交 → 顶部应该出现金色 ladder 卡片含 4 档色阶
- [ ] 桌面 hover 表格行 / 手机查看 mini 卡，色条 + 渐变 fill 都应正常
- [ ] 点"一键加仓 (4)" → confirm 显示每档明细 → 确定后批量录入
- [ ] 切英文 / 繁中 → 标签 + 警告都翻译

---

### 上一轮（2026-05-19 cloud · QA P0 round 1）— BS 边界 guard + position_id 小数 strike

**主题**：用户让 QA 资深视角系统扫一遍 bug 池。并行起 4 个 audit agent（前端 JS / 后端 Python / i18n / 数据一致性），归类成 P0/P1/P2 表。用户选"全修"分阶段做，P0 自主推。

**P0 #1 — BS 定价边界**（`api/state.py` `bs_call` / `bs_put`）：
- 原代码已 guard `T<=1e-8 or sigma<=0`，但 `S<=0` 或 `K<=0` 仍会让 `math.log(S/K)` 抛 `ValueError`
- 触发：Schwab + Yahoo + yfinance 三级 fallback 全挂 → underlying=0 → 整个推荐 endpoint 500
- 修：前置 `if S<=0 or K<=0: return 0/0 价格` 安全返回

**P0 #2 — `position_id` decimal strike 坍缩**（`api/state.py` 8 处 + `index.html` 3 处）：
- 原：后端 `int(p['strike'])`、前端 `parseInt(p.strike)` 把 100.5 截断成 100
- 触发：SPX / 部分 ETF / 小价位股有 0.5 strike → 两个不同的 100 put 和 100.5 put 共用同一 pid → state.closed 永远绑错；候选 id（`${o.strike}`）保留 ".5" 跟 pid 不匹配，UI "已加仓"判断错
- 修：新建 `_fmt_strike(s)` helper（前后端各一份），整数 → "100"，小数 → "100.5"。两端字符串严格相同。已对 0/100/100.0/100.5/0.5/700000 单测过

**关键自检**：
- Python `_fmt_strike` 和 JS `fmtStrike` 对所有典型 strike 输出**字符串完全相同**
- 整数 strike 的输出和老逻辑兼容（"100" → "100"），存量用户的 state map 不受影响
- 小数 strike 的输出从"截断成整数"变成"保留小数"，是修 bug，不是 breaking change

**没碰到的 P0 候选**：agent 报的"`_make_verdict` 在 v1.4 fallback 时 f-string 崩"经验证已有 `ev_pct is not None` guard，不是 P0，从池里删了。

**下一阶段**：P1（9 条）+ P2（含 i18n 348 个缺 key）需要逐条过用户。等用户回来再起。

---

### 上一轮（2026-05-19 cloud · v2 #1 surface v2 fields）

**主题**：v1 backend 已 ship 但前端没显示 EV / VRP / RV / 压测 / 资金占用 — 价值看不见。按 §9 建预览页 `v2-cards.html` 让用户选 A/B/C，**用户选 B（结构化信号 box）**，并要求"hover 时小白能看懂的解释" + "概念加到小白指南"。

**核心实现**（`index.html`）：

1. **新 `renderV2Sigbox(opt, isShort)`**（line 6947 后）：候选卡片 `rec-metrics` 下方插入"📊 包租公 2.0 信号" box。6 行：年化边际收益 / VRP / 已实现波动率 / 压测 -5% / 压测 -10% / 接货占现金。每行带颜色（good/warn/bad）+ tag + `?` 帮助 icon。仅 `used_v2_base=true` 时显示，v1.4 fallback 静默。

2. **Hover/tap tooltip**（line 2030+ CSS）：`[data-tip]::after` 伪元素，hover/focus 时绝对定位显示；移动端点击行 toggle `.show-tip` class 同样显示。5 个 tooltip 长文案 `tip_ev` / `tip_vrp` / `tip_rv` / `tip_stress` / `tip_capital`，大白话解释怎么算 / 怎么用。

3. **小白指南扩容**（EDU_TOPICS）：新增分类"📊 包租公 2.0 信号（高阶）"，5 个词条（EV / VRP / RV / 压测 / 接货占现金），每个含 desc / 例子 / care + 三语字段。

4. **i18n 三语补 24 个 key**：sigbox 标签 + 5 个长 tooltip 文案 + EDU 分类名 + tag 词。

5. **清理**：删 `v2-cards.html` 预览页 + `vercel.json` 移路由（rebase 时和 main 的 admin.html 添加冲突，已解掉）。

**待用户验证**：
- [ ] hard-refresh `/app` 对 TSLA 跑 CSP → 候选卡片显示"📊 包租公 2.0 信号" box
- [ ] hover ? icon → tooltip 弹出
- [ ] 移动端 tap 整行 → tooltip 显示
- [ ] 小白指南滚到底有新分类 + 5 个新词条
- [ ] 切英文/繁中 → 标签 + tooltip + EDU 都翻译

---

### 上一轮 hotfix（2026-05-19 cloud · `api/state.py` `portfolio_history`）— 每日 P&L 图表"今日点"与 hero 数字对不上

**问题**：截图里图表 tooltip 显示 "2026-05-19 已选总 P&L: $-202.00"，但顶部 hero "未实现盈亏" 显示 "+$226.00"，相差 $428。

**Root cause**：图表的"今日点"在 `portfolio_history` 里用 **BS 模型 + 交易日反推的 IV** 重新定价；而顶部 hero 用 `enriched.pnl`，后者来自 **实时期权报价**（Schwab/yfinance mid）。两条路径数据源不同：
- IV 用的是交易日反推的（trade-day IV），不是当前 IV → IV 变化 → mark 偏移
- mark = BS(u, K, T, r, trade_iv) ≠ 市场 mid（spread / 流动性 / 真实 vol surface）

历史日（trade_date → 昨天）只能用 BS（没有当时的期权报价），可以接受。但**今日点**完全可以直接用 enriched 的实时报价。

**修复**：`portfolio_history(...)` 新增 `enriched=None` 形参，main handler 把已富集的持仓传进来。今日点直接使用 `e.pnl` / `e.sold` / `e.id`，跟 hero 数字同源 → 不再对不上。历史点逻辑不变（仍是 BS）。

调用点：`enriched = [position_state(...) for p in positions]` 已在 history 之前算出，按顺序传入即可。

**遗留**：今天点和昨天点之间会有视觉上"小跳"（昨天 BS，今天市场 mid）。这是真实数据差异，不是 bug — 用户最关心的是当前 P&L 跟 hero 一致。

---

### 上一轮（2026-05-19 cloud — usage tracking + /admin 面板上线）

### ✅ feature（2026-05-19 cloud · usage 埋点 + /admin 后台）

**目标**：用户可在 /admin 看到每个登录用户用了多少次推荐、复盘、早安简报、登录次数。先只埋点，额度不卡。

**改动**：
- `supabase/usage_events.sql` — 新表 schema（需要用户在 Supabase SQL Editor 跑一次）。RLS 启用 + 默认无 SELECT policy → 只有 service_role 能读。
- `api/state.py` —
  - 新 section "Usage tracking"（Schwab 之后、yfinance 之前）：`_supabase_request` / `log_usage_event` / `_verify_admin_token` / `admin_stats`
  - `do_POST` 加 3 路：`recommend` 末尾自动埋点（带 goal/risk/candidates_n/top_tier/error_kind）；`log_event`（前端来源，白名单 4 个 event）；`admin_stats`（JWT 验证 + 内存聚合）
- `index.html` —
  - `_logUsage(event, metadata)` helper（fire-and-forget，无登录 noop）
  - `_onSignedIn`：每天每用户每会话一次 `login` 或 `first_login`（用 sessionStorage 防抖）
  - `showReview`：每次开复盘 modal 记一次 `review`
  - `renderMorningBrief`：每天每用户每会话一次 `morning_brief_view`
  - `submitRec`：请求 body 加 `user_id` / `user_email`，后端用来落 usage_event
- `admin.html` — 新建 /admin 仪表盘。Google 登录后客户端验 email 白名单，调 `admin_stats` 拿聚合数据（核心指标 / 事件分布 / 30 天 sparkline / top 25 用户 / 推荐健康度）
- `vercel.json` — 加 admin.html build + `/admin` 路由

**需要用户做**（一次性）：
1. 去 Supabase Dashboard → SQL Editor，跑 `supabase/usage_events.sql`
2. 去 Vercel 项目（option-analysis-platform-web） → Settings → Environment Variables → 加 `SUPABASE_SERVICE_ROLE_KEY`（Supabase Dashboard → Settings → API → service_role secret，⚠️ 不是 anon key）
3. 验证：访问 https://trade.congyangwang.com/admin → Google 登录（hi@congyangwang.com）→ 应能看到 dashboard。如果空，先去 /app 用一次推荐，回来刷新。

**安全设计**：
- `log_event` 白名单 event 类型（login/first_login/review/morning_brief_view）。user_id/email 来自前端，不可信，最坏情况是被冒充制造噪声事件 — 可接受。
- `admin_stats` 接受前端传的 Supabase access_token，后端调 `/auth/v1/user` 验证 + 检查 email ∈ ADMIN_EMAIL_WHITELIST。无效 token / 非白名单 email 返回 `unauthorized`。
- 服务端用 `SUPABASE_SERVICE_ROLE_KEY` 调 REST API 插入/查询，绕过 RLS。

**没埋什么**：未登录用户不埋（设计），匿名分享视图不埋，share view 下也不发 brief_view。

**没做的扩展位**（以后想做时改这里）：
- 真要加额度/coin 系统 → 在 `log_usage_event` 之前查月度 count，超额返回 `{ error: 'quota_exceeded' }`，前端识别后弹付费/升级
- 想看小时粒度活跃 → admin_stats 已有 `by_day_30d` 框架，按小时聚合改一下 strftime 即可

---

### ✅ hotfix #2（2026-05-19 cloud · `index.html:9072` `applyGoal`）

**问题**：用户报"没有候选达到 ≥ 300% 安全度"。max_safety 默认 85%，怎么会是 300？

**Root cause**：用户之前选过 stable_rent (默认 $300/月)，输入框留下 "300"。切到 max_safety 时 label / unit 都变了 (安全度下限 %)，但旧逻辑只在空值时填默认 → 残留 300 被解读为 **300% 安全度** → 永不满足。

不同 goal 数值语义完全不同（$/月 vs % vs $strike），保留前一个 goal 的值无意义。

**修复**：检测 goal 真正切换 (`_recGoalKey !== key`)，切换时强制重置为新 default（或清空）。重复点击同一 goal 仅在空值时填默认（保留用户输入）。

---

### ✅ 这一轮 hotfix #1（2026-05-19 cloud · `index.html:9271`）

**问题**：用户反馈"TSLA 敞口 11 张 short put · 15 张 short call · 抵押 $438k · 占账户 893.9%"，张数远超实际。

**Root cause**：推荐请求构建 `openOptionPositions` 时用 `.filter(p => !p.closed)`，但 `closed` 标志存在 **state map** 里（按 position_id 索引），不在 position 对象上 → `p.closed` 永远 undefined → filter 永不剔除 → 所有历史持仓（含已平仓）都进 `option_positions` → `_portfolio_context` 全部累加 → 数字膨胀。

副作用：`willing_to_own` 自动推导也被污染（有过 short put 历史的 ticker 永远 willing，不一定符合当前偏好）。

**修复**（`index.html:9270-9281`）：
```js
const __stMap = loadStateMap();
const openOptionPositions = loadPositions()
  .filter(p => {
    const st = __stMap[posIdOf(p)];
    return !(st && st.closed);
  })
  .map(p => ({ ... }));
```

只影响推荐请求构建。前端展示侧用 `d.positions`（后端已富集 closed 字段），不受影响。

---

### 上一轮（2026-05-19 cloud — 包租公算法 2.0.1 · capital_risk 双重计算修正）

**问题**：用户反馈 prod 上"看到好几次资金不足"警告。

**Root cause**（`_capital_risk_check`）：
- UI 上"账户可用保证金"=用户填的 broker dashboard Available to Trade（**已扣除**现有持仓后净可用现金）
- 但我在 `_capital_risk_check` 里又**叠加了**现有所有 short put 的累计抵押 → **双重计算**
- 加上 `suggested_contracts` = avail × 20% 自动算，所以现有持仓占可用 ≥ 40% 就触发 60% 阈值 warning，太常见

**修复**（一笔）：
1. 删 `existing_commit` 叠加：只算 `this_commit / avail_cash`
2. 阈值放松：veto > **100%**（真超额）/ warning > **80%**（占大头）
3. warning **从 verdict cons 拿掉**（只作 metadata 字段，避免 v1 UI 噪音）
4. veto 文案改 factual：`🚫 接货需 ${X,YYY}，超过可用现金 ${A,BBB}`
5. veto label 改"可用现金不够接货"（更直白）

**Smoke**：
- 1 张 $40k / avail $300k = 13% → ok ✓
- 1 张 $90k / avail $100k = 90% → warning（不进 cons）✓
- 3 张 $40k / avail $100k = 120% → veto（cons 显示金额）+ tier=2 ✓

---

最后更新：2026-05-19（cloud — 包租公算法 2.0 · EV/VRP + willing_to_own + 资金占用 + 杠杆 ETF + 压力测试）

### ✅ 上一轮（2026-05-19 cloud · `claude/improve-recommendation-algorithm-Gid32`）

**主题**：用户主动发起讨论"推荐算法有没有变得更厉害更正确的空间"。深度讨论后落地 v2.0 算法（backend-only，前端不动，按 §9 留 v2 走预览页）。

**讨论收敛**（4 轮）：
1. 我提了 7 个可改点，用户挑了 EV/VRP + 集中度 + verdict 统一 三块
2. 用户反对"集中度惩罚"（Wheel 派"all in TSLA"是 conviction 不是风险）→ 我同意，改成 **willing_to_own + 资金硬上限**
3. 用户问"明日跌 5% gamma 风险算法怎么考虑" → 加 **stress test 透明披露**（不进 score，只出数）
4. 用户晒别人的实盘截图（NVDL/TQQQ/SOXL 等 3x 杠杆 ETF + 6 档阶梯 + 无平仓）→ 吸收**杠杆 ETF 警告** + `wheel_purist` 出场风格；阶梯 ladder builder 留 v2

**核心改动**（`api/state.py`，~250 行）：

**新 helper**（line 1843 前）：
- `LEVERAGED_ETF` set：~50 个 2x/3x 指数 ETF + 单股杠杆产品（NVDL/TSLL/TQQQ/SOXL/SQQQ/...）
- `_is_leveraged_etf(ticker)` membership check
- `_realized_vol(ticker, window=30)`：yfinance close-to-close 对数收益率 × √252，年化波动率
- `_stress_test(opt, underlying, iv, is_call, is_short)`：BS 重新定价标的朝不利方向 -5% / -10%，IV 同时 pump 15%/30%（vol-of-vol 经验）。返回 `adverse_5pct` / `adverse_10pct` 字典，每个含 `mtm_pnl_$` / `mtm_pnl_pct_of_collateral` / `new_delta`。仅 short premium 关心。
- `_capital_risk_check(candidates, option_positions, avail_cash)`：累计现有未平仓 short put 抵押 + 当前候选若被指派，对比 avail_cash。> 95% → veto；60-95% → warning；其他 → ok。in-place 给每个 candidate 加 `capital_risk` / `capital_pct` / `capital_commitments`。激进阈值。

**`_landlord_score` 2.0 重写**：
- 新签名加 `realized_vol` / `is_leveraged_etf` / `is_willing_to_own` 三参
- **base 换成"年化 EV %"**：`fair_value = bs_put(S, K, T, realized_vol_30d)`，`edge = mid - fair_value`，`EV_annualized = edge / strike × 365/days × 100`。floor 0.5 防归零。
- 经济意义：VRP > 1 时正 EV（IV 比实际 vol 高 = 卖期权赚溢价），VRP < 1 时负 EV（你在亏卖 vol）
- v2 base 启用时 `safety = 1.0`（已隐含 N(-d2_RV) 不双重计分），`iv_f = 1.0`（已被 EV/VRP 吸收）
- 新增 `wto_f`：CSP on willing-to-own ticker × 1.08（被指派 = 接到想要的股票）；CC × 0.97（你不想被叫走）；**杠杆 ETF 例外，wto_f 永远 = 1.0**
- realized_vol 不可用时回退 v1.4 公式，backward compatible
- components 多吐：`ev_annualized_pct` / `realized_vol_pct` / `vrp_ratio` / `fair_value_per_share` / `wto_factor` / `used_v2_base` / `is_leveraged_etf` / `is_willing_to_own`

**`_make_verdict` 加 3 类新信号**：
- EV / VRP：v2 时 `ev_pct < 0` 加 con "正在亏卖 vol" (-2)；`ev_pct > 15 且 VRP > 1.20` 加 pro "年化边际收益 X% (VRP Y.YY)" (+2)；`ev_pct > 5` 加 pro 弱 (+1)
- 资金占用：`capital_risk = veto` → cons "🚫 若被指派 + 现有 short put 占现金 X% (>95%)" + weight -5 + **强制 tier 顶到 2 星**；`warning` → cons "⚠️ 接货后现金占用 X%" + weight -1
- 杠杆 ETF：`is_leveraged_etf and is_short` → cons "⚠️ 杠杆 ETF — 长期持有有波动率衰减损耗，wheel 回本慢" + weight -1
- 新增 `is_leveraged_etf` 参数

**`_exit_plan` 加 `exit_style` 参数**：
- 默认 `"auto"` = v1.4 矩阵行为
- `"wheel_purist"` 覆盖：profit_pct=100（持到到期）、stop_pct=None、roll_trigger="assigned_only"、summary_key=`exit_summary_{kind}_wheel_purist`
- v1 只加 backend 参数，UI 选择器留 v2 走 §9 预览页

**`recommend()` 主流程**：
- 新计算 `realized_vol_30d` / `is_leveraged_etf` / `is_willing_to_own`（自动推导：持股 ≥100 或 已有 short put on this ticker）
- 读 `req.exit_style`（默认 auto，校验白名单）
- 第一轮 loop 末加：`_stress_test` → `c["stress_components"]`；`c["is_leveraged_etf"]` / `c["is_willing_to_own"]` 标 candidate
- **拆分 verdict 到 loop 外**：因为 verdict 现在依赖 `capital_risk`，而 `capital_risk` 依赖第一轮算好的 `suggested_contracts`。两轮：第一轮算 score + stress + exit_plan + suggested_contracts；然后 `_capital_risk_check` 全表过一遍；再第二轮算 verdict
- 响应顶层多吐：`realized_vol_30d_pct` / `is_leveraged_etf` / `is_willing_to_own` / `exit_style` 透明字段

**`ALGORITHM_VERSION`**：1.2 → **1.9**

**自检**（pure-python unit tests，无 network）：
- `_is_leveraged_etf`：TQQQ/NVDL=T，TSLA/AAPL=F ✓
- `_landlord_score` v2 (TSLA $400 put, 30 DTE, IV=45%, RV=35% → VRP=1.286)：score=15.68，EV=12.78%，wto=1.08 ✓
- VRP < 1 (RV=50%)：EV=-6.59%，score 缩到 0.55 (floor) ✓
- realized_vol=None → 走 v1.4 fallback，score=2.3，used_v2=False ✓
- 杠杆 ETF + willing → wto_f=1.0 (bonus 被屏蔽) ✓
- `_stress_test`：TSLA -5% (S=399, IV pump→51.7%)，put 12→23，MTM=-$1094=-2.7% collateral；-10%：MTM=-$2507=-6.3% ✓
- `_capital_risk_check`：existing $35k + this $80k = 76% → warning；3 张 $40k strike vs $100k 现金 = 120% → veto ✓
- `_make_verdict`：veto 强制 tier=2；杠杆 ETF cons 命中；wheel_purist exit_plan profit=100/stop=None ✓

**前端没动**（按 §9）：v2 才做预览页把 `ev_annualized_pct` / `vrp_ratio` / `stress_components` / `capital_risk` 这些新字段渲染出来。当前用户在 UI 上仍只看到 rent_score 数字（数量级会变，因为 base 从 period_roc 换成 EV），star tier 和 verdict pros/cons 字符串会自然带新信号（因为已经是动态拼接）。

**待用户验证**：
- [ ] curl `/api/state` 推荐路径不爆 5xx
- [ ] 已登录用户对 TSLA / NVDA 等持仓 ticker 的 CSP 推荐应该看到新 pros：「💰 年化边际收益 X% (VRP Y.YY)」「📊 ...」
- [ ] 杠杆 ETF（TQQQ/NVDL）推 CSP 应该看到 cons：「⚠️ 杠杆 ETF — 长期持有有波动率衰减损耗」
- [ ] avail_margin 不够时（user 在账户设置填可用现金 < 现有 short put 总抵押 ×1.05）应该看到 capital veto，tier 被压到 2 星
- [ ] realized_vol 偶尔 None 时不爆错（应该走 v1.4 fallback）

**v2 路线**（未做）：
- 前端 UI surface：ev_annualized_pct / VRP / stress_components / capital_risk → 候选卡片渲染（要走 §9 预览页）
- wheel_purist 出场风格的 UI 选择器（risk profile 旁边加一个 dropdown）
- ladder builder 模式：输入 ticker + 总愿意接货金额，输出 3-5 档 strike 组合，捆绑卖出建议
- per-ticker 手动 willing_to_own toggle（v1 自动推导覆盖不到"我想买 GOOG 但没建仓"的情况）

---

### 上一轮（2026-05-18 cloud · `claude/cross-ticker-comparison-Ha2I6`）— 候选对比支持跨 ticker

**主题**：用户报"候选对比功能应该支持跨 ticker"。

**Root cause**（`index.html:7155-7159` 旧逻辑）：
`window._compareSelected: Set<candId>` 是 window 全局 — 跨 ticker **勾选状态保留**。
但 `showCompare()` 用 `window._lastCandidates.filter(...)` 从**当前 ticker 推荐结果**里反查候选数据。
`_lastCandidates` 每次切 ticker / 重跑推荐就被覆盖。所以：
- pill 显示 5 个 → ✅ 计数正确
- 点开 modal → ❌ 只看到当前 ticker 那 2 个

**修复**：把候选数据**快照**存进新加的 `window._compareCandidates: Map<candId, snapshot>`，跟 Set 一起维护。`showCompare` 改成从 Map 取数据，跨 ticker 也能完整查到。

**核心改动**（`index.html`）：

1. **数据流** (`index.html:7140-7172`)：
   - 新增 `window._compareCandidates = new Map()`，key=candId，value=候选完整快照（含 `_isShort` 标记，来自勾选时的 `_lastRecMeta.is_short`）
   - `toggleCompareSelect(candId, true)` 时从 `_lastCandidates` 找到候选并 `{...cand, _isShort: meta.is_short}` 存 Map
   - 取消勾选 / `clearCompareSelect()` 同时清 Map

2. **showCompare 重写** (`index.html:7207-7357`)：
   - 数据源换成 `Array.from(window._compareCandidates.values())`
   - 智能选指标集（用每条候选自己的 `_isShort` 而不是 `_lastRecMeta`）：
     - 全 short → short 集（12 指标，含包租公分 / 年化收益）
     - 全 long → long 集（12 指标，含杠杆 / Vega）
     - 混合 short/long → 通用集（10 指标，去掉 short-only/long-only 的字段）
   - 跨 ticker 检测：`new Set(list.map(o=>o.ticker)).size > 1`
   - 指标标 `abs: true` 的（Mid 价 / 权利金/张 / Theta/天 / Vega/1%）跨 ticker 时**关闭绿/红高亮** — 用户已确认这是首选行为
   - 头部 banner 提示（`.cmp-hint-banner` 金色 left-border）：跨 ticker 提示 + 混合 short/long 提示，按需出现

3. **UI 微调** (`index.html:2621-2645`)：
   - 跨 ticker 时表头 ticker 渲染成色调 chip（基于 ticker 字符串 hash 的 hue），不同股票一眼能分辨
   - 同 ticker 时仍是原来的纯文本（无视觉变化）

4. **i18n 三语补 2 个 key**：
   - `cross_ticker_abs_hint` — 跨 ticker 提示
   - `mixed_short_long_hint` — 混合卖出/买入提示
   - 三套都补：`index.html:4826-4827` (zh) / `5405-5406` (zh_tw) / `6118-6119` (en)

**用户设计选择**（AskUserQuestion 已确认）：
- 跨 ticker 绝对值高亮：**关闭 + 顶部小字提示**（避免 NVDA 100 vs AAPL 200 这种永远偏向高价股的误导）
- 跨 ticker 切换：**保留前一个 ticker 的勾选**（这就是"跨 ticker 对比"的核心场景）

**已知边缘情况**：
- 用户重跑推荐导致同 candId 数据更新 → Map 仍存旧数据。低概率，先不处理。
- 5 个候选上限保留（同 ticker 时也是这上限，没变）。

---

### 更早一轮（2026-05-18 cloud · `claude/fix-window-scrolling-Ok62X`）— 账户设置 modal 滚动修复

**主题**：用户报"账户设置窗口不能上下滚动"。截图显示账户 03 被截断到屏幕底部、无法滚动到底。

**Root cause**（`index.html:11085`）：
`showAccountSettings()` 用 `modal.style.display = 'block'` 打开 modal，但 modal CSS 是 flex column layout：
- `.am-header { flex-shrink: 0 }` / `.am-body { flex: 1; overflow-y: auto }` / `.am-actions { flex-shrink: 0 }`
- 父容器 `.account-modal { max-height: min(720px, calc(100dvh - 40px)); overflow: hidden }`
- `.account-modal.show { display: flex }` 本来应该激活 flex container

但 **inline `display: block` 优先级高于 `.show` class** → 父不是 flex container → `.am-body` 的 `flex: 1` 不生效 → body 按内容自然撑高 → 超出 max-height 被 `overflow: hidden` 剪掉，看起来就不能滚。

**修复**：把 `'block'` 改成 `'flex'`（最小一字之改）。

---

### 更早一轮（2026-05-18 cloud — 只读分享链接重做 · ✅ 用户验证通过）

### `claude/fix-readonly-link-generation-RedjD`

**主题**：用户报"生成只读链接的功能有问题"。经过 4 轮迭代最终落地。

**最终设计**：
- 接收方看到**完整页面**（早安管家 / Summary / sparkline / 推荐指数 / 复盘 / 操作建议 / 期权指南 / P&L 图 / 持仓卡），价格全部冻结在分享时刻
- 默认**所有元素都禁交互**（hover 无指针变化、点击无反应）
- 唯一例外：**包租公推荐指数**按钮加金描边发光暗示可点 → 点了跳首页 `/`（intro）引导对方注册自用
- 顶部金色 banner 提示是只读快照 + ts，banner 上"打开我自己的"链接可回主 app
- URL 格式：登录 `/app#s=<8char>` 短链 / 未登录 fallback `/app#share=<base64>` 长 fragment

**核心改动**（`index.html`）：

**前端 share 逻辑** (`index.html:8235-8452`)：
- 新 `_b64UrlEncode/_b64UrlDecode`（用 `TextEncoder/TextDecoder`）
- 新 `_trimPositionForShare(p)` 取富集字段：mark/pnl/Greeks/status/exit_plan/earnings 全冻结
- 新 `_genShareKey()` 8-char base62（避开 0/O/1/l/I）
- `generateShareLink` async：登录 → Supabase 短链 / 未登录 → fragment fallback
  - encode 时 `filter(p => !p.closed)` —— 只分享活跃持仓，Summary 数字才跟原始端一致
  - encode 早安管家：分享者今天 x 掉了就 `morning_brief = null`
  - encode tickers / intraday / suggestions / history 让接收方看到完整页面
- `loadFromShare` async 三格式：`#s=<key>` / `#share=<base64>` / `?share=<base64>`（向后兼容）
- 剔除 `state._meta`（隐私）：broker / margin $ / prefs / 管家缓存全不分享

**Share view 行为** (`index.html:11400+`)：
- `refresh()` 入口短路：share view 用 snapshot 直接 render，不调后端
- `_bootstrap` async：share view 跳过 supabase init / setInterval / visibilitychange
- `renderMorningBrief` 入口加 `_isShareView` 守门：不查接收方 localStorage dismissed flag

**CSS** (`index.html:4150-4187`)：
```css
body.share-view * { pointer-events: none !important; cursor: default !important; }
body.share-view #share-banner, body.share-view #share-banner *,
body.share-view #share-modal, body.share-view #share-modal *,
body.share-view .rec-btn-large, body.share-view .rec-btn-large * {
  pointer-events: auto !important;
}
body.share-view .rec-btn-large {
  cursor: pointer !important;
  box-shadow: 0 0 0 1px var(--accent), 0 4px 14px rgba(230,184,106,0.25);
}
```
+ hide `.cloud-sync-status / #add-form / .yf-warn / modal-backdrop:not(#share-modal)`

**复制 modal**：
- clipboard 失败 fallback modal 带 textarea + 项目主按钮规范的"复制 / 关闭"按钮
- `#share-modal .share-btn` scoped CSS：金色 `var(--accent)` bg + 8px 圆角 + scale(1.04) hover

**i18n**：zh_tw / en 各补 10 个 key（错误文案 + modal 按钮）

**用户跑的 SQL**（已完成 ✅）：
```sql
create table if not exists public.share_snapshots (
  id text primary key, data jsonb not null,
  user_id uuid references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.share_snapshots enable row level security;
create policy "anyone can read share snapshots" on public.share_snapshots for select using (true);
create policy "users can insert own share snapshots" on public.share_snapshots for insert with check (auth.uid() = user_id);
create policy "users can delete own share snapshots" on public.share_snapshots for delete using (auth.uid() = user_id);
```

**迭代历程**（4 轮）：
1. `633722e` 初版：「截图样」hide 大部分元素 + 卡片 pointer-events:none
2. `7f2371b` 修数字不一致：encode 时 filter 掉 closed positions；modal 按钮加 scoped CSS 匹配项目规范
3. `61acc93` 转向"完整页面 + 全局 click → /"：encode morning_brief/suggestions/history/intraday；CSS 放宽
4. `71b5aa5` 最终：用户反馈"too noise"，改成默认全禁 + 仅推荐指数可点 → /

**已知限制**：
- 短链需要登录。未登录用户走 fragment 长 URL
- share 表无自动清理，未来要定期 GC：`delete from share_snapshots where created_at < now() - interval '90 days';`
- 跨域 RLS 公开 read — 任何拿到 key 的人能读到 snapshot（这是分享的设计意图）

---

### 上一轮（2026-05-18 cloud · `claude/fix-app-loading-performance-Kdum4` — app loading perf 并行化 + optimistic render）

**主题**：用户报"app loading 要 5s+，看下 root cause"。

**实测（prod）**：
- HTML gzip 131KB（OK）/ Chart.js + Supabase JS head 同步加载阻塞渲染
- `/api/state` POST 1 持仓 **11.3s 冷 / 8s 热** ⚠️ 主瓶颈

**Root cause**：`compute()` 在 `api/state.py` 里串行调 6-8 个外部 API（详见 commit `f5b3631`）。前端 `refresh()` 启动时 await 这 11s，用户看空白页。

**落地（方案 A · 短期高 ROI）**：

前端 `index.html`:
1. Chart.js + Supabase JS 加 `defer` —— 不阻塞 HTML parse
2. `_bootstrap()` 包到 `DOMContentLoaded`（保证 defer 后 Chart 已就绪）
3. `_optimisticBoot()` —— 从 `localStorage.last_compute_response` 立即 renderAll
4. `refresh()` 成功后缓存 `d`（剥 `history` 控制体积）到 localStorage
5. i18n 加 `正在刷新最新数据…`（zh_tw / en）

后端 `api/state.py`:
6. `fetch_prices` 内部 `ThreadPoolExecutor` 并行 per ticker
7. `compute()` 顶层并行 prices + intraday
8. `compute()` 顶层 prefetch all active position chains 并行
9. `_fetch_position_news` 内部并行 per ticker
10. `_generate_morning_brief` 内部 news + vix 并行
11. `portfolio_history` 内部 `fetch_history` 并行 per ticker

**预期效果**：
- 用户感官：首屏 5s+ → 立即（用 localStorage cache 渲染）
- 真实 API 调用：11s → 估计 3-5s（LLM 仍是大头但只第一次/per-day 必走）
- 后续 refresh 走 LLM cache → < 2s

**追加改动（同 session · 用户报"新登录还是觉得慢"）**：
- 发现登出 → refresh 拉空 positions 会污染 `last_compute_response`，再登录时
  optimistic boot 拿到空 cache，仍要等 4-13s
- Cache key 按用户分桶：`last_compute_response::<userId|guest>`，登出登入不互相覆盖
- `_onSignedIn` 在 `_loadCloudData()` 后、`refresh()` 前再调一次 `_optimisticBoot()`
  —— 用 user-scoped cache 立刻渲染上次登录的 UI（同设备第二次登录起立即可见）
- 第一次登录的新用户 cache miss 时无 fallback（接受首次慢），但二次登录起 ≈ 立即

**未触碰**：方案 B（拆 `/api/state` + `/api/brief` endpoint）和方案 C（SSE streaming）。如果方案 A 部署后用户仍觉慢，下一步走 B 把 morning_brief 单独 endpoint。

**待用户验证**：
- [ ] Mac Chrome / iPhone Safari 刷 `/app` — 首屏应立即（如果有过一次成功拉取）
- [ ] 加新仓 / 切语言后等 ~3-5s 看到 API 真实数据更新
- [ ] Vercel logs 不爆错（`from concurrent.futures import ThreadPoolExecutor` Python 标准库，必有）
- [ ] LLM 早安管家仍正常生成（并行化没动 LLM）

---

### 更早一轮（2026-05-18 cloud · `claude/tsla-put-analysis-ApkJ3` — 管家文案改 priority list · 方案 B）

**主题**：用户报当前管家 LLM 输出是一大段密文（"管家的 ... 一堆**啥意思，你要不要美化一下？给我三个方案"），扫读体验差。

**流程**：
1. 按 CLAUDE.md §9 建预览页 `/styles` 给 3 方案（A 卡片三段 / B 优先级清单 / C 仪表盘）×（桌面+392px iPhone 同屏）
2. 用户选 **B · 优先级清单**
3. 落地到 `renderMorningBrief` + 后端 LLM 改 JSON 输出
4. 清理预览页 + 路由

**改动**（commit `3b31434` 推到 main 触发部署）：

**后端 `api/state.py`**：
- `_generate_concierge_llm` system prompt 改成严格 JSON: `{headline, sub?, items[], footer?}`
- 每个 item: `{priority: urgent|cashflow|root|watch, ticker, title, body, action: rec|position:<pid>|news:<url>|null, cta}`
- 新 `_parse_concierge_json` 宽容剥 markdown code fence + 前置 narrative + 字段缺失，验证 priority enum
- `_template_concierge` 改返回 `(prose, structured_brief)` 元组——从 top_3_focus 派生 items（near_strike/vix_spike/earnings → urgent；profit_opportunity → cashflow；newly_itm/news_alert → root；其他 → watch）
- `_generate_morning_brief` 缓存 `concierge_brief` 到 brief_snapshot，响应多字段 `concierge_brief`
- `CONCIERGE_VERSION` 7 → **8**（强制旧 prose-only cache 失效）
- 三语 i18n 加：`看持仓 / 看推荐 / 看原文`（无尾箭头版）
- 加 `import re`

**前端 `index.html`**：
- 新 CSS `.mb-priority-*` 系列（urgent 红描边 + 4 chip 配色：urgent 红 / cashflow 绿 / root 金 / watch 灰）
- 桌面 ≥900px: priority list 全宽 + calendar 右栏 260px grid
- 手机 ≤600px: 单列堆叠，CTA 全宽
- 新 helper：
  - `_mbBoldify(s)` 安全 `**xx**` → `<strong>`（先 escape HTML 再 unescape markdown，无 XSS）
  - `_mbPriorityIcon` / `_mbPriorityLabel` 优先级 → 🚨💰🩺👀 / 紧急/守住/隐患/观望
  - `_mbRenderPriorityItem(item, idx)` action dispatch（rec/position/news → 对应按钮）
  - `_mbRenderConciergeBrief(brief)` 组装整段 priority list HTML
- `renderMorningBrief(brief)` 双分支：
  - `concierge_brief.items.length > 0` → priority list 模式（`.mode-priority` class）
  - 否则 → 旧 prose hero + focus list（backward compat / template w/o items）
- 三语 i18n 补：紧急/守住/隐患/观望 + 环境

**清理**：删 `styles.html` 预览页 + `vercel.json` 移 builds 和 route

**Smoke test**（部署后 curl 验证）：
- API `morning_brief.concierge_brief.items` 返回 3 条，priority 正确（root news / cashflow profit / urgent danger）
- 前端 bundle 包含新 CSS class + JS helpers (35 处 mb-priority/mode-priority 引用)
- 当次测试 `generated_by=template`（LLM 未走通 — 可能 ANTHROPIC_API_KEY env 不在 test compute 路径，或 LLM transient 失败）
- 真实用户路径带 state，会走 LLM；template fallback 也保证有 ≥1 个 priority item

**待用户验证**：
- [ ] Mac Chrome 看 `/app` 早安管家：应该是 priority list（红/绿/金/灰 chip + CTA 按钮），不再是一大段 prose
- [ ] iPhone Safari：单列堆叠 + CTA 全宽
- [ ] Vercel logs 搜 `[concierge] brief: by=llm items=N` 确认 LLM 真有走通
- [ ] LLM 失败时也能看到 priority list（不会变成旧 prose）
- [ ] 切换 zh/zh_tw/en chip 标签正确翻译

**已知 risk**：
- LLM 可能偶尔返回非 JSON → `_parse_concierge_json` 返回 (None,None) → 走 template fallback。`[concierge] llm_parse_fail` 日志会打文本 head 帮 debug。
- 历史 brief_snapshot 没 `concierge_brief` → version 7→8 bump 强制 miss → 下次刷新走完整路径填上。

### 🐛 部署后 debug 4 轮（同 session）

用户截图反馈"AI 没有 work" — 看到的是 template 兜底（`今日 N 件事要看。`）。诊断 + 修复链：

**Round 1 (`93df263`)**：CSS bug — `mb-priority-headline` 没 grid-area 被 auto-placement 扔到隐式行底部。
- 改 grid-template-areas 成 head/content/side 3 area，wrapper `.mb-priority-content` 承载 headline+sub+list+footer+chips，calendar 独占 side
- 同时 bump client timeout 8s → 14s + max_tokens 1500 → 900 + 缩短 system prompt（猜测 LLM timeout）

**Round 2 (`c764e5b`)**：加 `_llm_diag` debug 字段回响应（用户能看 Vercel logs 但我看不到，得自助诊断）
- 字段含 `{phase, elapsed_s, error_type, error_msg, text_head, items}`

**Round 3 (`4a4a318`)**：发现 root cause — `max_tokens=900` 截断了 JSON
- diag 显示 `phase=parse_fail elapsed=13.42s text_head='```json\n{\n "headline": "..."\n  "items": [\n    ...截断'`
- LLM 也加了 \`\`\`json 包装（虽然 prompt 说别加）
- 修法 3 招：
  - bump max_tokens 900 → 1600 + timeout → 18s
  - assistant prefill `{` 强制 LLM 直接吐 JSON 起始（跳过 narrative / code fence）
  - parser 加 truncated-JSON 修复：找最后一个 top-level `}` 截断 + 补 `]}` 闭合（pytest-like 单测过）

**Round 4 (`e7dcfed`)**：LLM 用瞎拼 position_id (`TSLA_put_415_4d` 用天数替 expiry) → CTA 找不到 DOM
- prompt 加 `[pid=TSLA_put_415_2026-05-22]` 前缀给每个 active position
- system prompt 强调 "pid 必须从行里复制，不准瞎拼"

**最终验证（生产）**：
- `by=llm phase=ok elapsed=8.08s items=4`
- headline: "**TSLA $415P 仅4天到期、距行权1.2%，必须今天决策**；META $540P 已锁利85%..."
- 4 个 items: TSLA urgent / META cashflow / NVDA root / NVDA Call watch
- 全部 position_id 正确 (`TSLA_put_415_2026-05-22` etc.)
- CTA 多样："查看 TSLA Put" / "考虑平仓" / "讨论分散策略"
- 自然 footer: "今日Theta+$154、大盘平稳，但TSLA Put已成定时炸弹..."

**临时 debug 字段 `_llm_diag`** 还留在响应里（位于 `morning_brief._llm_diag`）。**稳定运行 1-2 天后可删**（删 3 处：global `_last_llm_diag` 定义 + `_generate_concierge_llm` 内 set 行 + `return` 字典里的 `_llm_diag` 字段）。

---



### 🆕 这一轮 v2（2026-05-18 cloud · 同分支续）

**主题**：用户问"目前 ai 管家会用我的所有持仓作为输入的一部分吗" → 答否，只 top 3 + 聚合 + 新闻。用户要求"可以是全部持仓吗，然后如果有持仓变化把这个动作也记住并且触发一次重新生成"。

**改动 4 处 `api/state.py`**：

1. **`_make_brief_snapshot`** per-position dict 加 `ticker` + `label` —— 给"removed 持仓"描述用（pid 还在 snap 但持仓不在了，靠 label 描述）
2. **新 `_compute_position_changes(yesterday_snap, positions)`** —— 返回 `{added: [{label}], removed: [{label}], has_changes: bool}`。基于 pid 集合 diff（pid 含 ticker/type/strike/expiry，编辑算 旧 pid 删 + 新 pid 加）
3. **`_generate_concierge_llm`** 签名加 `positions`、`pos_changes`，prompt 加两个 section：
   - `All active positions (N)`: 每张一行 `label · Nd · $pnl (pct%) · Δ · θ · [ITM/ATM tag]` —— LLM 有全局视野
   - `Recent position changes`: `+ 新开: {label}` / `- 平仓/移除: {label}` —— 让管家主动提到刚发生的动作
   - system prompt 加两条规则："列了 changes 自然承认（'你刚加的 NVDA Put...'）" + "active 是给全局判断用，不要逐张列"
4. **`_generate_morning_brief`** 调用 `_compute_position_changes`，cache 命中条件加 `not pos_changes.has_changes`（持仓变了强制重生成）；`CONCIERGE_VERSION` 6→7；brief log 加 `changes=+N/-M`

**预期效果**：
- 管家 prompt 从"3 个聚焦 + 聚合数字"变成"全部持仓清单 + 聚合 + 3 个聚焦 + 变化日志"
- 用户加仓 / 平仓 / 编辑持仓 → 下次 refresh 自动 cache miss → 新管家文本会自然提到这个动作
- token 用量预计：~30 张持仓 ~1000 tokens 多，对 Haiku 4.5 单用户低频不算问题

**待验证**：
- [ ] 部署后管家文本看起来是不是真的"看到"了全部持仓（不再只盯 top 3）
- [ ] 加一张新仓 → 5min 后 refresh，管家文本应自然提到这个新仓
- [ ] 平一张仓 → 5min 后 refresh，管家应该 acknowledge 这个动作
- [ ] Vercel logs 搜 `[concierge] llm_call: active=N changes=` 看 N 和 changes 是不是对的

---

### 上一轮（2026-05-18 cloud · `claude/fix-butler-ai-features-E40Iq` 起步）

**主题**：用户报"管家的 ai 功能失效了" — 早安管家整天显示 `_template_concierge` 兜底文案（"今日 N 件事要看。"），不再调 LLM。

**诊断**（先 curl 后端确认）：
- `debug_env` 显示 `has_anthropic_key: true / anthropic_client_ready: true` ✓
- 直接 `compute` 调用返回 `generated_by: llm` 配 300+ 字 LLM 文本 — **后端 LLM 实际能调通**
- 但 `api/state.py:3111-3145` `_generate_morning_brief` 有 cache poisoning bug：

**Bug**：一旦某次 LLM 失败（冷启动 / 超时 / 网络抖动）→ fallback 到 `_template_concierge` → **结果被无条件写进 `state._meta.brief_snapshot`**（line 3142-3145，旧版）→ 下次同一天读，cache 命中模板文本 → 整天不再重试 LLM。第二天 `date` 不匹配才会重试。

**修复**（3 处改 `_generate_morning_brief`）：
1. cache 命中加 `snap_by != "template"` — template 不算有效 cache
2. 只在 `by != "template"` 时把 concierge_* 字段写进 snapshot — template 失败只留 diff 用的 positions/vix snap
3. `CONCIERGE_VERSION` 5 → 6，一次性失效现存 template-stuck 用户 cache
4. brief log 加 `snap_by` 字段方便排查

**预期效果**：
- 部署后用户刷一次 → CONCIERGE_VERSION 6 vs 5 不匹配 → cache miss → 重试 LLM
- LLM 成功 → 缓存 + 当天复用
- LLM 失败 → template 兜底显示，但 5min 后下次 refresh 再次重试（直到成功）

**待验证**：
- [ ] 用户部署后刷 `/app`，看管家文本是否变回 LLM 风格（"今早不用急——VIX 微升..."）
- [ ] Vercel logs 搜 `[concierge] brief: by=...` 应看到 by=llm 而非 by=template
- [ ] 如果反复看到 `[concierge] llm_error: APITimeoutError` → 可能要看 Vercel 计划是否支持加 maxDuration

---

### 上一轮（2026-05-18 cloud · `claude/clickable-position-cards-mgODq`）

**主题**：用户想把持仓卡片整张做成"点击可选中"，更方便操作；同时不能破坏卡内已有交互。

**改动前**：只有 checkbox + `.pos-name`（左上 ticker / strike / type badge 区）能点击切换选中；卡片其他大片区域（PnL 大字、进度条、出场计划、空白处）点了没反应。

**改动**（`index.html` 单文件，无新 i18n）：

CSS（`.pos` 规则块）：
- `cursor: pointer` — 暗示整张可点
- `transition` 加 `box-shadow` 让选中态切换有动画
- `.pos:not(.unchecked) { box-shadow: 0 0 0 1px rgba(230,184,106,0.55) }` —
  选中态金色 1px 描边（用 box-shadow 不和 `.danger-status`/`.warn-status` 的 border 冲突）
- hover 时 box-shadow alpha 升到 0.72，更明显
- `.pos input:not([type=checkbox]), .pos textarea, .pos select { cursor: auto }` 防御输入框继承 pointer

HTML（`renderPosition` + `renderClosedPos` 两处）：
- 整张 `.pos` 容器加 `onclick="togglePos('${p.id}')"`
- `.pos-name` 删除原本的 onclick（多余，已被整卡接管）
- checkbox 加 `onclick="event.stopPropagation()"`（保留 onchange，避免 click 冒泡 + onchange 双触发反转两次）
- `<details class="pos-payoff">` 加 `onclick="event.stopPropagation()"`（点损益曲线展开不切换选中）
- `pos-actions` 三按钮（平仓/编辑/删除）onclick 前加 `event.stopPropagation();`
- `.close-form` / `.edit-form` 容器加 `onclick="event.stopPropagation()"`（一处兜底，内部 input/按钮都不再误触发）
- closed 卡的「撤销平仓」按钮加 `event.stopPropagation()`

**已确认未受影响**（grep audit 完）：
- ⋯ 菜单（`.pos-more` + `.pos-more-menu`）原本就有 stopPropagation ✓
- 笔记按钮（`.journal-btn`）原本就有 stopPropagation ✓
- ⋯ 菜单内的 copy 按钮 — 在 `.pos-more-menu` 容器内，冒泡被截断 ✓

**遗留 / 待用户验证**：
- [ ] Mac Chrome / iPhone Safari 实测：整卡点击切换选中 OK
- [ ] checkbox 点击只 toggle 一次（没双触发）
- [ ] 点 PnL 大字 / 进度条 / 出场计划文字 → toggle ✓
- [ ] 点平仓/编辑/删除 → 弹对应表单/对话，不切换选中
- [ ] 点损益曲线 summary → 展开/收起，不切换选中
- [ ] 选中态金色描边在亮/暗主题下视觉 OK
- [ ] danger-status / warn-status 卡（红/黄边）+ 选中 (金色 box-shadow) 同时存在时不冲突

---

### 上一轮（2026-05-18 · 云 · `claude/enable-prompt-caching-WDhfs`）

**触发**：用户看 Anthropic console 显示 296.2K tokens/week + $0.55/月 spend，问"管家 API 是不是很贵，要不要开 prompt caching"。

**结论**：**不开 prompt caching**。原因：
1. system prompt 仅 ~488 tokens，远低于 Haiku 4.5 的 **4096 tokens 最小 cacheable prefix**
   —— 加 `cache_control` 不会报错，但 silent 不 cache（`cache_creation_input_tokens: 0`），一分钱省不到
2. 整个 codebase 只有 1 个 LLM 调用（早安管家 `_generate_concierge_llm` @ `api/state.py:3075`）
3. 设计上每用户每天只调 1 次（`brief_snapshot` 缓存在 `state._meta`），TTL 内基本无第二次命中
4. spend 一个月 $0.55，年化 < $7，不值得折腾

**但**：用户提到"我下午才加上这个功能 + 单用户开发"——296K tokens/week 完全不合理。怀疑 cache miss
路径：CONCIERGE_VERSION bump 失效旧 snapshot / 切语言 / cloud 未 ready 时刷新 / 多 tab / 部署后狂刷调试。

**做了什么**（commit 在 `claude/enable-prompt-caching-WDhfs` 分支）：

加 instrumentation 让用户能看真实调用频次：
- `api/state.py:_generate_concierge_llm` 入口 print `[concierge] llm_call: lang=...`
  （client 没初始化时打 `llm_skip: no_client`）
- `api/state.py:_generate_morning_brief` 决定路径后 print `[concierge] brief: by={llm|cached|template} ...
  snap_date={...} snap_lang={...} snap_ver={...} want_ver={...}`
  —— **关键字段对照能直接看出 cache miss 是哪个 key 不匹配**

**待用户验证**：
- [ ] push 后部署，刷 `/app` 几次，去 Vercel logs 搜 `[concierge]` 看真实调用模式
  https://vercel.com/genki3ngs-projects/option-analysis-platform-web/logs
- [ ] 如果 by=llm 比 by=cached 多很多 → 看 snap_* 字段对哪个不匹配 → 决定下一步
- [ ] 如果都正常一天一次 → 296K tokens 可能是历史调试累积，不用动

**下一个 session 如果用户反馈"还是很多调用"**：根据日志的 `snap_*` 字段判断是哪种 miss，针对性修：
- snap_date 总不匹配 → date 比较 bug
- snap_lang 不匹配 → 用户切语言，可以让 cache 跨语言（用同一份英文 LLM 输出动态翻译？或接受）
- snap_ver 不匹配 → CONCIERGE_VERSION 在历史上被 bump 过，新部署后会自愈
- 都匹配但仍 by=llm → 后端 state 没收到 brief_snapshot（cloud 同步问题）

---

### 🚨 静态分析诊断（同 session 后续 · 2026-05-18）

加完日志后继续深入查代码，定位了**首要 bug**（不用看 logs 就能确认）：

**`setInterval(refresh, 30000)` @ `index.html:10825`** — 每 30 秒 unconditional refresh：
- 1 天 2880 次 × 7 天 = 20,160 次 `/api/state` 调用
- 即使 LLM cache 大部分命中，每次后端都跑完整 `_generate_morning_brief`（拉 VIX、算 diff、计算 chips/calendar、拉 news）
- **没有 `document.hidden` 检测** — 浏览器后台、电脑睡眠都还在跑
- 30s 间隔对"包租公"这种"早晚看一眼"的定位太密集
- 这本身也是 Schwab API 用量浪费

**`_saveCloud()` 写云**确实带 state（`index.html:10504` `state: _cloudCache.state`），所以
`state._meta.brief_snapshot` 是会持久化的 — 但 30s interval 创造大量 race 窗口（_saveCloud
debounced 400ms）让 LLM 偶尔被击穿（多 tab 场景更明显）。

**realtime handler 不是凶手**（虽然 explore agent 怀疑过）：
- `index.html:10531` `_cloudCache = { positions, state: row.state }` 完全替换
- 但 `_lastSavedSignature` dedupe（10530）让自己 save 的 echo 不会触发
- 别人 push 的 row 也包含 state（含 brief_snapshot）所以不会真的丢

### ✅ 已修（同 session 接着做）

用户授权直接修，做了 3 处改动：

1. **`index.html:10825`** `setInterval(refresh, 30000)` → `setInterval(refresh, 300000)`
   一天 2880 次 → 288 次，砍 90%
2. **`index.html` `refresh()` 入口**加 `if (document.hidden) return;`
   tab 后台 / 浏览器睡眠时不拉数据，Schwab + LLM 双省
3. **`index.html`** 加 `visibilitychange` listener
   用户切回 tab 立即刷一次，保住"切回就更新"的体验感

**预期效果**：
- Schwab API 调用 → -90%（也帮 refresh_token 7d 续命有缓冲）
- LLM 调用频次 → -90% + race 窗口大幅缩小，cache 几乎全命中
- 如果你 spend 还是高 → 看日志 `[concierge]` 找 race / version bump

**待验证**：用户 prod 刷一刷，看 `/app` 体验是否还流畅（切回 tab 即时更新 OK 吗？5min 不主动切走太"卡"吗？）

如果体验不好，可以再调 interval 到 2-3 分钟（CLAUDE.md 第 8 节授权直接动）。

### 🔍 用户截图发现：当前 brief 是 template fallback，不是 LLM

用户贴了 brief 截图，concierge_text 只显示"今日 3 件事要看。"—— 这是 `_template_concierge`
的兜底输出（`api/state.py:3019`），**不是 LLM 生成**。说明 `_generate_concierge_llm` 这次失败了
（throw exception 被吞）。

但用户 token volume 296K/week 说明 LLM 历史上**调用成功过**——偶发失败，不是配置错。

**做了**：把 `except Exception: return None` 改成 `except Exception as e: print(error); return None`
打出具体异常类型 + 信息（之前吞了），下次失败能在 Vercel logs 看到原因。

**Vercel function timeout**：vercel.json 没设 maxDuration → Hobby 默认 10s，Pro 60s。
当前 Anthropic client `timeout=8.0`（`api/state.py:2592`），Hobby 下已是上限不能再延。

**用户下一步**：刷一下 app → 去 Vercel logs 搜 `[concierge] llm_error` 看具体失败原因：
- `APITimeoutError` → 升 Vercel Pro 或接受偶发兜底
- `AuthenticationError` → ANTHROPIC_API_KEY 失效，rotate
- `RateLimitError` → 限流（不太可能，单用户低频）
- 其他 → 看错误信息

---

### 更早一轮（2026-05-18 cloud · `claude/fix-iphone-text-truncation-R1vGM`）

**主题**：用户报"很多文字折叠了，在 iphone 上不够优雅" + "卡片里的实时价格也没对齐"。

**预览页**：建 `/iphone-text` 3 方案（A 紧致字号 / B Icon 工具栏 / C 工具栏分行）× 桌面+392px iPhone 同屏对照。
用户选 **C 框架 + B 出场 tag**（toolbar 三行分行；副标半中文化；出场建议改 锁利/接货 tag 化 stacked）。

**落地改动**（`index.html` 单文件）：

CSS（仅 `@media (max-width: 600px)` 加 mobile rules，桌面不变）：
- `.pos-toolbar` 移动端 wrap + order：行 1 [add-btn flex:1] + [📥 数据]；行 2 toggles grid 4 列；行 3 排序 dropdown
- 隐藏 `.tb-sep` / `.tb-spacer` / `#sel-count` 在 mobile
- `.lbl-full` / `.lbl-short` 双 span 切换 — 桌面用长（"📐 简洁模式"），mobile 用短（"📐 简洁"）
- `.pos-meta` mobile font-size 11 → 10.5 + ellipsis 防极端长 ticker 折行
- `.pos-stats` mobile 从 flex-wrap 改 `grid 3 列`，5 项 (Δ/IV/θ + Mark/$P) 完美对齐
- `.exit-plan.compact` 重构：HTML 用 ep-prefix + 2 ep-row（tag+body）。桌面横排（ep-row inline + ::before 分隔符 · / tag 隐藏）；mobile column stacked + tag 显示
  - tag "锁利" 用 accent 色；tag "接货"/"卖出" 用 red 色

HTML：
- 给两个 `.tb-group` 加唯一 class：`tb-group-toggles` / `tb-group-sort`
- `<span style="flex:1"></span>` → `<span class="tb-spacer"></span>`
- `renderPosition` 里副标 hardcoded 英文模板改成 `_fillTpl(t('pos_meta_line'), {...})`
- `renderPositionExitPlan` 重构成 ep-prefix + 2 ep-row 结构

JS：
- `updateHideClosedBtn` / `updateDensityBtn` 从 `textContent` 改 `innerHTML`，输出双 span (full + short)

i18n（三语 dict 各补 8 个新 key）：
- `pos_meta_line` 副标模板（zh "Exp {expiry} · {contracts} 张 · 卖价 ${sell_price}/股" / zh_tw 用繁体 / en 保留 contracts/share）
- `锁利` / `接货` / `卖出` — exit plan tag 文案
- `显示已平` / `隐藏已平` / `📐 简洁` / `📐 完整` — toggle button mobile 短版

**遗留**：
- [ ] 用户在 iPhone 实测 — 4 toggle 一行 grid / 副标不再折 / 出场建议 stacked tag 视觉是否符合
- [ ] 用户实测 OK 后可删预览页 `iphone-text.html` + vercel.json 路由（暂保留对照用）
- [ ] 三浏览器矩阵未测

---

### 🆕 local session（上一轮 · 2026-05-17 深夜）

**主题：intro 重组 + README 重写 + 全 sections audit**

- **README.md 全面重写**（commit `fac5e12`）：
  - 算法版本 1.1 → 1.3，加 v1.2 财报衰减、v1.3 自适应、v1.B POP 校准
  - 删「File System Access 文件夹同步」（早替换了），换 Supabase OAuth + RLS
  - 加 8+ 新功能盘点（加仓预览/对比/Wheel hint/POP+Exit/早安管家/简洁双密度/数据源 pill）

- **intro 重组 — 用户选 B+C 综合**（commit `f1cbdb7`）：
  - 走 CLAUDE.md 第 9 节预览页流程：先建 `intro-preview.html` 给 3 方案
    A 时间轴 / B Feature Grid / C 工作流 7 步 → 用户选 B+C 综合
  - Hero 下立刻插「⭐ 能干啥 Feature Grid」（2×4，7 个 NEW tag）
  - 「三步当上包租公」扩成「完整工作流 7 步」（最后一步 span-2）
  - 「配套能力」从 8 项扩到 12 项
  - 算法 section：1.1 → 1.3，DTE/Δ adaptive + 财报 5 档衰减 + 12 月回测
  - 三语 i18n 三套补 ~50 个新 key
  - 删 intro-preview.html + vercel.json 路由清理（接受 cloud 的简化 vercel.json）

---

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
