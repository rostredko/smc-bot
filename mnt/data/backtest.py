import ccxt
import pandas as pd
import numpy as np
import json

# -------------------------------
# Налаштування
# -------------------------------
with open("config.json", "r") as f:
    config = json.load(f)

exchange = getattr(ccxt, config['exchange'])()
symbol = config.get("symbol", "BTC/USDT")
timeframe = "15m"  # швидший таймфрейм
lookback = 2000

# -------------------------------
# Підтягуємо історичні дані
# -------------------------------
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=lookback)
df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

# -------------------------------
# Додаткові індикатори
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
# Логіка бота
# -------------------------------
balance = 1000.0
risk_per_trade = 0.02
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

    # Сигнал (тільки RSI)
    signal = None
    if rsi < 50:
        signal = "LONG"
    elif rsi > 50:
        signal = "SHORT"

    # Вхід
    if position is None and signal is not None:
        position = signal
        entry_price = close
        risk_amount = balance * risk_per_trade
        # TP / SL
        if position == "LONG":
            stop_loss = entry_price * (1 - 0.01)
            take_profit = entry_price * (1 + 0.03)
        else:
            stop_loss = entry_price * (1 + 0.01)
            take_profit = entry_price * (1 - 0.03)
        trades.append({'entry_time': row['timestamp'], 'position': position, 'entry': entry_price})

    # Вихід по SL/TP
    if position is not None:
        if position == "LONG":
            if row['low'] <= stop_loss:
                pnl = -risk_amount
                balance += pnl
                trades[-1].update({'exit_time': row['timestamp'], 'exit': stop_loss, 'pnl': pnl})
                position = None
            elif row['high'] >= take_profit:
                pnl = risk_amount * 3
                balance += pnl
                trades[-1].update({'exit_time': row['timestamp'], 'exit': take_profit, 'pnl': pnl})
                position = None
                wins += 1
        elif position == "SHORT":
            if row['high'] >= stop_loss:
                pnl = -risk_amount
                balance += pnl
                trades[-1].update({'exit_time': row['timestamp'], 'exit': stop_loss, 'pnl': pnl})
                position = None
            elif row['low'] <= take_profit:
                pnl = risk_amount * 3
                balance += pnl
                trades[-1].update({'exit_time': row['timestamp'], 'exit': take_profit, 'pnl': pnl})
                position = None
                wins += 1

# -------------------------------
# Результат
# -------------------------------
total_trades = len(trades)
winrate = (wins / total_trades * 100) if total_trades>0 else 0

print(f"Final Balance: {balance:.2f} USDT")
print(f"Total Trades: {total_trades}, Wins: {wins}, Winrate: {winrate:.2f}%")
print("\nTrades details:")
for t in trades:
    exit_price = t.get('exit')
    pnl = t.get('pnl', 0)
    exit_str = f"{exit_price:.2f}" if isinstance(exit_price, (int, float)) else "N/A"
    pnl_str = f"{pnl:.2f}" if isinstance(pnl, (int, float)) else "0.00"
    print(f"{t['entry_time']} | {t['position']} | Entry: {t['entry']:.2f} | Exit: {exit_str} | PnL: {pnl_str}")