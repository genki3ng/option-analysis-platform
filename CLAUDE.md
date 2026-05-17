# CLAUDE.md — 项目说明（给 Claude 的长期记忆）

> 任何 Claude session（local Claude Code、Web、Mobile）进来第一件事：
> **先读这个文件 + `HANDOFF.md`，然后跟用户简单复述你看到了什么再开始动手。**

---

## ⚠️ Session 必读：开场 + 收尾 3 条铁律

用户用 claude.ai 习惯了"一个对话窗口持续聊"，但 Claude Code Web 是 task-isolated session。
为了让协作不掉链子，**任何 session 严格执行下面 3 条**：

### 1. 开场必报模型

读完 CLAUDE.md + HANDOFF.md 之后、做任何事之前，**告诉用户你正在哪个模型上跑**。
用户的期望默认：**Claude Opus 4.7 1M Max**。

- 如果你跑的是 Opus 4.7 1M Max → 一句话告知即可："✅ 我在 Opus 4.7 1M Max 上，准备好了"
- 如果**不是** → 暂停一切，告诉用户："⚠️ 我现在跑的是 X（不是 Opus 4.7 1M Max），你是要换还是接着用？"
  - 模型不能由 agent 自己切（初始化时定的），但用户能开新 session 时挑

### 2. 任务过程中"独立检查"

如果用户问"另一边 session 做了什么"或"你看到刚才的更新吗"：
- **绝不能**说"我记得"或"刚才"。每个 session 是空记忆，没有"刚才"。
- 主动跑 `git pull origin main && git log --oneline -10 && cat HANDOFF.md` 看实际状态
- 然后复述"我看到 main 上最新是 commit X，HANDOFF.md 里写了 Y，对吗？"

### 3. 收尾必更新 HANDOFF.md

在你**说完"任务做完了"或类似总结之前**，必须：
1. 简要更新 `HANDOFF.md`（"最后更新"日期 + 本 session 干了啥 + 留下的状态）
2. `git commit + push`（如果 HANDOFF.md 有改动）
3. 然后才能宣告完成

**理由**：Claude Code Web 的 session 完成后会被归档，且**用户不会被通知**。
下一个 session 进来只能靠 HANDOFF.md 接住上下文。你不写，就把下一个 session 坑了。

如果你不确定要不要算"完成了"，也至少写一笔进度。**宁愿多写，不要漏写**。

---

## 0. 用户 & 一句话

用户 **congyang**（hi@congyangwang.com）。中英文都行，但默认中文回复，专业领域术语保留英文。
不要堆 emoji 装饰，关键节点用一两个是 OK 的。文字简洁、可扫读。

> **「包租公 · Landlord」** — 一个让散户用 Covered Call / CSP / Wheel 策略"出租"美股的可视化工具 + 推荐引擎。

线上：https://trade.congyangwang.com  ·  GitHub：https://github.com/genki3ng/baozugong

---

## 1. 技术栈

| 层 | 用什么 |
|---|---|
| 前端 | 纯 HTML + 内联 CSS/JS（不打包、不构建）`index.html` / `intro.html` / `marks.html` |
| 后端 | Vercel Serverless Python（`api/state.py`，单文件，无框架） |
| 行情 | Schwab Market Data API（主路径）→ Yahoo via curl_cffi → yfinance（兜底） |
| 用户 / 同步 | Supabase（Google OAuth + Postgres + Realtime） |
| 部署 | Vercel（GitHub auto-deploy on `main`） |
| 域名 | trade.congyangwang.com（Cloudflare-managed DNS） |

**没有构建系统**。改 HTML/Python 直接 `git push`，Vercel 1 分钟内 deploy。

---

## 2. 关键 URL & ID

| 用途 | 地址 |
|---|---|
| 生产 | https://trade.congyangwang.com/app |
| 介绍页 | https://trade.congyangwang.com/ |
| GitHub | https://github.com/genki3ng/baozugong |
| Vercel project | option-analysis-platform-web (`prj_pKnwgi29hkTUshTImCnxM9TOmSIl`) |
| Supabase project | `nvavwcvxmzksadpbtafs.supabase.co` |
| Vercel Analytics | https://vercel.com/genki3ngs-projects/option-analysis-platform-web/analytics |

⚠️ **不要把域名搬回旧项目** `option-analysis-platform`（id: `prj_E3ldwqv44qgM4ruStQE4QzlX7slv`）。它是早期的废弃项目，本来 trade.congyangwang.com 错绑在它上面，已经搬到 `-web` 后缀的新项目。旧项目最好让用户删掉。

