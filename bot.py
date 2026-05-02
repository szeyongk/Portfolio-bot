append(tag + ' *' + t + '* ' + pdisplay + day)
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
today = datetime.now(pytz.timezone(TIMEZONE)).strftime(’%A %d %B %Y’)
tickers = ’, ’.join(p[‘ticker’] for p in PORTFOLIO)
prompt = (
’Today is ’ + today + ‘. You are a concise portfolio analyst.\n\n’
‘PORTFOLIO (live prices in SGD):\n’ + report + ‘\n\n’
’Total SGD ’ + str(round(total_val)) + ’ | PnL ’ + str(round(total_pct, 1)) + ‘%\n’
‘Risk: ’ + RISK_PROFILE + ’ | Singapore investor\n\n’
’1. Search today market news for: ’ + tickers + ‘\n’
‘2. List 3 most relevant news items\n’
‘3. Give HOLD/ADD/TRIM/EXIT recommendation per position\n’
‘4. Flag 1-2 things to watch next 48 hours\n\n’
‘Use Telegram Markdown bold only. Max 350 words.\n\n’
‘*MARKET PULSE*\n’
‘[3 news items]\n\n’
‘*RECOMMENDATIONS*\n’
‘[actions per position]\n\n’
‘*WATCH*\n’
‘[things to monitor]’
)
msg = client.messages.create(
model=‘claude-sonnet-4-20250514’,
max_tokens=900,
tools=[{‘type’: ‘web_search_20250305’, ‘name’: ‘web_search’}],
messages=[{‘role’: ‘user’, ‘content’: prompt}]
)
return ‘’.join(b.text for b in msg.content if b.type == ‘text’)

def send(text):
url = ‘https://api.telegram.org/bot’ + TELEGRAM_BOT_TOKEN + ‘/sendMessage’
chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
for chunk in chunks:
requests.post(url, json={‘chat_id’: TELEGRAM_CHAT_ID, ‘text’: chunk, ‘parse_mode’: ‘Markdown’}, timeout=15)
time.sleep(0.5)

def run():
tz = pytz.timezone(TIMEZONE)
now = datetime.now(tz).strftime(’%d %b %Y %H:%M’)
print(‘Starting update ’ + now)
fx = fetch_fx()
prices, prev = fetch_prices(PORTFOLIO)
report, total_val, total_pct = build_report(PORTFOLIO, prices, prev, fx)
print(‘Getting AI analysis…’)
ai = get_ai(report, total_val, total_pct)
msg = ‘PORTFOLIO BRIEF\n’ + now + ’ SGT\n––––––––––\n\nHOLDINGS\n’ + report + ‘\n\n’ + ai
send(msg)
print(‘Done!’)

if name == ‘**main**’:
run()
schedule.every().day.at(str(SEND_HOUR).zfill(2) + ‘:’ + str(SEND_MINUTE).zfill(2)).do(run)
while True:
schedule.run_pending()
time.sleep(30)
