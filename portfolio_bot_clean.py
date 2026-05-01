import os
import anthropic
import yfinance as yf
import requests
import schedule
import time
from datetime import datetime
import pytz

ANTHROPIC_API_KEY  = os.getenv(“ANTHROPIC_API_KEY”,  “YOUR_ANTHROPIC_API_KEY”)
TELEGRAM_BOT_TOKEN = os.getenv(“TELEGRAM_BOT_TOKEN”, “YOUR_BOT_TOKEN”)
TELEGRAM_CHAT_ID   = os.getenv(“TELEGRAM_CHAT_ID”,   “266348361”)

SEND_HOUR   = 16
SEND_MINUTE = 0
TIMEZONE    = “Asia/Singapore”
CURRENCY    = “SGD”
RISK_PROFILE = “moderate”

PORTFOLIO = [
{“ticker”: “AVUV”,    “name”: “American Century Small Cap Value ETF”,       “shares”: 6.5604,     “avg_cost”: 119.61,  “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “GOOGL”,   “name”: “Alphabet Inc Class A”,                        “shares”: 1.5913,     “avg_cost”: 345.171, “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “NVDA”,    “name”: “NVIDIA Corporation”,                          “shares”: 3.0057,     “avg_cost”: 208.85,  “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “QQQ”,     “name”: “Invesco QQQ Trust Nasdaq-100”,                “shares”: 3.5397,     “avg_cost”: 660.853, “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “SCHD”,    “name”: “Schwab US Dividend Equity ETF”,               “shares”: 30.1421,    “avg_cost”: 31.24,   “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “VOO”,     “name”: “Vanguard S&P 500 ETF”,                        “shares”: 14.0411,    “avg_cost”: 654.067, “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “VXUS”,    “name”: “Vanguard Total International Stock ETF”,      “shares”: 2.8491,     “avg_cost”: 82.479,  “cost_currency”: “USD”, “account”: “Moomoo”},
{“ticker”: “SPOT”,    “name”: “Spotify Technology SA”,                       “shares”: 3,          “avg_cost”: 286.483, “cost_currency”: “USD”, “account”: “IGM”},
{“ticker”: “Z74.SI”,  “name”: “Singapore Telecommunications Singtel”,        “shares”: 100,        “avg_cost”: 3.287,   “cost_currency”: “SGD”, “account”: “IGM”},
{“ticker”: “CRO-USD”, “name”: “Cronos CRO”,                                  “shares”: 7724.05,    “avg_cost”: 0.5988,  “cost_currency”: “USD”, “account”: “Crypto.com”},
{“ticker”: “ETH-USD”, “name”: “Ethereum ETH”,                                “shares”: 0.18215232, “avg_cost”: 4720.75, “cost_currency”: “USD”, “account”: “Crypto.com”},
{“ticker”: “ETHW-USD”,“name”: “EthereumPoW ETHW”,                            “shares”: 0.18215232, “avg_cost”: 0.38,    “cost_currency”: “USD”, “account”: “Crypto.com”},
]

MANUAL_POSITIONS = [
{
“name”: “Fidelity Asia Equity ESG A-USD”,
“account”: “IGM”,
“cost_usd”: 989.63,
“current_value_usd”: 1062.00,
}
]

def fetch_fx_rate():
try:
data = yf.download(“SGD=X”, period=“2d”, interval=“1d”, progress=False, auto_adjust=True)
return float(data[“Close”].dropna().iloc[-1])
except:
return 1.35

def fetch_prices_and_prev(portfolio):
tickers = [p[“ticker”] for p in portfolio]
prices, prev_prices = {}, {}
if not tickers:
return prices, prev_prices
data = yf.download(tickers, period=“5d”, interval=“1d”, progress=False, auto_adjust=True)
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
prices[ticker]      = safe_get(data[“Close”], ticker, -1)
prev_prices[ticker] = safe_get(data[“Close”], ticker, -2)
return prices, prev_prices

