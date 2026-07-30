import os
import anthropic
import yfinance as yf
import requests
import schedule
import time
import io
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
SEND_HOUR = 16
SEND_MINUTE = 0
TIMEZONE = 'Asia/Singapore'
RISK_PROFILE = 'moderate'
PORTFOLIO = [
    dict(ticker='AVUV', name='Amer Century SCV', shares=6.5604, avg_cost=119.61, cost_currency='USD', account='Moomoo'),
    dict(ticker='GOOGL', name='Alphabet (GOOGL)', shares=7.885, avg_cost=367.079, cost_currency='USD', account='Moomoo'),
    dict(ticker='NVDA', name='NVIDIA', shares=18.4645, avg_cost=206.293, cost_currency='USD', account='Moomoo'),
    dict(ticker='QQQ', name='Invesco QQQ', shares=6.9517, avg_cost=695.676, cost_currency='USD', account='Moomoo'),
    dict(ticker='SCHD', name='Schwab Dividend', shares=30.1421, avg_cost=31.24, cost_currency='USD', account='Moomoo'),
    dict(ticker='VOO', name='Vanguard S&P 500', shares=21.7768, avg_cost=666.112, cost_currency='USD', account='Moomoo'),
    dict(ticker='VXUS', name='Vanguard Intl', shares=14.8491, avg_cost=84.306, cost_currency='USD', account='Moomoo'),
    dict(ticker='Z74.SI', name='Singtel (Moomoo)', shares=100, avg_cost=4.30, cost_currency='SGD', account='Moomoo'),
    dict(ticker='Z74.SI', name='Singtel (IGM)', shares=100, avg_cost=3.287, cost_currency='SGD', account='IGM'),
    dict(ticker='CRO-USD', name='Cronos (CRO)', shares=7724.05, avg_cost=0.5988, cost_currency='USD', account='Crypto.com'),
    dict(ticker='ETH-USD', name='Ethereum (ETH)', shares=0.18215232, avg_cost=4720.75, cost_currency='USD', account='Crypto.com'),
    dict(ticker='ETHW-USD', name='EthereumPoW', shares=0.18215232, avg_cost=0.38, cost_currency='USD', account='Crypto.com'),
]
MANUAL_POSITIONS = [
    dict(name='Fidelity Asia ESG', account='IGM', cost_usd=989.63, current_value_usd=1062.00),
]
def fetch_fx():
    try:
        last = yf.Ticker('SGD=X').fast_info['last_price']
        if last:
            return 1.0 / float(last)
    except Exception as e:
        print('FX live-quote fetch error (trying daily close next): ' + str(e))
    try:
        data = yf.download('SGD=X', period='2d', interval='1d', progress=False, auto_adjust=True)
        return 1.0 / float(data['Close'].dropna().iloc[-1])
    except Exception as e:
        print('FX daily-close fetch error (using fallback 1.27): ' + str(e))
        return 1.27
def fetch_prices(portfolio):
    tickers = list(dict.fromkeys(p['ticker'] for p in portfolio))
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
def compute_positions(portfolio, prices, fx):
    results = []
    for p in portfolio:
        t = p['ticker']
        price = prices.get(t)
        if price is None:
            continue
        if p['cost_currency'] == 'USD':
            val_sgd = price * fx * p['shares']
            cost_sgd = p['avg_cost'] * fx * p['shares']
        else:
            val_sgd = price * p['shares']
            cost_sgd = p['avg_cost'] * p['shares']
        pnl = val_sgd - cost_sgd
        pnl_pct = (pnl / cost_sgd * 100) if cost_sgd else 0
        results.append(dict(
            ticker=t,
            name=p['name'],
            account=p['account'],
            val_sgd=val_sgd,
            val_usd=val_sgd / fx,
            cost_sgd=cost_sgd,
            pnl_sgd=pnl,
            pnl_pct=pnl_pct,
            price=price,
            cost_currency=p['cost_currency'],
        ))
    for m in MANUAL_POSITIONS:
        val_sgd = m['current_value_usd'] * fx
        cost_sgd = m['cost_usd'] * fx
        pnl = val_sgd - cost_sgd
        pnl_pct = (pnl / cost_sgd * 100) if cost_sgd else 0
        results.append(dict(
            ticker=m['name'],
            name=m['name'],
            account=m['account'],
            val_sgd=val_sgd,
            val_usd=m['current_value_usd'],
            cost_sgd=cost_sgd,
            pnl_sgd=pnl,
            pnl_pct=pnl_pct,
            price=None,
            cost_currency='USD',
        ))
    return results