---

## 3. 文件树

```
.
├── index.html      ← 主 app（~8000 行，包含 CSS / JS / i18n / Supabase 接入）
├── intro.html      ← 落地页（介绍 + 算法 + 隐私）
├── marks.html      ← 内部 brand mark 候选页
├── api/
│   └── state.py    ← 唯一后端文件（~2300 行）
├── scripts/
│   └── schwab_auth.py  ← 一次性脚本，refresh_token 过期时本地跑生成新 token
├── requirements.txt
├── vercel.json     ← 路由：/ → intro, /app → index, /marks → marks
├── README.md
├── CLAUDE.md       ← 本文件
└── HANDOFF.md      ← 短期上下文 / 进行中 / 已知问题
```

---

## 4. 必须了解的架构决定

### 4.1 Schwab 凭证（环境变量）

`api/state.py` 需要 3 个 env vars：
- `SCHWAB_CLIENT_ID`
- `SCHWAB_CLIENT_SECRET`
- `SCHWAB_REFRESH_TOKEN`（**有效期 7 天**，过期了用 `scripts/schwab_auth.py` 本地重生成）

Vercel 项目级 env vars 已经设了（通过 Vercel API），但**这个项目的 `@vercel/python` legacy builder 在 propagation 上有时不稳定**。

**症状**：`debug_env` 显示 `schwab_env_keys: []`，推荐返回 `"missing SCHWAB_CLIENT_ID env"`。

**根治方法**：用 Vercel REST API 做 deployment 时把 env vars **inline** 在 payload 的 `env` 和 `build.env` 字段里。但现在 GitHub auto-deploy 不能 inline，只能赌项目级 propagation 这次工作。**如果坏了**，需要 Vercel token + 用 API 手动部署一次（前历史里有详细方案）。

### 4.2 数据流（重要）

```
用户改持仓
  ↓
savePositions(arr) — 在 index.html
  ├─ 已登录: 写 _cloudCache.positions → debounced 350ms upsert 到 Supabase user_data
  └─ 总是: 写 localStorage（作为离线降级备份）
  
读持仓
  ↓
loadPositions()
  ├─ share view: 用 _sharedSnapshot
  ├─ 已登录 & cloud ready: 用 _cloudCache.positions
  └─ 否则: 用 localStorage
```

**Supabase 表 schema**（只有一张表）：
```sql
public.user_data (
  user_id uuid primary key references auth.users(id),
  positions jsonb default '[]',
  state jsonb default '{}',
  updated_at timestamptz default now()
)
-- RLS: 只有 auth.uid() = user_id 才能 select/insert/update
-- Realtime: publication supabase_realtime 已添加 user_data
```

**state 的内部约定**：键大部分是 `position_id`（如 `TSLA_put_400_2026-05-22`），但有一个**保留 namespace** `_meta`：
- `state._meta.selection`: 用户勾选要纳入图表/建议的持仓 ID 列表

后端 `api/state.py` 只用 `state.get(pid, {})` 读单个持仓状态，不会迭代所有 key，所以 `_meta` 不会冲突。

### 4.3 i18n（中文做 key）

约定：**永远以简体中文字符串作为 key**。
- HTML：`<span data-i18n="包租公">包租公</span>` 或 `data-i18n-html="..."`（含 HTML）
- JS 模板字面量：`${t('包租公')}`
- 服务端：`_T(lang, '包租公')` 或 `_T(lang, '{n} 个空头持仓', n=5)`（支持 `{var}` 插值）

三个语言 dict：
- `index.html` 里有 zh / zh_tw / en 三套大对象
- `api/state.py` 里有 `TRANS_TW` / `TRANS_EN`（约 80 个 key，凡是服务端生成的中文字符串都在里面）

**加新文案时**：三套都要补，否则 EN/繁中 模式会显示原始中文 key。

### 4.4 包租公算法

**核心概念**：用户是"包租公"，把股票"出租"出去收"租金"（权利金）。

**包租公分（rent_score）**：算法 1.1，8 个因子：
- 年化租金 · 安全度（BS）· DTE 甜蜜区（7-21d）· Delta 甜蜜区（0.15-0.30）
- IV rank · 流动性（spread × OI × volume 复合）· 回测胜率 · 财报跨期

