#!/usr/bin/env python3
“””
Portfolio Intelligence Bot — Pre-configured
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Holdings pre-loaded from Moomoo + Brokerage 2 + Crypto.com accounts.

INSTALL:
pip install anthropic yfinance requests schedule pytz

RUN (test immediately):
python portfolio_bot.py

FREE HOSTING:
PythonAnywhere  → upload & set daily scheduled task
GitHub Actions  → use cron workflow below
Railway.app     → deploy as background service

━━━ GITHUB ACTIONS CRON (.github/workflows/portfolio.yml) ━━━━━━━━━━━━━━━━━━

# name: Portfolio Bot

# on:

# schedule:

# - cron: ‘0 8 * * *’   # 16:00 SGT = 08:00 UTC

# workflow_dispatch:

# jobs:

# run:

# runs-on: ubuntu-latest

# steps:

# - uses: actions/checkout@v3

# - uses: actions/setup-python@v4

# with: { python-version: ‘3.11’ }

# - run: pip install anthropic yfinance requests pytz

# - run: python portfolio_bot.py

# env:

# ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

# TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}

# TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
“””

import os
import anthropic
import yfinance as yf
import requests
import schedule
import time
import json
from datetime import datetime
import pytz

# ── CONFIG ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY  = os.getenv(“ANTHROPIC_API_KEY”,  “YOUR_ANTHROPIC_API_KEY”)
TELEGRAM_BOT_TOKEN = os.getenv(“TELEGRAM_BOT_TOKEN”, “YOUR_BOT_TOKEN”)
TELEGRAM_CHAT_ID   = os.getenv(“TELEGRAM_CHAT_ID”,   “266348361”)

SEND_HOUR   = 16
SEND_MINUTE = 0
TIMEZONE    = “Asia/Singapore”
CURRENCY    = “SGD”
FX_TICKER   = “SGD=X”   # Yahoo Finance: 1 USD → SGD

RISK_PROFILE = “moderate”

# ── YOUR PORTFOLIO ─────────────────────────────────────────────────────────────

# ONLY UPDATE THIS when you buy or sell. All prices are fetched automatically.

# 

# avg_cost for USD-denominated assets = price in USD

# avg_cost for SGD-denominated assets = price in SGD

# cost_currency = the currency your avg_cost is in

