import numpy as np

# Break of Structure (BoS)
def detect_bos(df):
    if len(df) < 3:
        return None
    prev_high = df['high'].iloc[-3]
    last_high = df['high'].iloc[-2]
    current_high = df['high'].iloc[-1]
    if current_high > last_high > prev_high:
        return "BOS_UP"
    prev_low = df['low'].iloc[-3]
    last_low = df['low'].iloc[-2]
    current_low = df['low'].iloc[-1]
    if current_low < last_low < prev_low:
        return "BOS_DOWN"
    return None

# Order Block (просте визначення — остання свічка перед BOS)
def detect_order_block(df, bos_signal):
    if not bos_signal:
        return None
    if bos_signal == "BOS_UP":
        return df.iloc[-2].to_dict()  # свічка перед пробоєм
    if bos_signal == "BOS_DOWN":
        return df.iloc[-2].to_dict()
    return None

# Трейд-сигнал
def generate_signal(df):
    bos = detect_bos(df)
    ob = detect_order_block(df, bos)
    if bos == "BOS_UP":
        return "LONG", ob
    elif bos == "BOS_DOWN":
        return "SHORT", ob
    else:
        return "NO TRADE", None
