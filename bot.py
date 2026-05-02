import os
import anthropic
import yfinance as yf
import requests
import schedule
import time
from datetime import datetime
import pytz
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
SEND_HOUR = 16
SEND_MINUTE = 0
TIMEZONE = 'Asia/Singapore'
RISK_PROFILE = 'moderate'
PORTFOLIO = [
    dict(ticker='AVUV', name='American Century Small Cap Value ETF', shares=6.5604, avg_cost=119.61, cost_currency='USD', account='Moomoo'),
    dict(ticker='GOOGL', name='Alphabet Inc Class A', shares=1.5913, avg_cost=345.171, cost_currency='USD', account='Moomoo'),
    dict(ticker='NVDA', name='NVIDIA Corporation', shares=3.0057, avg_cost=208.85, cost_currency='USD', account='Moomoo'),
    dict(ticker='QQQ', name='Invesco QQQ Nasdaq-100', shares=3.5397, avg_cost=660.853, cost_currency='USD', account='Moomoo'),
    dict(ticker='SCHD', name='Schwab US Dividend Equity ETF', shares=30.1421, avg_cost=31.24, cost_currency='USD', account='Moomoo'),
    dict(ticker='VOO', name='Vanguard S&P 500 ETF', shares=14.0411, avg_cost=654.067, cost_currency='USD', account='Moomoo'),
    dict(ticker='VXUS', name='Vanguard Total International ETF', shares=2.8491, avg_cost=82.479, cost_currency='USD', account='Moomoo'),
    dict(ticker='SPOT', name='Spotify Technology SA', shares=3, avg_cost=286.483, cost_currency='USD', account='IGM'),
    dict(ticker='Z74.SI', name='Singapore Telecom Singtel', shares=100, avg_cost=3.287, cost_currency='SGD', account='IGM'),
    dict(ticker='CRO-USD', name='Cronos CRO', shares=7724.05, avg_cost=0.5988, cost_currency='USD', account='Crypto.com'),
    dict(ticker='ETH-USD', name='Ethereum ETH', shares=0.18215232, avg_cost=4720.75, cost_currency='USD', account='Crypto.com'),
    dict(ticker='ETHW-USD', name='EthereumPoW ETHW', shares=0.18215232, avg_cost=0.38, cost_currency='USD', account='Crypto.com'),
]
MANUAL_POSITIONS = [
    dict(name='Fidelity Asia Equity ESG', account='IGM', cost_usd=989.63, current_value_usd=1062.00),
]
def fetch_fx():
    try:
        data = yf.download('SGD=X', period='2d', interval='1d', progress=False, auto_adjust=True)
        return float(data['Close'].dropna().iloc[-1])
    except Exception:
        return 1.35
def fetch_prices(portfolio):
    tickers = [p['ticker'] for p in portfolio]
    prices = {}
    prev = {}
    try:
        data = yf.download(tickers, period='5d', interval='1d', progress=False, auto_adjust=True)
        for t in tickers:
            try:
                if len(tickers) == 1:
                    vals = data['Close'].dropna()
                else:
                    vals = data['Close'][t].dropna()
                prices[t] = float(vals.iloc[-1])
                prev[t] = float(vals.iloc[-2]) if len(vals) > 1 else None
            except Exception:
                prices[t] = None
                prev[t] = None
    except Exception as e:
        print('Price fetch error: ' + str(e))
    return prices, prev
