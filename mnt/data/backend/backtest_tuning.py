import ccxt
import pandas as pd
import numpy as np
import json
from itertools import product
import time

# -------------------------------
# Налаштування
# -------------------------------
with open("config.json", "r") as f:
    config = json.load(f)

exchange = getattr(ccxt, config['exchange'])()
symbol = config.get("symbol", "BTC/USDT")
timeframe = "15m"
lookback_total = 10000
limit_per_request = 1000  # Binance обмежує ~1000 свічок за раз

# -------------------------------
# Завантажуємо історичні дані 10 000 свічок
# -------------------------------
all_ohlcv = []
since = None

while len(all_ohlcv) < lookback_total:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit_per_request, since=since)
    if not ohlcv:
        break
    all_ohlcv.extend(ohlcv)
    since = ohlcv[-1][0] + 1
    time.sleep(0.2)

# обрізаємо до точного lookback_total
all_ohlcv = all_ohlcv[-lookback_total:]

df = pd.DataFrame(all_ohlcv, columns=['timestamp','open','high','low','close','volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

# -------------------------------
# Індикатор RSI
# -------------------------------
def RSI(series, period=14):
    delta = series.diff()
    gain = np.where(delta>0, delta, 0)
    loss = np.where(delta<0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

df['RSI'] = RSI(df['close'], 14)

# -------------------------------
# Функція бектесту
# -------------------------------
def run_backtest(df, long_rsi, short_rsi, sl_pct, tp_ratio, risk):
    balance = 1000.0
    position = None
    entry_price = None
    stop_loss = None
    take_profit = None
    trades = []
    wins = 0

    for i in range(14, len(df)):
        row = df.iloc[i]
        close = row['close']
        rsi = row['RSI']

        # Сигнал
        signal = None
        if rsi < long_rsi:
            signal = "LONG"
        elif rsi > short_rsi:
            signal = "SHORT"

        # Вхід
        if position is None and signal is not None:
            position = signal
            entry_price = close
            risk_amount = balance * risk
            if position == "LONG":
                stop_loss = entry_price * (1 - sl_pct/100)
                take_profit = entry_price * (1 + sl_pct/100 * tp_ratio)
            else:
                stop_loss = entry_price * (1 + sl_pct/100)
                take_profit = entry_price * (1 - sl_pct/100 * tp_ratio)
            trades.append({'position': position, 'entry': entry_price})

        # Вихід по SL/TP
        if position is not None:
            if position == "LONG":
                if row['low'] <= stop_loss:
                    pnl = -risk_amount
                    balance += pnl
                    trades[-1].update({'exit': stop_loss, 'pnl': pnl})
                    position = None
                elif row['high'] >= take_profit:
                    pnl = risk_amount * tp_ratio
                    balance += pnl
                    trades[-1].update({'exit': take_profit, 'pnl': pnl})
                    position = None
                    wins += 1
            elif position == "SHORT":
                if row['high'] >= stop_loss:
                    pnl = -risk_amount
                    balance += pnl
                    trades[-1].update({'exit': stop_loss, 'pnl': pnl})
                    position = None
                elif row['low'] <= take_profit:
                    pnl = risk_amount * tp_ratio
                    balance += pnl
                    trades[-1].update({'exit': take_profit, 'pnl': pnl})
                    position = None
                    wins += 1

    total_trades = len(trades)
    winrate = (wins / total_trades * 100) if total_trades>0 else 0
    return balance, total_trades, winrate

# -------------------------------
# Параметри для перебору
# -------------------------------
long_rsi_list = [35, 40, 45, 50]
short_rsi_list = [50, 55, 60, 65]
sl_list = [0.5, 1.0, 1.5]
tp_ratio_list = [2, 3]
risk_list = [0.01, 0.02, 0.03]

results = []

# -------------------------------
# Перебір усіх комбінацій
# -------------------------------
for long_rsi, short_rsi, sl_pct, tp_ratio, risk in product(long_rsi_list, short_rsi_list, sl_list, tp_ratio_list, risk_list):
    final_balance, trades_count, winrate = run_backtest(df, long_rsi, short_rsi, sl_pct, tp_ratio, risk)
    results.append({
        'long_rsi': long_rsi,
        'short_rsi': short_rsi,
        'sl_pct': sl_pct,
        'tp_ratio': tp_ratio,
        'risk': risk,
        'final_balance': final_balance,
        'trades': trades_count,
        'winrate': winrate
    })

# -------------------------------
# Вивід топ-5 результатів
# -------------------------------
results_sorted = sorted(results, key=lambda x: x['final_balance'], reverse=True)
print("\nTop 5 parameter sets:")
for r in results_sorted[:5]:
    print(r)
