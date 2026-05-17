# HANDOFF.md — 最近上下文

> 本文件每次有较大改动后会更新。读完它你就接住了。
> **新 session 第一句话**：先读 `CLAUDE.md` 再读本文件，然后简单复述你看到了什么。

最后更新：2026-05-17（batch 4 子批 A 完成）

### 📦 Batch 4 进行中（推荐引擎进阶 backlog）

Batch 4 是用户 priority table 的最后一波，分 3 个子批做：
- **子批 A ✅ 已上线**（`d09ab02`）：long_vol 下架 + Vol skew 信号 + Wheel 闭环提示
- **子批 B 待做**：历史 POP 校准 + Exit plan 模板（~2 天）
- **子批 C 待做**：表单双轨模式（目标 vs 策略，UX 大改，~1 天）

子批 A 验证清单：
- [ ] /app 推荐结果里出现 Vol skew pill（put_skew/call_skew，中间值不显示）
- [ ] 持仓列表上方出现 Wheel 闭环提示（用户必须账户中设过 ≥100 股，或最近 30d 有 CSP expired_itm）
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