def make_chart_with_day(positions, prev_prices, fx, today):
    BG = '#0d1117'
    CARD = '#161b22'
    GREEN = '#2ecc71'
    RED = '#e74c3c'
    GOLD = '#f39c12'
    WHITE = '#e8edf5'
    MUTED = '#8b949e'
    ACCENT = '#58a6ff'
    acc_colors = {'Moomoo': ACCENT, 'IGM': GOLD, 'Crypto.com': '#9b59b6'}
    accounts = ['Moomoo', 'IGM', 'Crypto.com']
    sorted_pos = []
    for acc in accounts:
        acc_pos = [p for p in positions if p['account'] == acc]
        acc_pos.sort(key=lambda x: x['pnl_pct'], reverse=True)
        sorted_pos.extend(acc_pos)
    names = [p['name'] for p in sorted_pos]
    pnl_pcts = [p['pnl_pct'] for p in sorted_pos]
    vals = [p['val_sgd'] for p in sorted_pos]
    accs = [p['account'] for p in sorted_pos]
    day_changes = []
    for p in sorted_pos:
        t = p['ticker']
        prev = prev_prices.get(t)
        if prev and p['price']:
            chg = (p['price'] - prev) / prev * 100
            day_changes.append((p['name'], chg))
    day_changes.sort(key=lambda x: x[1], reverse=True)
    fig = plt.figure(figsize=(12, 14), facecolor=BG)
    gs = fig.add_gridspec(3, 2, height_ratios=[0.8, 3.5, 1.5], hspace=0.35, wspace=0.3)
    # Header
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.set_facecolor(BG)
    ax_header.axis('off')
    total_val = sum(p['val_sgd'] for p in positions)
    total_cost = sum(p['cost_sgd'] for p in positions)
    total_pnl = total_val - total_cost
    total_pct = (total_pnl / total_cost * 100) if total_cost else 0
    total_usd = total_val / fx
    sign = '+' if total_pnl >= 0 else ''
    pnl_color = GREEN if total_pnl >= 0 else RED
    ax_header.text(0.5, 0.85, 'PORTFOLIO BRIEF', ha='center', va='top',
                   fontsize=18, fontweight='bold', color=WHITE, transform=ax_header.transAxes)
    ax_header.text(0.5, 0.55, today, ha='center', va='top',
                   fontsize=11, color=MUTED, transform=ax_header.transAxes)
    ax_header.text(0.5, 0.15,
                   'SGD {:,.0f}  /  USD {:,.0f}    '.format(total_val, total_usd) +
                   sign + 'SGD {:,.0f}  ({}{:.1f}%)'.format(total_pnl, sign, total_pct),
                   ha='center', va='top', fontsize=13, fontweight='bold',
                   color=pnl_color, transform=ax_header.transAxes)
    # Position P&L bars
    ax_bars = fig.add_subplot(gs[1, :])
    ax_bars.set_facecolor(CARD)
    ax_bars.spines['top'].set_visible(False)
    ax_bars.spines['right'].set_visible(False)
    ax_bars.spines['left'].set_color('#30363d')
    ax_bars.spines['bottom'].set_color('#30363d')
    y = np.arange(len(names))
    bars = ax_bars.barh(y, pnl_pcts, color=[GREEN if p >= 0 else RED for p in pnl_pcts],
                        height=0.6, alpha=0.85)
    for i, (acc, bar) in enumerate(zip(accs, bars)):
        ax_bars.barh(i, 0.3, left=min(pnl_pcts) - 2, color=acc_colors[acc],
                     height=0.6, alpha=1.0)
    ax_bars.set_yticks(y)
    ax_bars.set_yticklabels(names, fontsize=9, color=WHITE)
    ax_bars.set_xlabel('P&L %', color=MUTED, fontsize=9)
    ax_bars.tick_params(colors=MUTED)
    ax_bars.axvline(0, color='#30363d', linewidth=1)
    ax_bars.set_facecolor(CARD)
    ax_bars.tick_params(axis='y', which='both', length=0)
    for i, (bar, pct, val) in enumerate(zip(bars, pnl_pcts, vals)):
        label = '{:+.1f}%  SGD {:,.0f}'.format(pct, val)
        x_pos = bar.get_width()
        ha = 'left' if x_pos >= 0 else 'right'
        offset = 0.5 if x_pos >= 0 else -0.5
        ax_bars.text(x_pos + offset, bar.get_y() + bar.get_height() / 2,
                     label, va='center', ha=ha, fontsize=8,
                     color=WHITE, fontweight='bold')
    ax_bars.set_title('Position P&L  (colour = account)', color=WHITE,
                       fontsize=11, pad=10, loc='left')
    patches = [mpatches.Patch(color=c, label=a) for a, c in acc_colors.items()]
    ax_bars.legend(handles=patches, loc='lower right', facecolor=CARD,
                   edgecolor='#30363d', labelcolor=WHITE, fontsize=8)
    # Broker Summary
    ax_br = fig.add_subplot(gs[2, 0])
    ax_br.set_facecolor(CARD)
    ax_br.axis('off')
    ax_br.set_title('By Broker', color=WHITE, fontsize=11, pad=8, loc='left')
    broker_data = {}
    for p in positions:
        acc = p['account']
        if acc not in broker_data:
            broker_data[acc] = {'val': 0, 'cost': 0}
        broker_data[acc]['val'] += p['val_sgd']
        broker_data[acc]['cost'] += p['cost_sgd']
    row = 0.88
    for acc in accounts:
        if acc not in broker_data:
            continue
        d = broker_data[acc]
        pnl = d['val'] - d['cost']
        pct = (pnl / d['cost'] * 100) if d['cost'] else 0
        sign = '+' if pnl >= 0 else ''
        col = GREEN if pnl >= 0 else RED
        ax_br.text(0.02, row, acc, color=acc_colors[acc],
                   fontsize=10, fontweight='bold', transform=ax_br.transAxes)
        ax_br.text(0.02, row - 0.13,
                   'SGD {:,.0f} / USD {:,.0f}'.format(d['val'], d['val'] / fx),
                   color=WHITE, fontsize=9, transform=ax_br.transAxes)
        ax_br.text(0.02, row - 0.26,
                   'PnL {}{:.1f}%'.format(sign, pct),
                   color=col, fontsize=9, fontweight='bold', transform=ax_br.transAxes)
        row -= 0.38
    # Today's movers
    ax_mv = fig.add_subplot(gs[2, 1])
    ax_mv.set_facecolor(CARD)
    ax_mv.axis('off')
    ax_mv.set_title("Today's Movers", color=WHITE, fontsize=11, pad=8, loc='left')
    top_up = [x for x in day_changes if x[1] >= 0][:2]
    top_dn = sorted([x for x in day_changes if x[1] < 0], key=lambda x: x[1])[:2]
    movers = top_up + top_dn
    row = 0.92
    for name, chg in movers:
        col = GREEN if chg >= 0 else RED
        sign = '+' if chg >= 0 else ''
        ax_mv.text(0.02, row, name[:20], color=WHITE,
                   fontsize=9, transform=ax_mv.transAxes)
        ax_mv.text(0.75, row, '{}{:.2f}%'.format(sign, chg),
                   color=col, fontsize=9, fontweight='bold',
                   transform=ax_mv.transAxes)
        row -= 0.22
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close()
    buf.seek(0)
    return buf
