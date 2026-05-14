# Option Analysis Platform — Project Notes for Claude

A web app for monitoring short option positions, recommending new contracts,
and educating about options terminology.

**Production URL:** https://option-analysis-platform.vercel.app
**GitHub:** https://github.com/genki3ng/option-analysis-platform
**Local Mac app twin:** `~/tsla_monitor/` (different architecture, shared data via Drive)

## Stack

- **Frontend:** Single `index.html` — vanilla JS, no build step, Chart.js via CDN
- **Backend:** One Python serverless function `api/state.py` on Vercel
- **Data:** Browser `localStorage` (no server DB)
- **Market data:** yfinance (live chains + Greeks) + Massive API (historical price bands)
- **Cross-device sync:** File System Access API → Google Drive folder

## Architecture key decisions

### No server-side persistence
All user data (positions, state, username, prefs) lives in browser localStorage.
The Vercel function is stateless — every `/api/state` POST sends positions and
gets back computed Greeks/P&L/suggestions.

### Why two sync modes
1. `🔗 文件同步` (single JSON file) — web-only users, simple
2. `📁 文件夹同步` (directory with positions.json + state.json + username.txt)
   — shares format with local Mac app `monitor.py`

### Sort-by-tier-first for recommendations
Verdict tier (⭐⭐⭐⭐⭐ to ⭐) is computed BEFORE sorting. Sort uses
`(tier desc, score desc)` tuple so top tier always wins. Earlier bug: score-only
sort put ⭐⭐⭐⭐⭐ at #9.

## Deployment

```bash
# Direct API deploy (token in VC_TOKEN env)
cd ~/option-analysis-platform-web
python3 <<EOF
import json, base64
FILES = ['vercel.json', 'requirements.txt', 'index.html', 'README.md', 'api/state.py']
payload = {
    "name": "option-analysis-platform",
    "project": "prj_E3ldwqv44qgM4ruStQE4QzlX7slv",
    "target": "production",
    "files": [{"file": f, "data": base64.b64encode(open(f,'rb').read()).decode(),
               "encoding": "base64"} for f in FILES]
}
json.dump(payload, open('/tmp/payload.json', 'w'))
EOF
curl -X POST "https://api.vercel.com/v13/deployments" \
  -H "Authorization: Bearer $VC_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/payload.json
```

`vercel.json` uses legacy v2 `builds` + `routes` format because the auto-detection
broke with newer Vercel runtime:

```json
{
  "version": 2,
  "builds": [
    { "src": "api/state.py", "use": "@vercel/python" },
    { "src": "index.html", "use": "@vercel/static" }
  ],
  "routes": [
    { "src": "/api/state", "dest": "/api/state.py" },
    { "src": "/", "dest": "/index.html" },
    { "src": "/(.+)", "dest": "/$1" }
  ]
}
```

## Important files

| Path | Purpose |
|------|---------|
| `index.html` | Entire SPA (HTML + CSS + JS, ~3500 lines) |
| `api/state.py` | Vercel function: compute state + option recommender |
| `vercel.json` | Build config (explicit v2 format required) |
| `requirements.txt` | Just `yfinance` |
| `README.md` | User-facing docs |

## Data formats

### `positions.json` (array of open positions, shared with local Mac app)
```json
[
  {
    "ticker": "TSLA",
    "type": "call",
    "strike": 600.0,
    "expiry": "2027-01-15",
    "contracts": 10,
    "sell_price": 18.05,
    "trade_date": "2026-05-01"
  }
]
```

### `state.json` (closed position state, shared with local Mac app)
```json
{
  "TSLA_call_420_2026-05-08": {
    "closed": true,
    "close_date": "2026-05-08",
    "close_price": 5.446,
    "close_reason": "manual"
  }
}
```

### Position ID format (must match between frontend JS and backend Python)
`${ticker}_${type}_${int(strike)}_${expiry}`

Examples: `TSLA_call_600_2027-01-15`, `META_put_630_2026-05-29`

## API endpoint: `/api/state`

### POST body
```json
{
  "action": "compute" | "recommend",
  "positions": [...],   // from localStorage
  "state": {...},       // from localStorage
  "ticker": "TSLA",     // recommend only
  "direction": "bullish" | "bearish" | "neutral",
  "intent": "premium" | "csp" | "covered_call" | "long_vol" | "long_leaps",
  "timeframe": 7,       // target days to expiry
  "risk": "conservative" | "balanced" | "aggressive"
}
```