PORTFOLIO = [
# ── Moomoo Margin Account (0561) ──────────────────────────────────────────
{
“ticker”: “AVUV”,
“name”: “American Century Small Cap Value ETF”,
“shares”: 6.5604,
“avg_cost”: 119.61,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
{
“ticker”: “GOOGL”,
“name”: “Alphabet Inc (Class A)”,
“shares”: 1.5913,
“avg_cost”: 345.171,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
{
“ticker”: “NVDA”,
“name”: “NVIDIA Corporation”,
“shares”: 3.0057,
“avg_cost”: 208.85,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
{
“ticker”: “QQQ”,
“name”: “Invesco QQQ Trust (Nasdaq-100)”,
“shares”: 3.5397,
“avg_cost”: 660.853,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
{
“ticker”: “SCHD”,
“name”: “Schwab US Dividend Equity ETF”,
“shares”: 30.1421,
“avg_cost”: 31.24,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
{
“ticker”: “VOO”,
“name”: “Vanguard S&P 500 ETF”,
“shares”: 14.0411,
“avg_cost”: 654.067,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
{
“ticker”: “VXUS”,
“name”: “Vanguard Total International Stock ETF”,
“shares”: 2.8491,
“avg_cost”: 82.479,
“cost_currency”: “USD”,
“account”: “Moomoo”
},
# ── Second Brokerage ──────────────────────────────────────────────────────
{
“ticker”: “SPOT”,
“name”: “Spotify Technology SA”,
“shares”: 3,
“avg_cost”: 286.483,
“cost_currency”: “USD”,
“account”: “IGM”
},
{
“ticker”: “Z74.SI”,
“name”: “Singapore Telecommunications Ltd (Singtel)”,
“shares”: 100,
“avg_cost”: 3.287,
“cost_currency”: “SGD”,
“account”: “IGM”
},
# ── Crypto.com ────────────────────────────────────────────────────────────
{
“ticker”: “CRO-USD”,
“name”: “Cronos (CRO)”,
“shares”: 7724.05,
“avg_cost”: 0.5988,
“cost_currency”: “USD”,
“account”: “Crypto.com”
},
{
“ticker”: “ETH-USD”,
“name”: “Ethereum (ETH)”,
“shares”: 0.18215232,
“avg_cost”: 4720.75,
“cost_currency”: “USD”,
“account”: “Crypto.com”
},
{
“ticker”: “ETHW-USD”,
“name”: “EthereumPoW (ETHW)”,
“shares”: 0.18215232,
“avg_cost”: 0.38,       # approx — near-zero value (~$0.07 total)
“cost_currency”: “USD”,
“account”: “Crypto.com”
},
# Fidelity Asia Equity ESG A-USD: not on Yahoo Finance (unit trust).
# Tracked as a manual entry — current value updated via MANUAL_POSITIONS below.
# To update: change “current_value_usd” when you check the fund value.
]

# ── MANUAL POSITIONS (funds/assets not on Yahoo Finance) ─────────────────────

# Update “current_value_usd” periodically when you check your fund dashboard.

MANUAL_POSITIONS = [
{
“name”: “Fidelity Asia Equity ESG A-USD”,
“account”: “IGM”,
“cost_usd”: 989.63,
“current_value_usd”: 1062.00,   # ← update this manually when you check
“note”: “Unit trust — not on Yahoo Finance”
}
]

# ── FX RATES ──────────────────────────────────────────────────────────────────

def fetch_fx_rate():
“”“Fetch USD → SGD rate from Yahoo Finance.”””
try:
data = yf.download(“SGD=X”, period=“2d”, interval=“1d”, progress=False, auto_adjust=True)
return float(data[“Close”].dropna().iloc[-1])
except:
return 1.35   # fallback estimate

def fetch_sgd_usd_rate():
“”“Fetch SGD → USD (inverse of above).”””
usd_sgd = fetch_fx_rate()
return 1.0 / usd_sgd if usd_sgd else 0.74

# ── LIVE PRICE FETCH ──────────────────────────────────────────────────────────

def fetch_prices_and_prev(portfolio):
“”“Fetch current and previous close for all Yahoo-listed tickers.”””
tickers = [p[“ticker”] for p in portfolio]

```
prices, prev_prices = {}, {}

if not tickers:
    return prices, prev_prices

data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=True)

def safe_get(closes, ticker, idx):
    try:
        if len(tickers) == 1:
            vals = closes.dropna()
        else:
            vals = closes[ticker].dropna()
        return float(vals.iloc[idx]) if len(vals) > abs(idx) else None
    except:
        return None

for ticker in tickers:
    prices[ticker]      = safe_get(data["Close"], ticker, -1)
    prev_prices[ticker] = safe_get(data["Close"], ticker, -2)

return prices, prev_prices
```

# ── BUILD HOLDINGS TABLE ──────────────────────────────────────────────────────

def build_holdings(portfolio, prices, prev_prices, fx_usd_sgd, fx_sgd_usd):
lines = []
total_value_sgd = 0
total_cost_sgd  = 0

```
# Group by account
accounts = {}
for p in portfolio:
    acc = p.get("account", "Portfolio")
    accounts.setdefault(acc, []).append(p)

for acc_name, holdings in accounts.items():
    lines.append(f"\n*{acc_name}*")
    for p in holdings:
        ticker   = p["ticker"]
        shares   = p["shares"]
        avg_cost = p["avg_cost"]
        cost_ccy = p["cost_currency"]
        price    = prices.get(ticker)
        prev     = prev_prices.get(ticker)

        if price is None:
            lines.append(f"  ⚪ {ticker}: price unavailable")
            continue

        # Convert everything to SGD for totals
        if cost_ccy == "USD":
            price_sgd    = price * fx_usd_sgd
            avg_cost_sgd = avg_cost * fx_usd_sgd
        else:  # SGD
            price_sgd    = price
            avg_cost_sgd = avg_cost

        value_sgd = price_sgd * shares
        cost_sgd  = avg_cost_sgd * shares
        pnl_sgd   = value_sgd - cost_sgd
        pnl_pct   = (pnl_sgd / cost_sgd * 100) if cost_sgd else 0

        day_str = ""
        if prev:
            d_pct  = (price - prev) / prev * 100
            arrow  = "▲" if d_pct >= 0 else "▼"
            day_str = f" {arrow}{abs(d_pct):.1f}%"

        emoji    = "🟢" if pnl_sgd >= 0 else "🔴"
        pnl_sign = "+" if pnl_sgd >= 0 else ""
        ccy_disp = "SGD" if cost_ccy == "SGD" else "USD"
        price_disp = f"{ccy_disp} {price:.3f}" if cost_ccy == "SGD" else f"USD {price:.2f}"

        lines.append(
            f"  {emoji} *{ticker}* {price_disp}{day_str}\n"
            f"     {shares} units | SGD {value_sgd:,.0f} | P&L {pnl_sign}SGD {pnl_sgd:,.0f} ({pnl_sign}{pnl_pct:.1f}%)"
        )

        total_value_sgd += value_sgd
        total_cost_sgd  += cost_sgd

# Add manual positions
if MANUAL_POSITIONS:
    lines.append("\n*IGM — Unit Trusts*")
    for mp in MANUAL_POSITIONS:
        val_sgd  = mp["current_value_usd"] * fx_usd_sgd
        cost_sgd = mp["cost_usd"] * fx_usd_sgd
        pnl_sgd  = val_sgd - cost_sgd
        pnl_pct  = (pnl_sgd / cost_sgd * 100) if cost_sgd else 0
        pnl_sign = "+" if pnl_sgd >= 0 else ""
        emoji    = "🟢" if pnl_sgd >= 0 else "🔴"
        lines.append(
            f"  {emoji} *{mp['name'][:22]}* _(manual)_\n"
            f"     SGD {val_sgd:,.0f} | P&L {pnl_sign}SGD {pnl_sgd:,.0f} ({pnl_sign}{pnl_pct:.1f}%)"
        )
        total_value_sgd += val_sgd
        total_cost_sgd  += cost_sgd

# Totals
total_pnl     = total_value_sgd - total_cost_sgd
total_pnl_pct = (total_pnl / total_cost_sgd * 100) if total_cost_sgd else 0
pnl_sign      = "+" if total_pnl >= 0 else ""

lines.append(
    f"\n━━━━━━━━━━━━━━━━━━\n"
    f"💰 *Total Value:* SGD {total_value_sgd:,.0f}\n"
    f"📊 *Total P&L:* {pnl_sign}SGD {total_pnl:,.0f} ({pnl_sign}{total_pnl_pct:.1f}%)"
)

return "\n".join(lines), total_value_sgd, total_pnl_pct
```

# ── AI ANALYSIS ───────────────────────────────────────────────────────────────

def get_ai_analysis(holdings_text, total_value_sgd, total_pnl_pct):
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
today  = datetime.now(pytz.timezone(TIMEZONE)).strftime(”%A, %d %B %Y”)

```
tickers = ", ".join(p["ticker"] for p in PORTFOLIO)
prompt = f"""Today is {today}. You are a sharp, concise portfolio analyst.
```

PORTFOLIO SNAPSHOT (pre-calculated with live prices, in SGD):
{holdings_text}

Portfolio total: SGD {total_value_sgd:,.0f} | Overall P&L: {total_pnl_pct:+.1f}%
Risk profile: {RISK_PROFILE} | Base currency: SGD | Investor location: Singapore

TASK:

1. Search for TODAY’s key market news affecting: {tickers}
1. Pick the 3 most impactful news items for this specific portfolio
1. Give specific, actionable recommendations:
- Which positions to HOLD / ADD / TRIM / EXIT and why
- Any concentration risk or rebalancing to flag
- Match advice to a {RISK_PROFILE} risk profile
1. One key thing to watch in the next 48 hours

Use Telegram Markdown (*bold* only, no HTML). Max 400 words. Format:

📰 *MARKET PULSE*
[3 news items — ticker impact in brackets]

🎯 *RECOMMENDATIONS*
[specific per-position or thematic actions]

⚠️ *WATCH*
[1-2 things to monitor]

*Risk: {RISK_PROFILE} · {today}*”””

```
msg = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=900,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    messages=[{"role": "user", "content": prompt}]
)

return "".join(b.text for b in msg.content if b.type == "text")
```

# ── TELEGRAM ──────────────────────────────────────────────────────────────────

def send_telegram(text):
url = f”https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage”
# Split if too long (Telegram limit 4096 chars)
chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
for chunk in chunks:
r = requests.post(url, json={
“chat_id”: TELEGRAM_CHAT_ID,
“text”: chunk,
“parse_mode”: “Markdown”
}, timeout=15)
if not r.ok:
print(f”Telegram error: {r.text}”)
time.sleep(0.5)
return True

# ── MAIN JOB ──────────────────────────────────────────────────────────────────

def daily_update():
tz  = pytz.timezone(TIMEZONE)
now = datetime.now(tz).strftime(”%d %b %Y %H:%M”)
print(f”[{now}] Starting portfolio update…”)

```
try:
    fx_usd_sgd = fetch_fx_rate()
    fx_sgd_usd = 1.0 / fx_usd_sgd
    print(f"[{now}] FX: 1 USD = {fx_usd_sgd:.4f} SGD")

    prices, prev_prices = fetch_prices_and_prev(PORTFOLIO)
    print(f"[{now}] Prices fetched for {len(prices)} tickers")

    holdings_text, total_value, total_pnl_pct = build_holdings(
        PORTFOLIO, prices, prev_prices, fx_usd_sgd, fx_sgd_usd
    )

    print(f"[{now}] Getting AI analysis + market news...")
    ai_section = get_ai_analysis(holdings_text, total_value, total_pnl_pct)

    full_msg = (
        f"📡 *PORTFOLIO BRIEF*\n"
        f"_{now} SGT_\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💼 *HOLDINGS*\n"
        f"{holdings_text}\n\n"
        f"{ai_section}"
    )

    send_telegram(full_msg)
    print(f"[{now}] ✅ Update sent to Telegram.")

except Exception as e:
    err = f"⚠️ Portfolio Bot error ({now}): {e}"
    print(err)
    try:
        send_telegram(err)
    except:
        pass
```

# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if **name** == “**main**”:
send_time = f”{SEND_HOUR:02d}:{SEND_MINUTE:02d}”
tickers   = “ · “.join(p[“ticker”] for p in PORTFOLIO)

```
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  📡 Portfolio Intelligence Bot — Ready")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"  Tickers  : {tickers}")
print(f"  Schedule : {send_time} SGT daily")
print(f"  Currency : SGD (USD→SGD via Yahoo FX)")
print(f"  Risk     : {RISK_PROFILE}")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  Running first update now...")
print()

daily_update()  # immediate run on start

schedule.every().day.at(send_time).do(daily_update)
while True:
    schedule.run_pending()
    time.sleep(30)
```
