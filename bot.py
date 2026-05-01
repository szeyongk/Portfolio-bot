import os,anthropic,yfinance as yf,requests,schedule,time,pytz
from datetime import datetime

KEY=os.environ.get(chr(65)+chr(78)+chr(84)+chr(72)+chr(82)+chr(79)+chr(80)+chr(73)+chr(67)+chr(95)+chr(65)+chr(80)+chr(73)+chr(95)+chr(75)+chr(69)+chr(89))
BOT=os.environ.get(chr(84)+chr(69)+chr(76)+chr(69)+chr(71)+chr(82)+chr(65)+chr(77)+chr(95)+chr(66)+chr(79)+chr(84)+chr(95)+chr(84)+chr(79)+chr(75)+chr(69)+chr(78))
CID=os.environ.get(chr(84)+chr(69)+chr(76)+chr(69)+chr(71)+chr(82)+chr(65)+chr(77)+chr(95)+chr(67)+chr(72)+chr(65)+chr(84)+chr(95)+chr(73)+chr(68))