### Response (compute)
- `tickers`, `intraday` — per-ticker quotes + 5-min sparkline data
- `positions` — enriched with Greeks, P&L, mark_src, etc.
- `suggestions` — portfolio + per-position advice cards
- `history` — daily P&L timeseries
- `yfinance_available` — bool, frontend shows warning if false

### Response (recommend)
- `candidates` — top 15 with Greeks + verdict + price_band
- `iv_rank` — current IV percentile vs 30d realized vol
- `criteria` — echo of request + decided strategy + delta band

## Known gotchas (learned the hard way)

### Python `\n` in triple-quoted HTML strings
Inside `HTML = """..."""`, `\n` becomes a literal newline character. This
breaks JS single-quoted strings. Use `String.fromCharCode(10)` or `\\n`.

This bit us twice — once in CSV export (NL constant), once in suggestion details.

### JS string escape inside HTML attribute templates
```js
// BAD: confuses JS parser
onclick="deletePos('${id}', '${label.replace(/'/g, '\\'')}')"
// GOOD: avoid passing complex strings through attributes
onclick="deletePos('${id}')"
// Look up label from cached data in JS
```

### Vercel "functions" config can reject `api/state.py`
Newer Vercel builder may error: `pattern ... doesn't match any Serverless Functions`.
Fix: use `builds` + `routes` (legacy v2 format).

### Empty POSITIONS list breaks `min()`
`portfolio_history` and `get_underlying_at` both use `min(p.trade_date for p in POSITIONS)`.
Guard with `if not POSITIONS: return []`.

### Drive sync overwriting wrong direction
When user picks a Drive folder via "📁 文件夹同步", the confirm dialog asks:
- OK = use folder data (overwrite localStorage)
- Cancel = use localStorage (overwrite folder)

Be EXTRA careful with wording — wrong choice once nuked positions.json in Drive.
We added warning that "single loss" doesn't fit the "average" word.

### i18n semantic key fallback
HTML uses `data-i18n="info_b1"` (semantic key) but t() needs to find the
Chinese version when lang=zh. Solution: `I18N.zh` dict for semantic keys.
Without it, the default mode shows literal `info_b1`.

## Domain knowledge baked in

### Black-Scholes pricing & Greeks (in `api/state.py`)
- `bs_call(S, K, T, r, sigma)` returns `(price, delta, theta_per_day, vega_per_1pct_iv)`
- `bs_put(...)` — same signature
- `implied_vol(target, S, K, T, r, is_call)` — bisection inversion

### Verdict scoring weights (used for tier 1-5)
Severe cons weighted more than pros:
- Distance to strike < 2%: -3 (gamma extreme)
- Yield ≥ 100%: +3
- Safety prob ≥ 85%: +2
- IV rank ≥ 70 (selling): +2
- IV rank ≤ 20 (selling): -2
- LEAPS leverage ≥ 3x: +3

Tiers: weight ≥ +5 / +2 / -1 / -4 / less → 5/4/3/2/1 stars

### Massive API (Polygon clone) usage
Base: `https://api.massive.com`. Free tier:
- ✅ `/v2/aggs/ticker/TSLA/range/1/day/...` — stock daily OHLC
- ✅ `/v3/reference/options/contracts?underlying_ticker=...` — contract listing
- ✅ `/v2/aggs/ticker/O:TSLA260515P00400000/range/1/day/...` — option daily
- ❌ `/v3/snapshot/options/...` — real-time chain (paid)
- ❌ `/v2/last/nbbo/...` — real-time NBBO (paid)

API key is hardcoded in `api/state.py` (`MASSIVE_KEY`). For each top recommendation,
we fetch its 30-day daily OHLC to build a "price band" signal.

### yfinance for live chain data
`yfinance.Ticker(ticker).option_chain(expiry).calls / .puts` returns DataFrame
with bid/ask/lastPrice/impliedVolatility/etc. Free, no key, but unofficial — Yahoo
may rate-limit if hit too aggressively.

## File System Access API for cross-device sync

Only works on Chromium browsers (Chrome / Edge / Brave). Uses `showOpenFilePicker`
or `showDirectoryPicker`. Handle persisted in IndexedDB (`oap-sync` DB, `kv` store).