def build_report(portfolio, prices, prev, fx):
    lines = []
    total_val = 0
    total_cost = 0
    accounts = {}
    for p in portfolio:
        acc = p['account']
        if acc not in accounts:
            accounts[acc] = []
        accounts[acc].append(p)
    for acc, holdings in accounts.items():
        lines.append('\n*' + acc + '*')
        for p in holdings:
            t = p['ticker']
            price = prices.get(t)
            if price is None:
                lines.append('  - ' + t + ': unavailable')
                continue
            if p['cost_currency'] == 'USD':
                val = price * fx * p['shares']
                cost = p['avg_cost'] * fx * p['shares']
            else:
                val = price * p['shares']
                cost = p['avg_cost'] * p['shares']
            pnl = val - cost
            pnl_pct = (pnl / cost * 100) if cost else 0
            day = ''
            if prev.get(t):
                d = (price - prev[t]) / prev[t] * 100
                if d >= 0:
                    day = ' (+' + str(round(d, 1)) + '% today)'
                else:
                    day = ' (' + str(round(d, 1)) + '% today)'
            if pnl >= 0:
                sign = '+'
                tag = '[UP]'
            else:
                sign = ''
                tag = '[DN]'
            if p['cost_currency'] == 'SGD':
                pdisplay = 'SGD ' + str(round(price, 3))
            else:
                pdisplay = 'USD ' + str(round(price, 2))
            lines.append(tag + ' *' + t + '* ' + pdisplay + day)
            lines.append('  ' + str(p['shares']) + ' units | SGD ' + str(round(val)) + ' | PnL ' + sign + 'SGD ' + str(round(pnl)) + ' (' + sign + str(round(pnl_pct, 1)) + '%)')
            total_val += val
            total_cost += cost
    lines.append('\n*IGM Unit Trusts*')
    for m in MANUAL_POSITIONS:
        val = m['current_value_usd'] * fx
        cost = m['cost_usd'] * fx
        pnl = val - cost
        pnl_pct = (pnl / cost * 100) if cost else 0
        if pnl >= 0:
            sign = '+'
        else:
            sign = ''
        lines.append('[UP] *' + m['name'] + '* (manual)')
        lines.append('  SGD ' + str(round(val)) + ' | PnL ' + sign + 'SGD ' + str(round(pnl)) + ' (' + sign + str(round(pnl_pct, 1)) + '%)')
        total_val += val
        total_cost += cost
    total_pnl = total_val - total_cost
    total_pct = (total_pnl / total_cost * 100) if total_cost else 0
    if total_pnl >= 0:
        sign = '+'
    else:
        sign = ''
    lines.append('\n--------------------')
    lines.append('Total: SGD ' + str(round(total_val)))
    lines.append('PnL: ' + sign + 'SGD ' + str(round(total_pnl)) + ' (' + sign + str(round(total_pct, 1)) + '%)')
    return '\n'.join(lines), total_val, total_pct
def get_ai(report, total_val, total_pct):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now(pytz.timezone(TIMEZONE)).strftime('%A %d %B %Y')
    tickers = ', '.join(p['ticker'] for p in PORTFOLIO)
    prompt = (
        'Today is ' + today + '. You are a concise portfolio analyst.\n\n'
        'PORTFOLIO (live prices in SGD):\n' + report + '\n\n'
        'Total SGD ' + str(round(total_val)) + ' | PnL ' + str(round(total_pct, 1)) + '%\n'
        'Risk: ' + RISK_PROFILE + ' | Singapore investor\n\n'
        '1. Search today market news for: ' + tickers + '\n'
        '2. List 3 most relevant news items\n'
        '3. Give HOLD/ADD/TRIM/EXIT recommendation per position\n'
        '4. Flag 1-2 things to watch next 48 hours\n\n'
        'Use Telegram Markdown bold only. Max 350 words.\n\n'
        '*MARKET PULSE*\n'
        '[3 news items]\n\n'
        '*RECOMMENDATIONS*\n'
        '[actions per position]\n\n'
        '*WATCH*\n'
        '[things to monitor]'
    )
    msg = client.messages.create(
        model='claude-sonnet-4-5',
        max_tokens=900,
        tools=[{'type': 'web_search_20250305', 'name': 'web_search'}],
        messages=[{'role': 'user', 'content': prompt}]
    )
    return ''.join(b.text for b in msg.content if b.type == 'text')
def send(text):
    url = 'https://api.telegram.org/bot' + TELEGRAM_BOT_TOKEN + '/sendMessage'
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'Markdown'}, timeout=15)
        time.sleep(0.5)
def run():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime('%d %b %Y %H:%M')
    print('Starting update ' + now)
    fx = fetch_fx()
    prices, prev = fetch_prices(PORTFOLIO)
    report, total_val, total_pct = build_report(PORTFOLIO, prices, prev, fx)
    print('Getting AI analysis...')
    ai = get_ai(report, total_val, total_pct)
    msg = 'PORTFOLIO BRIEF\n' + now + ' SGT\n--------------------\n\nHOLDINGS\n' + report + '\n\n' + ai
    send(msg)
    print('Done!')
if __name__ == '__main__':
    run()
    schedule.every().day.at(str(SEND_HOUR).zfill(2) + ':' + str(SEND_MINUTE).zfill(2)).do(run)
    while True:
        schedule.run_pending()
        time.sleep(30)
