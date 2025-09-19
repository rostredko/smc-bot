import ccxt
import json
from utils import ohlcv_to_df
from smc_logic import generate_signal

# Завантажуємо конфіг
with open("config.json", "r") as f:
    config = json.load(f)

exchange = getattr(ccxt, config['exchange'])()

symbol = config.get("symbol", "BTC/USDT")
timeframe = config.get("timeframe", "1h")
lookback = int(config.get("lookback", 200))

# Тягнемо історію
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=lookback)
df = ohlcv_to_df(ohlcv)

# -----------------------------
# Paper trading логіка
# -----------------------------

balance = 1000  # стартовий баланс у USDT
position = None
entry_price = None

for i in range(50, len(df)):  # починаємо з 50-ї свічки, щоб був контекст
    sub_df = df.iloc[:i]
    signal, ob = generate_signal(sub_df)

    price = sub_df['close'].iloc[-1]

    if signal == "LONG" and position is None:
        position = "LONG"
        entry_price = price
        print(f"[{sub_df['timestamp'].iloc[-1]}] Open LONG @ {price}")

    elif signal == "SHORT" and position is None:
        position = "SHORT"
        entry_price = price
        print(f"[{sub_df['timestamp'].iloc[-1]}] Open SHORT @ {price}")

    elif signal == "NO TRADE" and position is not None:
        # закриваємо позицію на ціні close
        if position == "LONG":
            profit = price - entry_price
        else:
            profit = entry_price - price
        balance += profit
        print(f"[{sub_df['timestamp'].iloc[-1]}] Close {position} @ {price} | PnL: {profit:.2f}, Balance: {balance:.2f}")
        position = None
        entry_price = None

print(f"\nFinal Balance: {balance:.2f} USDT")