def build_text_report(positions, prev_prices, fx):
    lines = []
    accounts = ['Moomoo', 'IGM', 'Crypto.com']
    for acc in accounts:
        acc_pos = [p for p in positions if p['account'] == acc]
        if not acc_pos:
            continue
        lines.append('\n*' + acc + '*')
        for p in acc_pos:
            t = p['ticker']
            prev = prev_prices.get(t)
            day = ''
            if prev and p['price']:
                d = (p['price'] - prev) / prev * 100
                day = ' ({:+.1f}% today)'.format(d)
            sign = '+' if p['pnl_sgd'] >= 0 else ''
            tag = 'UP' if p['pnl_sgd'] >= 0 else 'DN'
            if p['cost_currency'] == 'SGD':
                pdisplay = 'SGD {:.3f}'.format(p['price']) if p['price'] else 'N/A'
            else:
                pdisplay = 'USD {:.2f}'.format(p['price']) if p['price'] else 'N/A'
            lines.append('[{}] *{}*  {}{}'.format(tag, t, pdisplay, day))
            lines.append('  SGD {:,.0f} | PnL {}SGD {:,.0f} ({}{}%)'.format(
                p['val_sgd'], sign, p['pnl_sgd'], sign, round(p['pnl_pct'], 1)))
    lines.append('\n--------------------')
    lines.append('*Broker Summary*')
    broker_data = {}
    for p in positions:
        acc = p['account']
        if acc not in broker_data:
            broker_data[acc] = {'val': 0, 'cost': 0}
        broker_data[acc]['val'] += p['val_sgd']
        broker_data[acc]['cost'] += p['cost_sgd']
    for acc in accounts:
        if acc not in broker_data:
            continue
        d = broker_data[acc]
        pnl = d['val'] - d['cost']
        pct = (pnl / d['cost'] * 100) if d['cost'] else 0
        sign = '+' if pnl >= 0 else ''
        lines.append('{}: SGD {:,.0f} / USD {:,.0f} | PnL {}{:.1f}%'.format(
            acc, d['val'], d['val'] / fx, sign, pct))
    total_val = sum(p['val_sgd'] for p in positions)
    total_cost = sum(p['cost_sgd'] for p in positions)
    total_pnl = total_val - total_cost
    total_pct = (total_pnl / total_cost * 100) if total_cost else 0
    sign = '+' if total_pnl >= 0 else ''
    lines.append('\n*TOTAL*')
    lines.append('SGD {:,.0f} / USD {:,.0f}'.format(total_val, total_val / fx))
    lines.append('PnL: {}SGD {:,.0f} ({}{}%)'.format(sign, total_pnl, sign, round(total_pct, 1)))
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
        '3. Give recommendation per position. Start each line with exactly one of these words: HOLD ADD TRIM EXIT — then the ticker, then your reasoning. Do not use any emoji.\n'
        '4. Flag 1-2 things to watch next 48 hours\n\n'
        'Use Telegram Markdown bold only. Max 350 words.\n\n'
        '*MARKET PULSE*\n'
        '[3 news items]\n\n'
        '*RECOMMENDATIONS*\n'
        '[actions per position]\n\n'
        '*WATCH*\n'
        '[things to monitor]'
    )
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=900,
                tools=[{'type': 'web_search_20250305', 'name': 'web_search'}],
                messages=[{'role': 'user', 'content': prompt}]
            )
            return ''.join(b.text for b in msg.content if b.type == 'text')
        except Exception as e:
            print('AI attempt ' + str(attempt + 1) + ' failed: ' + str(e))
            if attempt < 2:
                time.sleep(30)
    return 'AI analysis unavailable - API overloaded. Check markets manually.'
