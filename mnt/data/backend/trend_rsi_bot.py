import ccxt
import pandas as pd
import time
import datetime
import numpy as np

# ==== CONFIG ====
symbol = "BTC/USDT"
timeframe = "5m"
risk_per_trade = 0.02  # 2% від балансу
sl_pct = 0.01  # 1%
tp_ratio = 4   # 1 до 4 (тобто 4% TP)
balance = 1000.0
trades = []
open_position = None

exchange = ccxt.binance({"enableRateLimit": True})

def fetch_data():
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=500)
    df = pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df

def compute_indicators(df):
    df["rsi"] = compute_rsi(df["close"], 14)
    df["ema200"] = df["close"].ewm(span=200).mean()
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def check_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Тільки по тренду
    if last["close"] > last["ema200"]:
        # LONG: перетин RSI знизу вверх
        if prev["rsi"] < 45 and last["rsi"] >= 45:
            return "LONG"
    elif last["close"] < last["ema200"]:
        # SHORT: перетин RSI зверху вниз
        if prev["rsi"] > 55 and last["rsi"] <= 55:
            return "SHORT"
    return None

def paper_trade(signal, price):
    global balance, open_position, trades

    if open_position is None and signal in ["LONG","SHORT"]:
        risk_amount = balance * risk_per_trade
        qty = risk_amount / (sl_pct * price)
        sl = price * (1 - sl_pct) if signal == "LONG" else price * (1 + sl_pct)
        tp = price * (1 + tp_ratio*sl_pct) if signal == "LONG" else price * (1 - tp_ratio*sl_pct)

        open_position = {
            "side": signal,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "qty": qty
        }
        print(f"📈 OPEN {signal} at {price:.2f}, SL={sl:.2f}, TP={tp:.2f}, QTY={qty:.4f}")

    elif open_position is not None:
        if open_position["side"] == "LONG":
            if price <= open_position["sl"]:
                pnl = -risk_amount
                balance += pnl
                print(f"❌ LONG SL HIT at {price:.2f}, Balance={balance:.2f}")
                trades.append(pnl)
                open_position = None
            elif price >= open_position["tp"]:
                pnl = risk_amount * tp_ratio
                balance += pnl
                print(f"✅ LONG TP HIT at {price:.2f}, Balance={balance:.2f}")
                trades.append(pnl)
                open_position = None

        elif open_position["side"] == "SHORT":
            if price >= open_position["sl"]:
                pnl = -risk_amount
                balance += pnl
                print(f"❌ SHORT SL HIT at {price:.2f}, Balance={balance:.2f}")
                trades.append(pnl)
                open_position = None
            elif price <= open_position["tp"]:
                pnl = risk_amount * tp_ratio
                balance += pnl
                print(f"✅ SHORT TP HIT at {price:.2f}, Balance={balance:.2f}")
                trades.append(pnl)
                open_position = None

def main():
    global balance
    while True:
        df = fetch_data()
        df = compute_indicators(df)
        signal = check_signal(df)
        price = df.iloc[-1]["close"]

        paper_trade(signal, price)

        winrate = (sum(1 for t in trades if t > 0) / len(trades) * 100) if trades else 0
        print(f"Balance: {balance:.2f} | Trades: {len(trades)} | Winrate: {winrate:.2f}%")

        time.sleep(10)  # для тесту оновлюємо кожні 10 сек (в реалі треба 300 сек = 5 хв)

if __name__ == "__main__":
    main()
