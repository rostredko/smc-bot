import ccxt
import json
from utils import ohlcv_to_df
from smc_logic import generate_signal

# Завантажуємо конфіг
with open("config.json", "r") as f:
    config = json.load(f)

# Публічний доступ — без ключів
exchange = getattr(ccxt, config['exchange'])()

symbol = config.get("symbol", "BTC/USDT")
timeframe = config.get("timeframe", "1h")
lookback = int(config.get("lookback", 200))

# Тягнемо історію
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=lookback)
df = ohlcv_to_df(ohlcv)

# Генеруємо сигнал
signal, ob = generate_signal(df)
print(f"Signal: {signal}")
if ob:
    print(f"Order Block candle: {ob}")
