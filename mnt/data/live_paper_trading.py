import ccxt
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime
import csv
import os

# -------------------------------
# Налаштування
# -------------------------------
with open("config.json", "r") as f:
    config = json.load(f)

exchange = getattr(ccxt, config['exchange'])()
symbol = config.get("symbol", "BTC/USDT")
timeframe = "15m"
lookback_total = 1000
poll_interval = 60

# Параметри стратегії (вибрані з тюнінгу)
long_rsi = 45
short_rsi = 55
sl_pct = 0.5
tp_ratio = 2
risk = 0.03

# CSV файл для логів
csv_file = "paper_trades_log.csv"
if not os.path.exists(csv_file):
    with open(csv_file, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['entry_time','position','entry','exit','pnl','balance_after'])

# -------------------------------
# Функція RSI
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

# -------------------------------
# Paper trading логіка
# -------------------------------
balance = 1000.0
position = None
entry_price = None
stop_loss = None
take_profit = None
trades = []
wins = 0

print("Live paper trading запущено. Ctrl+C щоб зупинити.")

while True:
    try:
        # Завантажуємо останні свічки
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=lookback_total)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['RSI'] = RSI(df['close'], 14)
        row = df.iloc[-1]
        close = row['close']
        rsi = row['RSI']

        # Генеруємо сигнал
        signal = None
        if position is None:
            if rsi < long_rsi:
                signal = "LONG"
            elif rsi > short_rsi:
                signal = "SHORT"

            if signal:
                position = signal
                entry_price = close
                risk_amount = balance * risk
                if position == "LONG":
                    stop_loss = entry_price * (1 - sl_pct/100)
                    take_profit = entry_price * (1 + sl_pct/100 * tp_ratio)
                else:
                    stop_loss = entry_price * (1 + sl_pct/100)
                    take_profit = entry_price * (1 - sl_pct/100 * tp_ratio)
                trades.append({
                    'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'position': position,
                    'entry': entry_price
                })
                print(f"{datetime.now()} | New trade: {position} at {entry_price:.2f}")

        # Перевірка SL/TP
        if position is not None:
            exit_price = None
            pnl = 0
            exit_trade = False

            if position == "LONG":
                if row['low'] <= stop_loss:
                    pnl = -risk_amount
                    balance += pnl
                    exit_price = stop_loss
                    exit_trade = True
                    print(f"{datetime.now()} | LONG hit SL: {stop_loss:.2f}, PnL: {pnl:.2f}, Balance: {balance:.2f}")
                elif row['high'] >= take_profit:
                    pnl = risk_amount * tp_ratio
                    balance += pnl
                    exit_price = take_profit
                    exit_trade = True
                    wins += 1
                    print(f"{datetime.now()} | LONG hit TP: {take_profit:.2f}, PnL: {pnl:.2f}, Balance: {balance:.2f}")
            elif position == "SHORT":
                if row['high'] >= stop_loss:
                    pnl = -risk_amount
                    balance += pnl
                    exit_price = stop_loss
                    exit_trade = True
                    print(f"{datetime.now()} | SHORT hit SL: {stop_loss:.2f}, PnL: {pnl:.2f}, Balance: {balance:.2f}")
                elif row['low'] <= take_profit:
                    pnl = risk_amount * tp_ratio
                    balance += pnl
                    exit_price = take_profit
                    exit_trade = True
                    wins += 1
                    print(f"{datetime.now()} | SHORT hit TP: {take_profit:.2f}, PnL: {pnl:.2f}, Balance: {balance:.2f}")

            if exit_trade:
                trades[-1].update({'exit': exit_price, 'pnl': pnl, 'balance_after': balance})
                # Записуємо в CSV
                with open(csv_file, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        trades[-1]['entry_time'],
                        trades[-1]['position'],
                        trades[-1]['entry'],
                        trades[-1]['exit'],
                        trades[-1]['pnl'],
                        trades[-1]['balance_after']
                    ])
                position = None

        # Вивід поточної статистики
        total_trades = len(trades)
        winrate = (wins / total_trades * 100) if total_trades>0 else 0
        print(f"Balance: {balance:.2f} | Total Trades: {total_trades} | Wins: {wins} | Winrate: {winrate:.2f}%")

        time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\nЗупинка ботa вручну.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
