# HANDOFF.md — 最近上下文

> 本文件每次有较大改动后会更新。读完它你就接住了。
> **新 session 第一句话**：先读 `CLAUDE.md` 再读本文件，然后简单复述你看到了什么。

最后更新：2026-05-19（cloud — usage tracking + /admin 面板上线）

### ✅ 这一轮 feature（2026-05-19 cloud · usage 埋点 + /admin 后台）

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

### ✅ 上一轮 hotfix #2（2026-05-19 cloud · `index.html:9072` `applyGoal`）

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

**`ALGORITHM_VERSION`**：1.2 → **2.0**

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