仅对 **short premium 策略**有分（CSP / Covered Call / 默认 short premium）。
**买入期权**（LEAPS / 做多波动率）不算包租公分，前端会渲染"本分仅适用于卖出场景"提示。

### 4.5 部署节奏

`git push origin main` → Vercel 触发 build（30s-1min）→ 部署完成。

验证脚本：
```bash
curl -s "https://trade.congyangwang.com/app?_=$(date +%s)" | grep -c "<你的新字符串>"
```

如果 0，等 30 秒再试；如果一直 0，去 Vercel deployments 页看 build 是否失败。

---

## 5. 这些坑踩过别再踩

1. **trade.congyangwang.com 绑在错的项目**：历史上绑过 `option-analysis-platform`（旧），现在是 `option-analysis-platform-web`（新）。任何"修改部署但前台看不到"的问题，第一步先确认域名绑在哪个项目。

2. **Vercel env vars 不稳定**：legacy `@vercel/python` builder 偶尔不传 env 到 runtime。`debug_env` 是诊断工具：`POST /api/state {"action":"debug_env"}`。

3. **Supabase storageKey 不要乱改**：改了之后旧 localStorage 残留的 `sb-<old-key>-code-verifier` 会让 PKCE token 交换沉默失败。`_initSupabase` 里已经有自动清理，但**改 storageKey 必须先清理本地遗留**。

4. **`confirm()` 在 OAuth 回调后可能被浏览器拦截**：iOS Safari 尤其严。需要用户确认的弹框统一用页面内 modal（参考 `.migrate-modal`）。

5. **不要在 `window.load` 里清 URL 的 `?code=`**：Supabase PKCE 需要异步用这个 code 换 token。手动清会导致 token 交换失败（iOS Safari 上 100% 触发）。

6. **`selectedIds` 在 race 中被清空**：未登录时 `loadPositions` 返回空，后端返回空 `d.positions`，selectedIds 被 filter 清空。`_onSignedIn` 末尾必须 `selectedIds = null` 让下次 refresh 重新初始化。

7. **后端 / 前端 position id 必须严格一致**：`{ticker}_{type}_{strike int}_{expiry}`。前端用 `parseInt(strike)`，后端有对应的 `position_id()` 函数。改了一边必须改另一边。

8. **i18n 的 inner template literal 变量名陷阱**：`renderXxx` 函数里 `t()` 是 i18n 函数；如果你写 `arr.map(t => ...)`，参数 `t` 会 shadow 外面的 `t()` → 国际化失效。用 `tr` 或别的名字。

9. **删除 File System Access sync 的清理**：以前有一套用 IndexedDB + 本地文件夹的同步系统，commit `a9734d1` 删完了。新增功能时不要再调用已删除的 `syncOut()` / `syncIn()`。

10. **Schwab Order Limit 别设 0**：用户曾经把 Schwab Developer Portal 里的 Order Limit 调到 0，整个 API（包括 market data，虽然 Order Limit 名义上只管 trading）一起死。值至少 1，推荐 120。

---

## 6. 主要功能盘点

- ✅ 持仓监控（实时定价 + Greeks + P&L）
- ✅ 包租公推荐指数（算法 1.1，6 个 intent × 3 个 risk × bullish/bearish/neutral）
- ✅ 卖出策略 / LEAPS 两套不同的评分逻辑
- ✅ 早安简报（每日 9:30 ET 后自动生成）
- ✅ 复盘报告 modal
- ✅ 持仓笔记 / Trade journal
- ✅ Tier filter（⭐⭐⭐⭐+ 过滤）+ 重跑上次 pill
- ✅ 加仓预览 modal（集中度 / Greeks / 保证金 / 收益四维）
- ✅ 候选对比 modal（2-5 个候选横向 12 指标对比，绿/红高亮最优最差）
- ✅ 移动端 UX（bottom-sheet modal / 卡片防溢出 / header 压缩）
- ✅ 三语 i18n（简中 / 繁中 / English）
- ✅ Google 登录 + Supabase 实时云同步
- ✅ 本地 localStorage 降级（未登录可用）
- ✅ 首次登录迁移向导（页面内 modal，不会被浏览器拦截）
- ✅ 💾 导出 JSON 备份
- ✅ 期权小白指南（24 个术语，4 字段 × 三语）
- ✅ Vercel Analytics + Speed Insights（已埋 script，需 Dashboard 开启）

---

## 7. 写代码前的检查清单

