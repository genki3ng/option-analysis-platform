# Option Analysis Platform — Web

A browser-based dashboard for monitoring short option positions.
Data lives in your browser's localStorage — fully private, no server-side storage.

## Stack
- **Frontend**: vanilla HTML/CSS/JS, Chart.js via CDN
- **Backend**: single Python serverless function (`/api/state`)
- **Market data**: yfinance (Yahoo Finance)
- **Deploy**: Vercel

## Local dev

```bash
# Install Vercel CLI (one-time)
npm i -g vercel

# Run locally
vercel dev
# → http://localhost:3000
```

Or just open `index.html` in a browser — the API will fail (no `/api/state`),
but you can see the UI shell.

## Deploy to Vercel

1. Push this repo to GitHub
2. Go to [vercel.com/new](https://vercel.com/new)
3. Import your repo
4. Click Deploy (defaults work)

Done — get a URL like `your-project.vercel.app`.

## How it works

- **`index.html`**: SPA. Stores positions in `localStorage`. Every 30 s
  POSTs all positions to `/api/state` to get computed greeks, P&L, history.
- **`api/state.py`**: Stateless. Takes positions list, fetches Yahoo data,
  computes Black-Scholes greeks, generates suggestions, returns JSON.

## Privacy

- No database, no analytics, no tracking
- Each user's positions live only in their own browser
- The server never sees any user's data persistently (only computes on each request)

## Limitations

- Vercel hobby plan: 30 s function timeout (should be plenty)
- yfinance scrape-based; Yahoo may rate-limit heavy use
- localStorage = lose data if you clear browser cache (export CSV regularly!)
