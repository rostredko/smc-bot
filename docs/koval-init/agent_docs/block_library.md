# Block Library — Koval

Reference for available blocks, their types, params, and how to add new ones.

## Block categories

| Category | Purpose | File |
|----------|---------|------|
| `signal` | Detect market conditions (BOS, pattern, cross) | `koval/blocks/signals/` |
| `filter` | Confirm entry conditions (RSI, ADX, trend) | `koval/blocks/filters/` |
| `entry` | Define entry direction and type | Assembled by block_assembler |
| `exit` | Define TP/SL/trailing logic | `koval/blocks/exits/` |
| `risk` | Position sizing | `koval/blocks/risk/` |

## Block function interface

All block functions are pure:
```python
def check_<name>(value_or_candles, config: dict) -> bool | float
```

No state, no BT imports, no side effects. Takes data in, returns result.

## Available blocks

### Signals

| Block type | Function | Params |
|-----------|----------|--------|
| `signal.bos_detected` | `smc.detect_bos(candles, config)` | `pivot_span: int = 2` |
| `signal.choch_detected` | `smc.detect_choch(candles, config)` | `pivot_span: int = 2` |
| `signal.fvg_present` | `smc.detect_fvg(candles, config)` | `min_gap_atr: float = 0.5` |
| `signal.hammer` | `candlesticks.detect_hammer(candles, config)` | `body_ratio: float = 0.3` |
| `signal.engulfing` | `candlesticks.detect_engulfing(candles, config)` | — |
| `signal.shooting_star` | `candlesticks.detect_shooting_star(candles, config)` | — |
| `signal.ema_cross` | `technical.detect_ema_cross(candles, config)` | `fast: int = 9, slow: int = 21` |

### Filters

| Block type | Function | Params |
|-----------|----------|--------|
| `filter.rsi` | `momentum.check_rsi(rsi, config)` | `period: int = 14, min: float = 0, max: float = 100` |
| `filter.adx` | `trend.check_adx(adx, config)` | `period: int = 14, min: float = 25` |
| `filter.ema_trend` | `trend.check_ema_trend(close, ema, config)` | `period: int = 200` |
| `filter.atr_volatility` | `volatility.check_atr(atr, config)` | `min_atr: float = 0` |

### Exits

| Block type | Function | Params |
|-----------|----------|--------|
| `exit.fixed_tp` | `fixed.calculate_tp(entry, sl, config)` | `rr: float = 2.0` |
| `exit.atr_sl` | `fixed.calculate_atr_sl(close, atr, config)` | `atr_mult: float = 1.5` |
| `exit.trailing_sl` | `trailing.calculate_trailing_sl(close, atr, config)` | `atr_mult: float = 2.0` |
| `exit.breakeven` | `breakeven.should_move_to_be(entry, close, sl, config)` | `trigger_r: float = 1.0` |

### Risk

| Block type | Function | Params |
|-----------|----------|--------|
| `risk.pct_risk` | `position_sizer.calculate_position_size(...)` | `risk_pct: float = 1.0, leverage: float = 1.0` |

## How to add a new block

1. **Write the pure function** in the appropriate `koval/blocks/` file:
```python
# koval/blocks/signals/technical.py
def detect_macd_cross(candles: np.ndarray, config: dict) -> bool:
    """Returns True when MACD line crosses above signal line."""
    ...
```

2. **Write tests first** in `tests/blocks/`:
```python
def test_detect_macd_cross_bullish():
    candles = _make_candles(prices=[...])
    assert detect_macd_cross(candles, {"fast": 12, "slow": 26, "signal": 9}) is True
```

3. **Register in the block catalog** in `koval/strategy/registry.py`:
```python
BLOCK_CATALOG["signal.macd_cross"] = BlockDefinition(
    type="signal.macd_cross",
    category="signal",
    display_name="MACD Cross",
    description="MACD line crosses above/below signal line",
    function=detect_macd_cross,
    params_schema=MACDCrossParams,  # Pydantic model
)
```

4. **Docs update:** Add to this table above.

The block will appear automatically in the Block Builder palette and be available in JSON block graphs.