On page load, `_initSync()` checks IDB and tries to restore connection.
`queryPermission({mode:'readwrite'})` returns 'granted' if user previously gave
persistent permission — otherwise needs user gesture to re-grant.

## i18n system

Dictionary-based, 3 langs: `zh` (default), `zh_tw`, `en`. Keys can be either:
- Chinese strings (e.g. `'收到权利金'`) — original text doubles as key
- Semantic keys (e.g. `'info_b1'`) — must be defined in I18N.zh too

Markup: `data-i18n` (textContent), `data-i18n-html` (innerHTML),
`data-i18n-title` (tooltip), `data-i18n-placeholder` (input placeholder).

JS templates: use `t('key')` helper.

Dynamic backend strings (suggestions, verdicts) still 简中 only — future work
needs Python-side i18n or send language code to API.

## Education content

25 topics in `EDU_TOPICS` array, grouped into 6 categories. ITM/OTM/ATM put
FIRST because they're the most foundational. Each topic has `cat`, `sym`, `name`,
`desc`, `ex`, `care`. EN translations for titles + descriptions in I18N dict.

## Local Mac app twin (`~/tsla_monitor/`)

Original local-first version. Uses tkinter→Tk 8.5 first (broken on macOS),
then pivoted to a local HTTP server + browser UI.

Shares data with web app via:
- `~/tsla_monitor/positions.json` → symlink → Drive folder positions.json
- `~/tsla_monitor/state.json` → symlink → Drive state.json

Local app reads/writes Drive directly. Web app uses File System Access API
to also read/write the same Drive folder. **Don't run both simultaneously**
or they race.

Drive path:
```
~/Library/CloudStorage/GoogleDrive-congyang@meta.com/My Drive/
  claude/01_projects/28_personal_project/Options Short Monitor/
```

Local app can also be packaged as `OptionAnalysisPlatform.app` via `build_app.sh`.
For colleagues without Python: provides AppleScript launcher with `pip install yfinance`
fallback paths (system Python, Homebrew, etc.) and avoids Meta's fbcode Python
(broken pip).

## Future ideas (not implemented)

- Push notifications when positions hit alerts (need user opt-in + backend)
- AI commentary on positions/recommendations via Anthropic API
- X (Twitter) follow-along — scrape `@joely7758521` / `@Rustallintsla` trades
  (needs paid X API or Apify)
- Iron Condor / Vertical Spread builder UI
- Replace IV rank approximation with real historical IV (would need to fetch
  N strikes × 30 days = lots of API calls, requires paid Massive tier)
- Polygon-style WebSocket for tick-level updates
- Backtest mode: replay a strategy against historical data

## Commit conventions

Short imperative commit messages. Examples from history:
- `Add option recommendation engine`
- `Fix rec sort: tier-based primary sort, weighted verdict scoring`
- `Semantic timeframe buttons + Massive 30d price band integration`

Author: `Cong <cong@local>` (set via `git -c user.email=... -c user.name=...`).

## When debugging

1. **JS syntax**: `/usr/bin/osascript -l JavaScript /tmp/check.js` — quickly catches
   parser errors before deploying.
2. **API errors**: Check Vercel deployment "Functions" logs for Python tracebacks.
3. **Empty page**: Almost always a JS syntax error. Check Console.
4. **Wrong data on Drive**: Check Drive folder contents directly — symlinks
   sometimes get truncated by other Claude sessions / sync conflicts.
5. **Vercel timeout**: Hobby plan defaults to 10s. `maxDuration: 60` allowed.
   yfinance + Massive both have cold-start latency.

## Quick test script

Local test server (mocks Vercel routes):
```python
# /tmp/test_server.py
import sys, os, json
sys.path.insert(0, '/Users/congyang/option-analysis-platform-web')
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from api.state import compute, recommend, _check_yf

class H(SimpleHTTPRequestHandler):
    def do_POST(self):
        if urlparse(self.path).path == '/api/state':
            length = int(self.headers.get('Content-Length', 0))
            payload = json.loads(self.rfile.read(length).decode()) if length else {}
            action = payload.get('action', 'compute')
            result = recommend(payload) if action == 'recommend' else compute(payload)
            body = json.dumps(result, default=str).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

os.chdir('/Users/congyang/option-analysis-platform-web')
HTTPServer(('127.0.0.1', 8766), H).serve_forever()
```

Run: `python3 /tmp/test_server.py` then visit http://localhost:8766