def build_holdings(portfolio, prices, prev_prices, fx_usd_sgd):
lines = []
total_value_sgd = 0
total_cost_sgd  = 0
accounts = {}
for p in portfolio:
acc = p.get(“account”, “Portfolio”)
accounts.setdefault(acc, []).append(p)
for acc_name, holdings in accounts.items():
lines.append(”\n*” + acc_name + “*”)
for p in holdings:
ticker   = p[“ticker”]
shares   = p[“shares”]
avg_cost = p[“avg_cost”]
cost_ccy = p[“cost_currency”]
price    = prices.get(ticker)
prev     = prev_prices.get(ticker)
if price is None:
lines.append(”  - “ + ticker + “: price unavailable”)
continue
if cost_ccy == “USD”:
price_sgd    = price * fx_usd_sgd
avg_cost_sgd = avg_cost * fx_usd_sgd
else:
price_sgd    = price
avg_cost_sgd = avg_cost
value_sgd = price_sgd * shares
cost_sgd  = avg_cost_sgd * shares
pnl_sgd   = value_sgd - cost_sgd
pnl_pct   = (pnl_sgd / cost_sgd * 100) if cost_sgd else 0
day_str = “”
if prev:
d_pct = (price - prev) / prev * 100
arrow = “+” if d_pct >= 0 else “”
day_str = “ (” + arrow + str(round(d_pct, 1)) + “% today)”
emoji    = “green” if pnl_sgd >= 0 else “red”
pnl_sign = “+” if pnl_sgd >= 0 else “”
if cost_ccy == “SGD”:
price_disp = “SGD “ + str(round(price, 3))
else:
price_disp = “USD “ + str(round(price, 2))
lines.append(
“  [” + emoji + “] *” + ticker + “* “ + price_disp + day_str + “\n” +
“     “ + str(shares) + “ units | SGD “ + str(round(value_sgd, 0)) +
“ | P&L “ + pnl_sign + “SGD “ + str(round(pnl_sgd, 0)) +
“ (” + pnl_sign + str(round(pnl_pct, 1)) + “%)”
)
total_value_sgd += value_sgd
total_cost_sgd  += cost_sgd
if MANUAL_POSITIONS:
lines.append(”\n*IGM - Unit Trusts*”)
for mp in MANUAL_POSITIONS:
val_sgd  = mp[“current_value_usd”] * fx_usd_sgd
cost_sgd = mp[“cost_usd”] * fx_usd_sgd
pnl_sgd  = val_sgd - cost_sgd
pnl_pct  = (pnl_sgd / cost_sgd * 100) if cost_sgd else 0
pnl_sign = “+” if pnl_sgd >= 0 else “”
emoji    = “green” if pnl_sgd >= 0 else “red”
lines.append(
“  [” + emoji + “] *” + mp[“name”][:22] + “* (manual)\n” +
“     SGD “ + str(round(val_sgd, 0)) +
“ | P&L “ + pnl_sign + “SGD “ + str(round(pnl_sgd, 0)) +
“ (” + pnl_sign + str(round(pnl_pct, 1)) + “%)”
)
total_value_sgd += val_sgd
total_cost_sgd  += cost_sgd
total_pnl     = total_value_sgd - total_cost_sgd
total_pnl_pct = (total_pnl / total_cost_sgd * 100) if total_cost_sgd else 0
pnl_sign      = “+” if total_pnl >= 0 else “”
lines.append(
“\n––––––––––\n” +
“Total Value: SGD “ + str(round(total_value_sgd, 0)) + “\n” +
“Total P&L: “ + pnl_sign + “SGD “ + str(round(total_pnl, 0)) +
“ (” + pnl_sign + str(round(total_pnl_pct, 1)) + “%)”
)
return “\n”.join(lines), total_value_sgd, total_pnl_pct

def get_ai_analysis(holdings_text, total_value_sgd, total_pnl_pct):
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
today  = datetime.now(pytz.timezone(TIMEZONE)).strftime(”%A, %d %B %Y”)
tickers = “, “.join(p[“ticker”] for p in PORTFOLIO)
prompt = (
“Today is “ + today + “. You are a sharp, concise portfolio analyst.\n\n”
“PORTFOLIO SNAPSHOT (live prices, in SGD):\n” + holdings_text + “\n\n”
“Total: SGD “ + str(round(total_value_sgd, 0)) + “ | P&L: “ + str(round(total_pnl_pct, 1)) + “%\n”
“Risk profile: “ + RISK_PROFILE + “ | Currency: SGD | Location: Singapore\n\n”
“TASK:\n”
“1. Search for TODAY’s market news affecting: “ + tickers + “\n”
“2. Pick the 3 most relevant news items\n”
“3. Give specific recommendations: HOLD / ADD / TRIM / EXIT per position\n”
“4. Flag 1-2 things to watch in next 48 hours\n\n”
“Use Telegram Markdown (*bold* only). Max 350 words. Format:\n\n”
“MARKET PULSE\n”
“[3 news items]\n\n”
“RECOMMENDATIONS\n”
“[per-position actions]\n\n”
“WATCH\n”
“[things to monitor]\n\n”
“Risk: “ + RISK_PROFILE + “ | “ + today
)
msg = client.messages.create(
model=“claude-sonnet-4-20250514”,
max_tokens=900,
tools=[{“type”: “web_search_20250305”, “name”: “web_search”}],
messages=[{“role”: “user”, “content”: prompt}]
)
return “”.join(b.text for b in msg.content if b.type == “text”)

def send_telegram(text):
url = “https://api.telegram.org/bot” + TELEGRAM_BOT_TOKEN + “/sendMessage”
chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
for chunk in chunks:
r = requests.post(url, json={
“chat_id”: TELEGRAM_CHAT_ID,
“text”: chunk,
“parse_mode”: “Markdown”
}, timeout=15)
if not r.ok:
print(“Telegram error: “ + r.text)
time.sleep(0.5)
return True

def daily_update():
tz  = pytz.timezone(TIMEZONE)
now = datetime.now(tz).strftime(”%d %b %Y %H:%M”)
print(”[” + now + “] Starting portfolio update…”)
try:
fx_usd_sgd = fetch_fx_rate()
print(”[” + now + “] FX: 1 USD = “ + str(round(fx_usd_sgd, 4)) + “ SGD”)
prices, prev_prices = fetch_prices_and_prev(PORTFOLIO)
print(”[” + now + “] Prices fetched for “ + str(len(prices)) + “ tickers”)
holdings_text, total_value, total_pnl_pct = build_holdings(
PORTFOLIO, prices, prev_prices, fx_usd_sgd
)
print(”[” + now + “] Getting AI analysis…”)
ai_section = get_ai_analysis(holdings_text, total_value, total_pnl_pct)
full_msg = (
“PORTFOLIO BRIEF\n” +
now + “ SGT\n” +
“––––––––––\n\n” +
“HOLDINGS\n” +
holdings_text + “\n\n” +
ai_section
)
send_telegram(full_msg)
print(”[” + now + “] Sent to Telegram successfully.”)
except Exception as e:
err = “Portfolio Bot error (” + now + “): “ + str(e)
print(err)
try:
send_telegram(err)
except:
pass

if **name** == “**main**”:
send_time = str(SEND_HOUR).zfill(2) + “:” + str(SEND_MINUTE).zfill(2)
print(“Portfolio Bot starting…”)
print(“Schedule: “ + send_time + “ SGT daily”)
daily_update()
schedule.every().day.at(send_time).do(daily_update)
while True:
schedule.run_pending()
time.sleep(30)
