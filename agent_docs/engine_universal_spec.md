# Спека: Универсальный Engine для smc-bot

> Версия: 1.0 — 2026-05-01  
> Статус: Черновик для реализации  
> Контекст: анализ Jesse (open source benchmark) → план улучшений engine

---

## 0. Цель и видение

**Текущее состояние:** strategies — это Python-классы, жёстко связанные с Backtrader. Чтобы добавить стратегию, нужно знать BT internals, `notify_order`, OCO, `params` tuple. Это барьер для любого пользователя без кодинга.

**Цель:** пользователь заходит на дашборд, выбирает блоки стратегии из меню, настраивает параметры ползунками, запускает бэктест. Код не нужен.

**Принцип:** стратегии — это конфигурация, engine — её исполнитель.

```
Dashboard (form builder)
    ↓ JSON config
StrategyRegistry (resolve class by type)
    ↓
StrategyAdapter (thin BT shim → declarative API)
    ↓
BaseEngine (cerebro, broker, analyzers, metrics)
```

---

## 1. Что именно изменить и зачем

### 1.1 Проблемы сейчас (технические факты из кода)

| Файл | Размер | Проблема |
|------|--------|----------|
| `strategies/bt_price_action.py` | 1342 строки | Signal/filter/SL/TP/trailing/narrative перемешаны в `next()`. Нельзя добавить стратегию не поняв BT. |
| `strategies/base_strategy.py` | 436 строк | OCO, trailing, breakeven, drawdown, funding — всё в одном базовом классе. Сложно переиспользовать. |
| `engine/bt_oco_patch.py` | — | Существует потому что BT не умеет OCO в рамках бара — патчим чужой код. |
| `engine/base_engine.py` | — | `MockLogger`, `_setup_sizers(pass)`, `_ordered_timeframes` — мёртвый код (TD-17). |
| `web-dashboard/services/strategy_runtime.py` | — | Стратегия = Python-класс. Нет схемы, нет реестра, нет UI-описания параметров. |

Jesse решил это по-другому: `should_long()` + `go_long()` — чистые методы без BT-знаний. Engine сам делает всё остальное.

### 1.2 Цель архитектуры

```
strategies/
├── base/
│   ├── declarative_strategy.py   # ← новый ABC (декларативный API)
│   ├── bt_adapter.py             # ← тонкий BT-адаптер (ВЕСЬ BT-код здесь)
│   └── trade_setup.py            # ← dataclasses: TradeSetup, StructureState, POI
├── blocks/                       # ← переиспользуемые блоки
│   ├── structure.py              # market structure (BOS/CHoCH) — уже есть market_structure.py
│   ├── patterns.py               # candlestick patterns (переезжает из bt_price_action)
│   ├── filters.py                # RSI, ADX, EMA, OTE, Space-to-Target
│   ├── exit_manager.py           # SL/TP, trailing, breakeven, partial TP
│   └── risk_manager.py           # уже есть, расширяется
├── registry.py                   # ← реестр стратегий
├── bt_price_action.py            # (рефактор → через новый ABC)
├── fvg_sweep_choch_strategy.py   # (рефактор → через новый ABC)
└── fast_test_strategy.py
```

---

## 2. Фаза 1: Strategy Schema + Registry (без переписывания логики)

Это можно сделать **не трогая существующий код стратегий**, только добавляя сверху.

### 2.1 Pydantic-схемы параметров

**Файл: `strategies/schemas.py`**

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class StructureConfig(BaseModel):
    pivot_span: int = Field(2, ge=1, le=10, title="Fractal pivot span", 
                             description="Bars on each side to confirm swing high/low")
    use_structure_filter: bool = Field(True, title="Trade with HTF bias only")

class EntryPatternConfig(BaseModel):
    pattern_hammer: bool = Field(True, title="Hammer")
    pattern_inverted_hammer: bool = Field(True, title="Inverted Hammer")
    pattern_shooting_star: bool = Field(True, title="Shooting Star")
    pattern_hanging_man: bool = Field(True, title="Hanging Man")
    pattern_bullish_engulfing: bool = Field(True, title="Bullish Engulfing")
    pattern_bearish_engulfing: bool = Field(True, title="Bearish Engulfing")

class FiltersConfig(BaseModel):
    use_rsi_filter: bool = Field(True, title="RSI Filter")
    rsi_period: int = Field(14, ge=2, le=100, title="RSI Period")
    rsi_overbought: int = Field(70, ge=50, le=99, title="RSI Overbought")
    rsi_oversold: int = Field(30, ge=1, le=50, title="RSI Oversold")
    use_adx_filter: bool = Field(True, title="ADX Filter")
    adx_period: int = Field(14, ge=2, le=100, title="ADX Period")
    adx_threshold: float = Field(30.0, ge=5.0, le=60.0, title="ADX Threshold")
    use_ema_filter: bool = Field(False, title="EMA Trend Filter")
    trend_ema_period: int = Field(200, ge=10, le=500, title="EMA Period")
    use_ote_filter: bool = Field(False, title="OTE Retracement Filter")
    ote_min_retracement: float = Field(0.62, ge=0.3, le=0.9, title="OTE Min Fib")
    ote_max_retracement: float = Field(0.79, ge=0.3, le=0.99, title="OTE Max Fib")

class RiskConfig(BaseModel):
    risk_reward_ratio: float = Field(2.0, ge=0.5, le=20.0, title="Risk/Reward Ratio")
    risk_per_trade: float = Field(1.0, ge=0.01, le=10.0, title="Risk per Trade (%)")
    leverage: float = Field(1.0, ge=1.0, le=125.0, title="Leverage")
    max_drawdown: Optional[float] = Field(50.0, ge=1.0, le=100.0, title="Max Drawdown (%)")
    trailing_stop_distance: float = Field(0.0, ge=0.0, le=10.0, title="Trailing Stop (ATR mult)")
    breakeven_trigger_r: float = Field(0.0, ge=0.0, le=5.0, title="Breakeven Trigger (R)")
    sl_buffer_atr: float = Field(1.5, ge=0.0, le=5.0, title="SL ATR Buffer")

