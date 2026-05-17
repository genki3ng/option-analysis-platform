# HANDOFF.md — 最近上下文

> 本文件每次有较大改动后会更新。读完它你就接住了。
> **新 session 第一句话**：先读 `CLAUDE.md` 再读本文件，然后简单复述你看到了什么。

最后更新：2026-05-17

---

## 1. 最近 12 个 commit（按新到旧）

```
9ff7d00 docs: 授权 — 部署/合并 main 不再单独问
69d26f9 docs: HANDOFF 更新 — 算法 1.2 + Massive 移除 + 数据源 pill
f773187 feat: 推荐列表顶部加数据源降级 pill
0fc47de remove: Massive API（30 天历史价位带特性弃用）+ Schwab 错误日志
8103520 algo 1.2: 财报因子改成距财报天数衰减（替代 1.1 的 cross 二元否决）
88643f3 security: 加强 .gitignore + HANDOFF.md 补 public repo 注意事项
3a47516 docs: 加 CLAUDE.md + HANDOFF.md
ca2d251 fix: 持仓选择 (selectedIds) 在手机刷新后被清空
a973cbb fix: sweep stale supabase auth keys on init (prevent PKCE drift)
a4bf629 debug: visible auth diagnostic for mobile sign-in failures
51a4a96 fix: don't strip ?code= from URL on load (Supabase PKCE needs it async)
2c97f32 feat: Safari PKCE + Vercel Analytics + intro privacy section + contact email
a9734d1 refactor: remove File System Access sync (replaced by Supabase cloud)
23c70c6 fix: migration prompt uses in-page modal (was silently blocked after OAuth)
4354462 feat: Supabase Auth (Google sign-in) + realtime cloud sync
84ec1dd fix: compare-pill z-index above rec-form modal
e4ca47e Trigger: force Vercel build (GitHub integration test)
a4432f4 Add: 加仓预览 + 候选对比 + 手机 UX 优化 + 包租公分提示
db30630 Deploy: bump trigger (stability test)
```

## 2. 本 session（cloud / 2026-05-17）做了什么

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

## 2bis. 上一个 session 主要做了什么

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
- 简洁模式 toggle
- Iron Condor / Spread builder
- 真实历史 IV 接入（用 Massive）
- 跨 ticker 相关性分析
- 大佬交易信号（X subscriber post）接入
- 把"⭐过滤 / 语言 / 主题 / 表单上次的值"也同步到云端（目前只在 localStorage）

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