- [ ] 改 HTML 文案 → 三语 dict（zh/zh_tw/en）都补
- [ ] 改后端文案 → `TRANS_TW` 和 `TRANS_EN` 都补
- [ ] 改 position 字段 → 前后端 `position_id` 一致
- [ ] 加新 i18n key 时不与 JS 模板里的 `t` 参数名冲突
- [ ] 新 feature 影响 Cloud schema → 用 `state._meta.*` 保留 namespace，不要改 `user_data` 表结构（除非必要）
- [ ] 数据相关操作要考虑两种用户：登录（用 `_cloudCache`）/ 未登录（用 localStorage）
- [ ] 写完 `git add -A && git commit -m "..." && git push origin main`，然后 curl 验证

---

## 8. 与用户协作的几个偏好

- 用户喜欢**直接的语言**，少 happy talk。我有 bug 就承认 bug，不绕。
- **不要主动做 over-engineering**。功能要小、独立、可逐个测。
- **每次有不确定的实现选择**用 AskUserQuestion 给 2-3 个选项，不要默认替他决定大方向。
- 部署前**说一遍我即将做什么**，避免做反了再回滚。
- 用户**会贴 token / 凭证给我跑命令**，跑完**主动提醒 rotate**。永远不要把这些放进 commit。
- **部署 / 合并到 main 不再单独问**（用户 2026-05-17 授权 "以后都你来"）：
  feature 分支做完 → 自检 → fast-forward 或直接合到 main → push origin main →
  vercel 自动 build → 简单 curl 验证（沙盒能 curl 的话）→ 报结果。
  仍然适用的守则：commit message 写清楚；改完同步 HANDOFF.md；
  涉及破坏性操作（force push / 删分支 / 删表）还是要单独问。

---

## 9. 🎨 设计类任务的强制工作流

**任何涉及视觉 / UI / 布局 / 配色 / 控件样式 / 文案展示形式**的任务，
**不要直接改 `index.html` / `intro.html`**。先做"在线预览页"让用户选。

### 流程

1. **建一个临时预览页面**（HTML 文件 + vercel.json 路由）
   - 命名约定：`<feature>.html` 放项目根，路由 `/<feature>` → 该文件
   - 例子：`buttons.html` → `/buttons`，`cards.html` → `/cards`，`palette.html` → `/palette`
2. **页面里同屏展示 2-4 个候选方案**（A / B / C / D）
   - 每个方案带 1 句话说明（设计取舍 / 灵感来源）
   - **必须同时展示桌面 + 手机两种视口**（手机宽度可用 `width: 375px` 模拟，或在桌面上加 frame）
3. **告诉用户预览地址** `https://trade.congyangwang.com/<feature>`
4. **用 AskUserQuestion 让他选**（A / B / C / D / 都不行）
5. 选完 → 把该方案套用到正式页面 (`index.html` / `intro.html`)
6. **删掉预览页** + 从 vercel.json 移除路由 + commit

### vercel.json 加路由的位置

`/(.*)` 这条是 catch-all，**新路由必须加在它前面**：

```json
"routes": [
  { "src": "/api/state", "dest": "/api/state.py" },
  { "src": "/app/?", "dest": "/index.html" },
  { "src": "/marks/?", "dest": "/marks.html" },
  { "src": "/<feature>/?", "dest": "/<feature>.html" },   ← 加这里
  { "src": "/(.*)", "dest": "/intro.html" }
]
```

builds 数组也要加 `{ "src": "<feature>.html", "use": "@vercel/static" }`。

### 预览页模板要点

- 复用项目调色板（CSS 变量 `--bg / --card / --text / --accent` 等）
- 候选用大标题分割：`<h2>A · 简洁线框</h2>`，下面是真实可点的渲染
- **同屏桌面 + 手机对照**：
  ```html
  <div style="display:grid;grid-template-columns:1fr 375px;gap:24px">
    <div class="desktop-frame">...桌面渲染...</div>
    <div class="mobile-frame">...手机渲染（375px 宽）...</div>
  </div>
  ```
- 用户可以直接在浏览器开 dev tools 切换设备模式看，但**预览页里直接对比更省事**

### 反例（不要这样做）

❌ 直接在 `index.html` 改完 push，告诉用户"你看看好不好"  
❌ 只写文字描述"我想做成 A 这样：xxx，B 这样：yyy"  
❌ 只展示桌面或只展示手机  
❌ 让用户自己开 chrome devtools 切设备模式