class PriceActionStrategyConfig(BaseModel):
    """Full config for bt_price_action strategy. Dashboard renders this as a form."""
    type: Literal["price_action"] = "price_action"
    structure: StructureConfig = Field(default_factory=StructureConfig)
    entry: EntryPatternConfig = Field(default_factory=EntryPatternConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

class FVGSweepConfig(BaseModel):
    """Config for fvg_sweep_choch strategy."""
    type: Literal["fvg_sweep"] = "fvg_sweep"
    # ... аналогично
```

**Зачем:** dashboard запрашивает `GET /strategies` → получает JSON Schema из Pydantic → рендерит форму автоматически. Больше не нужно писать форму вручную для каждой стратегии.

### 2.2 Strategy Registry

**Файл: `strategies/registry.py`**

```python
from typing import Type, Dict, Any
from pydantic import BaseModel

class StrategyDefinition:
    name: str
    display_name: str
    description: str
    strategy_class: type        # Backtrader strategy class
    config_schema: Type[BaseModel]  # Pydantic schema → JSON Schema для дашборда
    default_timeframes: list[str]   # ["1h", "4h"]
    tags: list[str]                 # ["SMC", "price_action", "trend_following"]

STRATEGY_REGISTRY: Dict[str, StrategyDefinition] = {}

def register_strategy(
    name: str,
    display_name: str,
    description: str,
    strategy_class,
    config_schema: Type[BaseModel],
    default_timeframes: list[str] | None = None,
    tags: list[str] | None = None,
):
    STRATEGY_REGISTRY[name] = StrategyDefinition(
        name=name,
        display_name=display_name,
        description=description,
        strategy_class=strategy_class,
        config_schema=config_schema,
        default_timeframes=default_timeframes or ["1h", "4h"],
        tags=tags or [],
    )

def get_strategy_class(name: str):
    if name not in STRATEGY_REGISTRY:
        raise KeyError(f"Strategy '{name}' not found. Available: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name].strategy_class

def get_all_strategy_definitions() -> list[dict]:
    """Returns list of {name, display_name, description, schema, tags} for dashboard /strategies endpoint."""
    result = []
    for name, defn in STRATEGY_REGISTRY.items():
        result.append({
            "name": name,
            "display_name": defn.display_name,
            "description": defn.description,
            "schema": defn.config_schema.model_json_schema(),  # Pydantic v2
            "default_timeframes": defn.default_timeframes,
            "tags": defn.tags,
        })
    return result

# Auto-registration при импорте
def _register_defaults():
    from strategies.bt_price_action import PriceActionStrategy
    from strategies.schemas import PriceActionStrategyConfig
    
    register_strategy(
        name="price_action",
        display_name="Price Action (SMC/ICT)",
        description="HTF market structure (BOS/CHoCH) with LTF candlestick pattern execution",
        strategy_class=PriceActionStrategy,
        config_schema=PriceActionStrategyConfig,
        default_timeframes=["1h", "4h"],
        tags=["SMC", "ICT", "price_action", "BOS", "CHoCH"],
    )
    
    from strategies.fvg_sweep_choch_strategy import FVGSweepCHoCHStrategy
    from strategies.schemas import FVGSweepConfig
    register_strategy(
        name="fvg_sweep",
        display_name="FVG + Sweep + CHoCH",
        description="Fair Value Gap entry after liquidity sweep with CHoCH confirmation",
        strategy_class=FVGSweepCHoCHStrategy,
        config_schema=FVGSweepConfig,
        default_timeframes=["15m", "1h"],
        tags=["SMC", "FVG", "liquidity", "CHoCH"],
    )

_register_defaults()
```

**Интеграция в `strategy_runtime.py`:**

```python
# БЫЛО:
def resolve_strategy_class(strategy_name: str):
    # импорт по имени через importlib...

# СТАНЕТ:
from strategies.registry import get_strategy_class, get_all_strategy_definitions

def resolve_strategy_class(strategy_name: str):
    return get_strategy_class(strategy_name)

def get_strategy_definitions():
    return get_all_strategy_definitions()
```

**Интеграция в `/strategies` endpoint:**

```python
# БЫЛО: возвращало список имён + params dict
# СТАНЕТ: возвращает JSON Schema (Pydantic → UI рендерит форму автоматически)

@app.get("/strategies")
async def list_strategies():
    return get_all_strategy_definitions()
```

---

## 3. Фаза 2: Config Flattening → Backtrader params

Текущая проблема: `server.py:run_backtest_task` собирает `engine_config` dict (~35 полей) вручную. Это дублирование, мешает schema-driven подходу.

### 3.1 Config Translator

**Файл: `web-dashboard/services/runtime_config.py`** (новый, Phase 2 из TECHNICAL_DEBT_REPORT.md TD-03)

```python
from pydantic import BaseModel
from strategies.registry import STRATEGY_REGISTRY

def flatten_strategy_config_to_bt_params(strategy_name: str, strategy_config: dict) -> dict:
    """
    Converts nested JSON config (from dashboard) to flat Backtrader params dict.
    
    Input (from dashboard):
    {
        "type": "price_action",
        "structure": {"pivot_span": 2, "use_structure_filter": true},
        "filters": {"use_rsi_filter": true, "rsi_period": 14, ...},
        "risk": {"risk_reward_ratio": 2.0, ...}
    }
    
    Output (to cerebro.addstrategy):
    {
        "market_structure_pivot_span": 2,
        "use_structure_filter": True,
        "use_rsi_filter": True,
        "rsi_period": 14,
        "risk_reward_ratio": 2.0,
        ...
    }
    """
    defn = STRATEGY_REGISTRY.get(strategy_name)
    if defn is None:
        # Fallback: возвращаем как есть для обратной совместимости
        return strategy_config
    
    # Validate through Pydantic schema
    validated = defn.config_schema.model_validate(strategy_config)
    
    # Flatten nested config to BT params
    flat = {}
    for section_name, section_model in validated.model_dump().items():
        if isinstance(section_model, dict):
            flat.update(section_model)
        elif section_name != "type":
            flat[section_name] = section_model
    
    return flat

def build_engine_config(request_config: dict) -> dict:
    """
    Single canonical path: request → engine config.
    Called by both API and CLI.
    """
    strategy_name = request_config.get("strategy_name", "price_action")
    strategy_config = request_config.get("strategy_config", {})
    
    flat_strategy_params = flatten_strategy_config_to_bt_params(strategy_name, strategy_config)
    
    return {
        # Engine-level params
        "symbol": request_config.get("symbol", "BTC/USDT"),
        "exchange": request_config.get("exchange", "binance"),
        "exchange_type": request_config.get("exchange_type", "future"),
        "timeframes": request_config.get("timeframes", ["1h", "4h"]),
        "start_date": request_config.get("backtest_start"),
        "end_date": request_config.get("backtest_end"),
        "initial_capital": float(request_config.get("initial_capital", 10000)),
        "run_mode": request_config.get("run_mode", "single"),
        # Strategy params (flattened from nested schema)
        "strategy_config": flat_strategy_params,
    }
```

---

## 4. Фаза 3: Declarative Strategy ABC (Jesse-inspired)

Это основное архитектурное улучшение. Стратегия больше не знает про Backtrader.

### 4.1 Dataclasses для обмена данными

**Файл: `strategies/base/trade_setup.py`**

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass
class StructureState:
    """Market structure assessment. Produced by structure detection block."""
    bias: Literal['bullish', 'bearish', 'neutral'] = 'neutral'
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None
    active_poi: Optional[float] = None    # e.g., last broken swing level = POI
    bos_confirmed: bool = False
    choch_detected: bool = False
    ltf_choch_detected: bool = False
    poi_zone_upper: Optional[float] = None
    poi_zone_lower: Optional[float] = None


@dataclass
class TradeSetup:
    """
    Trade intent. Strategy produces this; engine executes.
    Strategy never calls self.buy() / self.sell() directly.
    """
    direction: Literal['long', 'short']
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None  # None = auto from RR ratio
    size: Optional[float] = None         # None = auto from RiskManager
    entry_type: Literal['market', 'limit', 'stop'] = 'limit'

    # Metadata for narrative and dashboard
    why_entry: list[str] = field(default_factory=list)  # ["Pattern: Hammer", "RSI=28", "ADX=35"]
    indicators_at_entry: dict = field(default_factory=dict)
    sl_calc_expr: Optional[str] = None  # "HTF swing low - 1.5×ATR"
    tp_calc_expr: Optional[str] = None  # "2.0×R"

    # Chart annotations
    annotations: list['ChartAnnotation'] = field(default_factory=list)


@dataclass
class ChartAnnotation:
    """Visual annotation attached to a TradeSetup or StructureState."""
    type: Literal['level', 'zone', 'marker', 'label']
    time: int           # unix ms
    value: float        # price
    color: str = '#ffffff'
    label: str = ''
    zone_top: Optional[float] = None
    zone_bottom: Optional[float] = None
```

### 4.2 Declarative Strategy ABC

**Файл: `strategies/base/declarative_strategy.py`**

```python
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np
from .trade_setup import TradeSetup, StructureState


class DeclarativeStrategy(ABC):
    """
    Base class for no-BT-knowledge strategies.
    Engine calls the hooks; strategy returns intents.
    
    Jesse comparison:
        Jesse: should_long() → bool, go_long() sets self.buy/sl/tp
        smc-bot: should_long() → bool, go_long() → TradeSetup (return value, no mutation)
    
    Usage example:
    
        class MyEMACross(DeclarativeStrategy):
            def should_long(self) -> bool:
                ema_fast = self.indicator("ema", period=9)
                ema_slow = self.indicator("ema", period=21)
                return ema_fast > ema_slow
            
            def go_long(self) -> TradeSetup:
                atr = self.indicator("atr")
                sl = self.close - 2 * atr
                return TradeSetup(
                    direction='long',
                    entry_price=self.close,
                    stop_loss=sl,
                    why_entry=["EMA9 > EMA21", f"ATR={atr:.2f}"],
                )
            
            def filters(self) -> list:
                return [
                    lambda: self.indicator("adx") > 25,
                    lambda: self.indicator("rsi") < 65,
                ]
    """

    # --- State injected by BTAdapter before each bar ---
    close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    volume: float = 0.0
    bar_index: int = 0
    timestamp: int = 0            # unix ms
    candles: Optional[np.ndarray] = None       # [time, open, high, low, close, volume]
    htf_candles: Optional[np.ndarray] = None   # HTF candles if multi-timeframe

    # Injected context
    account_value: float = 0.0
    position_size: float = 0.0   # 0 = flat
    position_direction: Optional[str] = None  # 'long' | 'short' | None

    # Injected config (populated from StrategyConfig schema)
    config: dict = {}

    # --- Hooks (abstract) ---

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self) -> TradeSetup:
        raise NotImplementedError("Override go_long() to define entry setup")

    def go_short(self) -> TradeSetup:
        raise NotImplementedError("Override go_short() to define entry setup")

    def should_cancel_entry(self) -> bool:
        """Return True to cancel a pending entry order."""
        return False

    def on_open_position(self, trade_id: int, setup: TradeSetup) -> None:
        """Called right after position opens. Override for custom logic."""

    def on_close_position(self, trade_id: int, result: dict) -> None:
        """Called right after position closes. Override for custom logic."""

    def on_tp_update(self, trade_id: int) -> Optional[float]:
        """Return new TP price to modify take profit, or None to keep current."""
        return None

    def on_sl_update(self, trade_id: int) -> Optional[float]:
        """Return new SL price to modify stop loss (trailing), or None to keep."""
        return None

    # --- Filter pipeline ---

    def filters(self) -> list:
        """
        Return list of callables → all must return True to enter.
        
        Example:
            def filters(self):
                return [
                    lambda: self.indicator("adx") > self.config.get("adx_threshold", 25),
                    lambda: self.indicator("rsi") < self.config.get("rsi_overbought", 70),
                ]
        """
        return []

    def _execute_filters(self) -> bool:
        return all(f() for f in self.filters())

    # --- Indicator access helper ---

    def indicator(self, name: str, **kwargs) -> float:
        """
        Access pre-computed indicator value.
        Indicators are computed by BTAdapter from candles numpy array.
        
        Supported: 'ema', 'rsi', 'adx', 'atr', 'macd', 'bb', 'stoch'
        
        Example:
            rsi = self.indicator("rsi", period=14)
            ema200 = self.indicator("ema", period=200)
            atr = self.indicator("atr")  # default period=14
        """
        return self._indicator_cache.get((name, tuple(sorted(kwargs.items()))), float('nan'))

    # --- Hyperparameters (for optimize mode, Jesse-style) ---

    def hyperparameters(self) -> list:
        """
        Define parameters for optimization.
        
        Example:
            def hyperparameters(self):
                return [
                    {"name": "rsi_period", "type": int, "min": 7, "max": 21, "default": 14},
                    {"name": "risk_reward_ratio", "type": float, "min": 1.0, "max": 4.0, "default": 2.0},
                ]
        """
        return []

    # --- Internal state (managed by BTAdapter) ---
    _indicator_cache: dict = {}
```

### 4.3 Backtrader Adapter

**Файл: `strategies/base/bt_adapter.py`**

Это тонкая обёртка. ВЕСЬ Backtrader-специфичный код живёт здесь. Стратегии на DeclarativeStrategy не знают, что под ними BT.

```python
import backtrader as bt
import talib
import numpy as np
from typing import Optional
from engine.logger import get_logger
from engine.trade_narrator import TradeNarrator
from strategies.helpers.risk_manager import RiskManager
from .declarative_strategy import DeclarativeStrategy
from .trade_setup import TradeSetup, StructureState

logger = get_logger(__name__)


class BTStrategyAdapter(bt.Strategy):
    """
    Backtrader strategy shim that delegates to a DeclarativeStrategy instance.
    Handles all BT internals: params, notify_order, notify_trade, OCO, trailing, breakeven.
    
    User strategy classes inherit DeclarativeStrategy, NOT this class.
    This adapter wraps them at runtime.
    """
    params = (
        # Risk params (always present)
        ('risk_reward_ratio', 2.0),
        ('risk_per_trade', 1.0),
        ('leverage', 1.0),
        ('max_drawdown', None),
        ('trailing_stop_distance', 0.0),
        ('breakeven_trigger_r', 0.0),
        ('sl_buffer_atr', 1.5),
        # Additional params come from strategy_config dict
        ('strategy_config', {}),
    )

    def __init__(self):
        super().__init__()
        # Instantiate the declarative strategy
        self._strategy = self._create_strategy_instance()
        self._strategy.config = dict(self.params.strategy_config or {})

        # Order state (hidden from user strategy)
        self._entry_order = None
        self._stop_order = None
        self._tp_order = None
        self._pending_setup: Optional[TradeSetup] = None
        self._trade_map = {}
        self._next_trade_id = 1
        self._equity_peak = self.broker.startingcash
        self._dd_limit_hit = False
        self._oco_closed = False
        self._entry_exec_bar = -1
        self._narrator = TradeNarrator(self.params.risk_reward_ratio)

    def _create_strategy_instance(self) -> DeclarativeStrategy:
        """
        Subclasses override this to return the concrete DeclarativeStrategy.
        
        Example adapter class generated by registry:
            class PriceActionAdapter(BTStrategyAdapter):
                def _create_strategy_instance(self):
                    return PriceActionLogic()
        """
        raise NotImplementedError

    def _inject_state(self):
        """Inject current bar state into the declarative strategy."""
        s = self._strategy
        s.close = float(self.data.close[0])
        s.high = float(self.data.high[0])
        s.low = float(self.data.low[0])
        s.open = float(self.data.open[0])
        s.volume = float(self.data.volume[0]) if hasattr(self.data, 'volume') else 0.0
        s.bar_index = len(self.data)
        s.account_value = self.broker.getvalue()
        s.position_size = abs(float(self.position.size)) if self.position else 0.0
        s.position_direction = (
            'long' if self.position.size > 0
            else 'short' if self.position.size < 0
            else None
        )
        # Build candles numpy array (last N bars)
        n = min(300, len(self.data))
        if n > 0:
            times = [self.data.datetime.datetime(-i).timestamp() * 1000 for i in range(n - 1, -1, -1)]
            s.candles = np.array([
                [times[i],
                 float(self.data.open[-n + 1 + i]),
                 float(self.data.high[-n + 1 + i]),
                 float(self.data.low[-n + 1 + i]),
                 float(self.data.close[-n + 1 + i]),
                 float(self.data.volume[-n + 1 + i]) if hasattr(self.data, 'volume') else 0.0]
                for i in range(n)
            ])
        # Populate indicator cache
        self._populate_indicator_cache(s)

    def _populate_indicator_cache(self, s: DeclarativeStrategy):
        """Pre-compute indicators needed by strategy."""
        if s.candles is None or len(s.candles) < 2:
            return
        closes = s.candles[:, 4].astype(float)
        highs = s.candles[:, 2].astype(float)
        lows = s.candles[:, 3].astype(float)

        cache = {}
        # Common indicators (talib)
        for period in [9, 14, 20, 21, 50, 200]:
            if len(closes) >= period:
                ema = talib.EMA(closes, timeperiod=period)
                cache[('ema', (('period', period),))] = float(ema[-1])
        if len(closes) >= 14:
            cache[('rsi', (('period', 14),))] = float(talib.RSI(closes, timeperiod=14)[-1])
            atr = talib.ATR(highs, lows, closes, timeperiod=14)
            cache[('atr', ())] = float(atr[-1])
            cache[('atr', (('period', 14),))] = float(atr[-1])
        if len(closes) >= 14:
            adx = talib.ADX(highs, lows, closes, timeperiod=14)
            cache[('adx', ())] = float(adx[-1])
            cache[('adx', (('period', 14),))] = float(adx[-1])
        s._indicator_cache = cache

    def next(self):
        if self._dd_limit_hit:
            return

        self._inject_state()
        self._update_equity_peak()

        # No position: check for entry
        if not self.position:
            self._oco_closed = False
            setup = None

            if self._strategy.should_long() and self._strategy._execute_filters():
                setup = self._strategy.go_long()
            elif self._strategy.should_short() and self._strategy._execute_filters():
                setup = self._strategy.go_short()

            if setup is not None:
                self._submit_entry(setup)
            return

        # In position: check trailing/breakeven
        self._update_exits()

    def _submit_entry(self, setup: TradeSetup):
        """Convert TradeSetup → Backtrader orders."""
        size = setup.size
        if size is None:
            size = RiskManager.calculate_position_size(
                account_value=self.broker.getvalue(),
                risk_per_trade_pct=self.params.risk_per_trade,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                leverage=self.params.leverage,
                dynamic_sizing=True,
                max_drawdown_pct=self.params.max_drawdown,
            )
        if size <= 0:
            return

        self._pending_setup = setup

        if setup.direction == 'long':
            if setup.entry_type == 'market':
                self._entry_order = self.buy(size=size)
            elif setup.entry_type == 'limit':
                self._entry_order = self.buy(price=setup.entry_price, exectype=bt.Order.Limit, size=size)
            else:
                self._entry_order = self.buy(price=setup.entry_price, exectype=bt.Order.Stop, size=size)
        else:
            if setup.entry_type == 'market':
                self._entry_order = self.sell(size=size)
            elif setup.entry_type == 'limit':
                self._entry_order = self.sell(price=setup.entry_price, exectype=bt.Order.Limit, size=size)
            else:
                self._entry_order = self.sell(price=setup.entry_price, exectype=bt.Order.Stop, size=size)

    def _place_bracket(self, exec_price: float, size: float, setup: TradeSetup):
        """Place SL + TP (OCO) after entry fill."""
        sl = setup.stop_loss
        tp = setup.take_profit
        if tp is None:
            sl_dist = abs(exec_price - sl)
            tp = exec_price + sl_dist * self.params.risk_reward_ratio if setup.direction == 'long' \
                else exec_price - sl_dist * self.params.risk_reward_ratio

        if setup.direction == 'long':
            self._stop_order = self.sell(price=sl, exectype=bt.Order.Stop, size=size)
            self._tp_order = self.sell(price=tp, exectype=bt.Order.Limit, size=size, oco=self._stop_order)
        else:
            self._stop_order = self.buy(price=sl, exectype=bt.Order.Stop, size=size)
            self._tp_order = self.buy(price=tp, exectype=bt.Order.Limit, size=size, oco=self._stop_order)

    def _update_exits(self):
        """Handle trailing stop and breakeven updates."""
        if self._stop_order is None or not self._stop_order.alive():
            return
        if self._entry_exec_bar < 0 or len(self.data) == self._entry_exec_bar:
            return  # Don't update on entry bar

        new_sl = self._strategy.on_sl_update(0)
        if new_sl is not None and new_sl != self._stop_order.price:
            self.cancel(self._stop_order)
            size = abs(self.position.size)
            direction = 'long' if self.position.size > 0 else 'short'
            if direction == 'long':
                self._stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=size)
                if self._tp_order and self._tp_order.alive():
                    self._tp_order = self.sell(
                        price=self._tp_order.price, exectype=bt.Order.Limit,
                        size=size, oco=self._stop_order
                    )
            else:
                self._stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=size)
                if self._tp_order and self._tp_order.alive():
                    self._tp_order = self.buy(
                        price=self._tp_order.price, exectype=bt.Order.Limit,
                        size=size, oco=self._stop_order
                    )

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if order == self._entry_order:
                self._entry_order = None
                size = abs(order.executed.size)
                self._place_bracket(order.executed.price, size, self._pending_setup)
                self._entry_exec_bar = len(self.data)
                return

            if self._stop_order and order.ref == self._stop_order.ref:
                if self._tp_order:
                    self.cancel(self._tp_order)
                    self._tp_order = None
                self._stop_order = None
                self._oco_closed = True

            elif self._tp_order and order.ref == self._tp_order.ref:
                if self._stop_order:
                    self.cancel(self._stop_order)
                    self._stop_order = None
                self._tp_order = None
                self._oco_closed = True

        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            if order == self._entry_order:
                self._entry_order = None
            elif order == self._stop_order:
                self._stop_order = None
            elif order == self._tp_order:
                self._tp_order = None

    def notify_trade(self, trade):
        if trade.justopened:
            if self._pending_setup:
                self._trade_map[trade.ref] = {
                    "setup": self._pending_setup,
                    "size": abs(trade.size),
                }
                self._strategy.on_open_position(self._next_trade_id, self._pending_setup)
                self._pending_setup = None
        elif trade.isclosed:
            stored = self._trade_map.get(trade.ref, {})
            result = {
                "pnl": trade.pnl,
                "pnl_comm": trade.pnlcomm,
                "setup": stored.get("setup"),
            }
            self._strategy.on_close_position(self._next_trade_id, result)
            self._next_trade_id += 1
            self._check_drawdown_after_trade()

    def _update_equity_peak(self):
        self._equity_peak = max(self._equity_peak, self.broker.getvalue())

    def _check_drawdown_after_trade(self):
        max_dd = self.params.max_drawdown
        if not max_dd or max_dd <= 0:
            return
        current = self.broker.getvalue()
        if self._equity_peak <= 0:
            return
        dd_pct = 100.0 * (self._equity_peak - current) / self._equity_peak
        if dd_pct > max_dd and not self._dd_limit_hit:
            self._dd_limit_hit = True
            try:
                self.cerebro.runstop()
            except Exception:
                pass
```

---

## 5. Фаза 4: Реализация стратегии через новый API

Демонстрирует что пишет разработчик стратегии после внедрения ABC.

### 5.1 Пример: EMA Cross (новая стратегия, ~40 строк)

```python
# strategies/ema_cross.py

from strategies.base.declarative_strategy import DeclarativeStrategy
from strategies.base.trade_setup import TradeSetup

class EMACrossStrategy(DeclarativeStrategy):
    """Simple EMA crossover strategy. Demonstrates minimal strategy implementation."""

    def should_long(self) -> bool:
        ema_fast = self.indicator("ema", period=self.config.get("fast_ema", 9))
        ema_slow = self.indicator("ema", period=self.config.get("slow_ema", 21))
        return ema_fast > ema_slow

    def should_short(self) -> bool:
        ema_fast = self.indicator("ema", period=self.config.get("fast_ema", 9))
        ema_slow = self.indicator("ema", period=self.config.get("slow_ema", 21))
        return ema_fast < ema_slow

    def go_long(self) -> TradeSetup:
        atr = self.indicator("atr")
        sl = self.close - self.config.get("sl_buffer_atr", 1.5) * atr
        return TradeSetup(
            direction='long',
            entry_price=self.close,
            stop_loss=sl,
            entry_type='market',
            why_entry=[f"EMA{self.config.get('fast_ema', 9)} > EMA{self.config.get('slow_ema', 21)}"],
        )

    def go_short(self) -> TradeSetup:
        atr = self.indicator("atr")
        sl = self.close + self.config.get("sl_buffer_atr", 1.5) * atr
        return TradeSetup(
            direction='short',
            entry_price=self.close,
            stop_loss=sl,
            entry_type='market',
            why_entry=[f"EMA{self.config.get('fast_ema', 9)} < EMA{self.config.get('slow_ema', 21)}"],
        )

    def filters(self) -> list:
        return [
            lambda: self.indicator("adx") > self.config.get("adx_threshold", 20),
        ]

    def hyperparameters(self) -> list:
        return [
            {"name": "fast_ema", "type": int, "min": 5, "max": 20, "default": 9},
            {"name": "slow_ema", "type": int, "min": 15, "max": 100, "default": 21},
            {"name": "risk_reward_ratio", "type": float, "min": 1.0, "max": 4.0, "default": 2.0},
        ]
```

Зарегистрировать:
```python
# В registry.py
register_strategy(
    name="ema_cross",
    display_name="EMA Crossover",
    description="Fast EMA crosses above/below slow EMA",
    strategy_class=EMACrossAdapterClass,  # BTStrategyAdapter subclass auto-generated
    config_schema=EMACrossConfig,
    default_timeframes=["1h"],
    tags=["trend_following", "simple"],
)
```

### 5.2 Пример: рефактор PriceAction через новый API

**До (bt_price_action.py, ~1342 строки):** логика размазана по `next()`, `notify_order()`, хелперам.

**После (~200 строк логики + adapter ~50 строк):**

```python
# strategies/price_action_logic.py

from strategies.base.declarative_strategy import DeclarativeStrategy
from strategies.base.trade_setup import TradeSetup, StructureState
from strategies.blocks.structure import detect_structure
from strategies.blocks.patterns import detect_ltf_pattern
from strategies.blocks.filters import check_rsi, check_adx, check_ema_trend

class PriceActionLogic(DeclarativeStrategy):
    """
    HTF structure + LTF pattern execution (SMC/ICT approach).
    Thin: delegates detection to reusable blocks.
    """

    def __init__(self):
        self._structure: StructureState = StructureState()
        self._active_pattern = None
        self._choch_armed = False
        self._choch_arm_bar = 0

    def _refresh_structure(self):
        """Recompute structure state from HTF candles."""
        if self.htf_candles is not None:
            self._structure = detect_structure(
                self.htf_candles,
                pivot_span=self.config.get("market_structure_pivot_span", 2)
            )

    def should_long(self) -> bool:
        self._refresh_structure()
        if not self.config.get("use_structure_filter", True):
            return self._check_ltf_entry('long')
        return self._structure.bias == 'bullish' and self._check_ltf_entry('long')

    def should_short(self) -> bool:
        self._refresh_structure()
        if not self.config.get("use_structure_filter", True):
            return self._check_ltf_entry('short')
        return self._structure.bias == 'bearish' and self._check_ltf_entry('short')

    def _check_ltf_entry(self, direction: str) -> bool:
        pattern = detect_ltf_pattern(self.candles, direction, self.config)
        if pattern is None:
            return False
        self._active_pattern = pattern
        return True

    def go_long(self) -> TradeSetup:
        atr = self.indicator("atr")
        sl = self._resolve_structural_sl('long', atr)
        return TradeSetup(
            direction='long',
            entry_price=self.close,
            stop_loss=sl,
            entry_type='limit',
            why_entry=[f"Pattern: {self._active_pattern}", f"Structure: bullish BOS"],
            indicators_at_entry={
                "RSI": round(self.indicator("rsi"), 1),
                "ADX": round(self.indicator("adx"), 1),
                "ATR": round(atr, 4),
            },
            sl_calc_expr=f"HTF swing low - {self.config.get('sl_buffer_atr', 1.5)}×ATR",
        )

    def go_short(self) -> TradeSetup:
        atr = self.indicator("atr")
        sl = self._resolve_structural_sl('short', atr)
        return TradeSetup(
            direction='short',
            entry_price=self.close,
            stop_loss=sl,
            entry_type='limit',
            why_entry=[f"Pattern: {self._active_pattern}", f"Structure: bearish BOS"],
            sl_calc_expr=f"HTF swing high + {self.config.get('sl_buffer_atr', 1.5)}×ATR",
        )

    def _resolve_structural_sl(self, direction: str, atr: float) -> float:
        buf = self.config.get("sl_buffer_atr", 1.5) * atr
        if direction == 'long' and self._structure.last_swing_low:
            return self._structure.last_swing_low - buf
        elif direction == 'short' and self._structure.last_swing_high:
            return self._structure.last_swing_high + buf
        # Fallback: fixed ATR buffer from close
        return (self.close - 2 * atr) if direction == 'long' else (self.close + 2 * atr)

    def filters(self) -> list:
        return [
            lambda: not self.config.get("use_rsi_filter", True) or check_rsi(
                self.indicator("rsi"), self.config, direction='long' if self.position_direction is None else self.position_direction
            ),
            lambda: not self.config.get("use_adx_filter", True) or check_adx(
                self.indicator("adx"), self.config
            ),
            lambda: not self.config.get("use_ema_filter", False) or check_ema_trend(
                self.close, self.indicator("ema", period=self.config.get("trend_ema_period", 200)), self.config
            ),
        ]

    def on_sl_update(self, trade_id: int):
        """Trailing stop logic — delegated from BTAdapter."""
        trail_dist = self.config.get("trailing_stop_distance", 0.0)
        if trail_dist <= 0:
            return None
        atr = self.indicator("atr")
        direction = self.position_direction
        if direction == 'long':
            new_sl = self.close - trail_dist * atr
            return new_sl  # BTAdapter only updates if higher than current SL
        elif direction == 'short':
            new_sl = self.close + trail_dist * atr
            return new_sl  # BTAdapter only updates if lower than current SL
        return None
```

---

## 6. Фаза 5: Dashboard интеграция — Strategy Builder UI

### 6.1 Как работает форма стратегии

**Текущий поток:**
```
Dashboard хардкодит форму для каждой стратегии → brittle, нужно обновлять форму при каждом добавлении параметра
```

**Целевой поток:**
```
GET /strategies → {name, display_name, schema: JSONSchema}
     ↓
Dashboard рендерит форму из JSON Schema (react-jsonschema-form / custom renderer)
     ↓
POST /backtest/start {strategy_name: "price_action", strategy_config: {...}}
```

### 6.2 JSON Schema → UI mapping

```json
// GET /strategies response (auto-generated from Pydantic)
{
  "name": "price_action",
  "display_name": "Price Action (SMC/ICT)",
  "schema": {
    "type": "object",
    "title": "Price Action Strategy",
    "properties": {
      "structure": {
        "type": "object",
        "title": "Structure & POI",
        "properties": {
          "pivot_span": {
            "type": "integer",
            "title": "Fractal Pivot Span",
            "minimum": 1, "maximum": 10, "default": 2,
            "description": "Bars on each side to confirm swing high/low"
          }
        }
      },
      "filters": {
        "type": "object",
        "title": "Entry Filters",
        "properties": {
          "use_rsi_filter": {"type": "boolean", "title": "RSI Filter", "default": true},
          "rsi_period": {"type": "integer", "title": "RSI Period", "minimum": 2, "maximum": 100}
          // ...
        }
      }
    }
  }
}
```

Dashboard читает `schema.properties` → рендерит секции как accordions → поля с `type: integer` + `minimum/maximum` → слайдеры; `type: boolean` → toggle; etc.

**Для добавления новой стратегии:** только `register_strategy(...)` + создать Pydantic schema. Форма генерируется автоматически.

### 6.3 Новая стратегия за 3 шага

```
1. Создать класс в strategies/ (наследует DeclarativeStrategy, ~50-200 строк логики)
2. Создать Pydantic schema в strategies/schemas.py (~30 строк)
3. register_strategy(...) в strategies/registry.py (5 строк)
```

Dashboard немедленно показывает новую стратегию с корректной формой.

---

## 7. Что остаётся неизменным (backward compatibility)

| Компонент | Статус |
|-----------|--------|
| `engine/bt_backtest_engine.py` | Без изменений |
| `engine/bt_live_engine.py` | Без изменений |
| `engine/bt_oco_patch.py` | Без изменений (адаптер использует его) |
| `engine/data_loader.py` | Без изменений |
| `engine/bt_analyzers.py` | Без изменений |
| `engine/trade_metrics.py` | Без изменений |
| `strategies/market_structure.py` | Без изменений (переиспользуется в blocks/) |
| `strategies/helpers/risk_manager.py` | Без изменений |
| `db/`, `web-dashboard/api/` | Без изменений |
| `bt_price_action.py` (старый) | Продолжает работать параллельно до полного рефактора |

**Переходный период:** старые стратегии (прямые `bt.Strategy` подклассы) продолжают работать через существующий `strategy_runtime.py`. Новые стратегии (через `DeclarativeStrategy` + `BTStrategyAdapter`) регистрируются в реестре и доступны параллельно.

---

## 8. Порядок реализации

### Sprint 1 (2-3 дня): Schema + Registry
- [ ] Создать `strategies/schemas.py` с Pydantic-схемами для `price_action` и `fvg_sweep`
- [ ] Создать `strategies/registry.py` с `STRATEGY_REGISTRY` и `register_strategy`
- [ ] Обновить `strategy_runtime.py` — делегировать в registry
- [ ] Обновить `/strategies` endpoint — возвращать JSON Schema
- [ ] Тесты: `test_strategy_registry.py` (register, lookup, schema output)

### Sprint 2 (3-4 дня): Config Flattening + Translator
- [ ] Создать `web-dashboard/services/runtime_config.py` (TD-03 из TECHNICAL_DEBT_REPORT)
- [ ] `flatten_strategy_config_to_bt_params` — nested config → flat BT params
- [ ] `build_engine_config` — один путь для API и CLI
- [ ] Тесты: `test_runtime_config_translation.py` (parity API/CLI, validation)
- [ ] Убрать inline `engine_config` dict из `run_backtest_task` в `server.py`

### Sprint 3 (4-5 дней): DeclarativeStrategy ABC + BTAdapter
- [ ] Создать `strategies/base/trade_setup.py` (dataclasses)
- [ ] Создать `strategies/base/declarative_strategy.py` (ABC)
- [ ] Создать `strategies/base/bt_adapter.py` (BT shim)
- [ ] Тесты: `test_bt_adapter.py` — adapter + minimal declarative strategy + BT cerebro (integration)
- [ ] Тесты: `test_declarative_strategy.py` — unit tests для логики без BT

### Sprint 4 (3-4 дня): Strategy Blocks
- [ ] Создать `strategies/blocks/filters.py` (check_rsi, check_adx, check_ema_trend)
- [ ] Создать `strategies/blocks/patterns.py` (detect_ltf_pattern — из bt_price_action)
- [ ] Тесты для каждого блока (pure functions, легко тестировать)
- [ ] Регистрация `ema_cross` как примера новой стратегии

### Sprint 5 (5-7 дней): Рефактор bt_price_action
- [ ] Создать `strategies/price_action_logic.py` (DeclarativeStrategy)
- [ ] Adapter class для registry
- [ ] Параллельный прогон: старый vs новый (должны давать одинаковый результат)
- [ ] Тест `test_price_action_parity.py` — backtest на одинаковых данных = одинаковые результаты
- [ ] После parity test pass — убрать старый `bt_price_action.py`

### Sprint 6 (2-3 дня): Dashboard form generation
- [ ] Обновить frontend: читать `schema` из `/strategies` response
- [ ] Рендерить форму из JSON Schema (секции → accordions, поля → input/slider/toggle)
- [ ] Тесты: frontend unit тесты для новой формы

---

## 9. Критические тесты для каждой фазы

```python
# Sprint 1
def test_registry_returns_json_schema_for_price_action():
    defs = get_all_strategy_definitions()
    pa = next(d for d in defs if d["name"] == "price_action")
    assert "schema" in pa
    assert pa["schema"]["type"] == "object"
    assert "structure" in pa["schema"]["properties"]

# Sprint 2
def test_config_translation_api_cli_parity():
    api_config = {"strategy_config": {"structure": {"pivot_span": 3}}}
    cli_config = {"market_structure_pivot_span": 3}
    api_flat = flatten_strategy_config_to_bt_params("price_action", api_config["strategy_config"])
    assert api_flat["market_structure_pivot_span"] == cli_config["market_structure_pivot_span"]

# Sprint 3
def test_bt_adapter_executes_declarative_strategy():
    class AlwaysLong(DeclarativeStrategy):
        def should_long(self): return True
        def go_long(self):
            return TradeSetup(direction='long', entry_price=100.0, stop_loss=95.0, entry_type='market')
    
    # Run with adapter in BT cerebro on synthetic data → expect at least 1 trade

# Sprint 5
def test_price_action_parity_old_vs_new():
    """Backtest on same fixed data: old class = new class, same trade count and PnL."""
    old_results = run_backtest_with_class(PriceActionStrategy, config)
    new_results = run_backtest_with_class(NewPriceActionAdapterClass, config)
    assert old_results["total_trades"] == new_results["total_trades"]
    assert abs(old_results["total_pnl"] - new_results["total_pnl"]) < 0.01
```

---

## 10. Итог: что даёт эта архитектура

| Было | Станет |
|------|--------|
| Стратегия = Python-класс с BT-знанием | Стратегия = декларативная логика (should_long, go_long) |
| Добавить стратегию = написать 500-1000 строк | Добавить стратегию = ~100 строк логики + schema + регистрация |
| Dashboard форма = хардкод на каждую стратегию | Dashboard форма = auto-генерация из JSON Schema |
| Нет типизации params | Pydantic schema = валидация + docs + UI |
| OCO/trailing в каждой стратегии | OCO/trailing один раз в BTAdapter |
| Тестировать = запускать BT cerebro | Тестировать логику = pure function test |
| Jesse: пользователь пишет код | smc-bot: пользователь выбирает блоки на дашборде |