def format_recommendations(ai_text):
    GREEN = '\U0001F7E2'  # 
    YELLOW = '\U0001F7E1'  # 
    RED = '\U0001F534'  # 
    lines = ai_text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('ADD'):
            out.append(GREEN + ' *ADD* ' + stripped[3:].lstrip(' \u2014-'))
        elif stripped.startswith('HOLD'):
            out.append(YELLOW + ' *HOLD* ' + stripped[4:].lstrip(' \u2014-'))
        elif stripped.startswith('TRIM'):
            out.append(RED + ' *TRIM* ' + stripped[4:].lstrip(' \u2014-'))
        elif stripped.startswith('EXIT'):
            out.append(RED + ' *EXIT* ' + stripped[4:].lstrip(' \u2014-'))
        else:
            out.append(line)
    return '\n'.join(out)
def send_photo(buf, caption):
    url = 'https://api.telegram.org/bot' + TELEGRAM_BOT_TOKEN + '/sendPhoto'
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'},
                  files={'photo': ('chart.png', buf, 'image/png')}, timeout=30)
def send_text(text):
    url = 'https://api.telegram.org/bot' + TELEGRAM_BOT_TOKEN + '/sendMessage'
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        resp = requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'Markdown'}, timeout=15)
        if not resp.ok:
            # Fallback: send without markdown
            requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk}, timeout=15)
        time.sleep(0.5)
def run():
    tz = pytz.timezone(TIMEZONE)
    now_sgt = datetime.now(tz)
    now_str = now_sgt.strftime('%d %b %Y %H:%M')
    today_str = now_sgt.strftime('%d %b %Y %H:%M SGT')
    # AI reco every Monday
    send_ai = now_sgt.weekday() == 0
    print('Starting update ' + now_str + ' SGT')
    fx = fetch_fx()
    print('FX: 1 USD = {:.4f} SGD'.format(fx))
    prices, prev_prices = fetch_prices(PORTFOLIO)
    print('Prices fetched')
    positions = compute_positions(PORTFOLIO, prices, fx)
    chart_buf = make_chart_with_day(positions, prev_prices, fx, today_str)
    print('Chart generated')
    text_report, total_val, total_pct = build_text_report(positions, prev_prices, fx)
    if send_ai:
        print('Getting AI analysis...')
        ai = get_ai(text_report, total_val, total_pct)
        ai = format_recommendations(ai)
        send_photo(chart_buf, 'Portfolio Brief  ' + now_str + ' SGT')
        send_text(text_report + '\n\n' + ai)
    else:
        send_photo(chart_buf, 'Portfolio Brief  ' + now_str + ' SGT')
        send_text(text_report)
    print('Done!')
if __name__ == '__main__':
    run()
