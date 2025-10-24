# SMC Trading Engine - Complete Guide

A production-ready Python backtesting framework for Smart Money Concepts (SMC) spot crypto trading strategies with Binance integration, comprehensive risk management, web dashboard, and automated testing.

**Status**: ✅ Production Ready | **Tests**: 88 passed | **Coverage**: 95%+ critical components

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Platform-Specific Setup](#platform-specific-setup)
3. [Usage Modes](#usage-modes)
4. [Web Dashboard](#web-dashboard)
5. [Configuration](#configuration)
6. [Strategies](#strategies)
7. [Development](#development)
8. [Testing](#testing)
9. [Command Reference](#command-reference)

---

## Quick Start

### Prerequisites

- **Python**: 3.8+ (check with `python --version`)
- **Node.js**: 16+ (for web dashboard only)
- **npm**: 8+ (for web dashboard only)

### Basic Installation (All Platforms)

```bash
# 1. Clone and navigate
git clone <repository-url>
cd smc-bot

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# ⚠️ See "Platform-Specific Setup" for your OS
```

---

## Platform-Specific Setup

### 🐧 Linux / macOS (Unix-like)

#### Initial Setup

```bash
# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
pip install -r deps/requirements.txt

# (Optional) For web dashboard
cd web-dashboard
pip install -r requirements.txt
npm install
npm run build
cd ..
```

#### Running Backtest (CLI)

```bash
# Default config
python main.py backtest

# Custom config
python main.py backtest config/my_config.json
```

#### Running Web Dashboard

```bash
# Terminal 1: Run backend
cd web-dashboard
python server.py

# Terminal 2 (new terminal): Optional - run frontend in dev mode
cd web-dashboard
npm run dev
# OR skip this if you already ran npm run build

# Open browser: http://localhost:8000
```

#### Running Tests

```bash
# All tests
python main.py test

# Specific test file
pytest tests/test_strategies.py -v

# With coverage
pytest tests/ --cov=engine --cov=strategies
```

#### Cleanup / Restart

```bash
# Kill port 8000 if stuck
lsof -ti:8000 | xargs kill -9

# Kill all Python processes
pkill -f "python.*server.py"
```

---

### 🪟 Windows

#### Initial Setup

```batch
REM Activate virtual environment
venv\Scripts\activate

REM Install Python dependencies
pip install -r deps\requirements.txt

REM (Optional) For web dashboard
cd web-dashboard
pip install -r requirements.txt
npm install
npm run build
cd ..
```

#### Running Backtest (CLI)

```batch
REM Default config
python main.py backtest

REM Custom config
python main.py backtest config\my_config.json
```

#### Running Web Dashboard

```batch
REM Terminal 1: Run backend
cd web-dashboard
python server.py

REM Terminal 2 (new terminal): Optional - run frontend in dev mode
cd web-dashboard
npm run dev
REM OR skip this if you already ran npm run build

REM Open browser: http://localhost:8000
```

#### Running Tests

```batch
REM All tests
python main.py test

REM Specific test file
pytest tests\test_strategies.py -v

REM With coverage
pytest tests\ --cov=engine --cov=strategies
```

#### Cleanup / Restart

```batch
REM Kill port 8000 if stuck
netstat -ano | findstr :8000
taskkill /PID <PID> /F

REM Kill all Python processes
taskkill /F /IM python.exe
```

---

## Usage Modes

### 1. Backtesting with CLI

Fast backtesting from command line without UI.

```bash
# Linux/macOS
source venv/bin/activate
python main.py backtest config/config.json

# Windows
venv\Scripts\activate
python main.py backtest config\config.json
```

**Advantages**:
- ✅ No UI overhead, pure speed
- ✅ Easy to run on servers/headless systems
- ✅ Perfect for automation and batch testing
- ✅ Good for parameter sweeping

**Output**: Results saved to `results/backtest_TIMESTAMP.json`

---

### 2. Web Dashboard

Interactive UI for backtesting and parameter tuning.

#### Prerequisites

```bash
# Linux/macOS
source venv/bin/activate
cd web-dashboard
pip install -r requirements.txt
npm install

# Windows
venv\Scripts\activate
cd web-dashboard
pip install -r requirements.txt
npm install
```

#### Startup

```bash
# Build frontend (one time or after changes)
npm run build

# Start backend + frontend
# Linux/macOS
python server.py

# Windows
python server.py

# Open: http://localhost:8000
```

#### Features

- 🎯 **Visual Strategy Selection** - Choose from available strategies
- ⚙️ **Parameter Editor** - Adjust all settings in UI
- 📊 **Live Console Output** - See logs in real-time via WebSocket
- 📈 **Interactive Charts** - Equity curve, trade distribution, analysis
- 🎨 **Modern UI** - Beautiful Material-UI design
- ⏹️ **Stop Button** - Cancel backtest mid-run and get intermediate results
- 💾 **Auto-Save Results** - JSON export to `results/` directory

#### Live Console Output

The dashboard shows strategy output in real-time as it executes:

```
[backtest_20251024_123456] ============================================================
[backtest_20251024_123456] BACKTEST CONFIGURATION
[backtest_20251024_123456] ============================================================
[backtest_20251024_123456] Strategy: smc_strategy
[backtest_20251024_123456] Symbol: BTC/USDT
[backtest_20251024_123456] Loading data...
[backtest_20251024_123456] ✅ Data loaded
[backtest_20251024_123456] Running backtest...
[backtest_20251024_123456] SIGNAL GENERATED: LONG @ $50,000
[backtest_20251024_123456] Backtest completed successfully
```

**Status Indicator**: 🟢 Connected / 🔴 Disconnected (top-right corner)

---

### 3. Live Trading

Paper trading (sandbox) or real money trading on Binance.

```bash
# Linux/macOS
source venv/bin/activate
python main.py live --sandbox

# Windows
venv\Scripts\activate
python main.py live --sandbox
```

⚠️ **Warning**: Only use real money after extensive testing in sandbox mode!

---

## Web Dashboard

### Architecture

```
Frontend (React + TypeScript)
    ↓ HTTP/REST
Backend (FastAPI)
    ↓ WebSocket (live logs)
    ↓ Python Engine
Backtest Results
```

### File Structure

```
web-dashboard/
├── server.py                  # FastAPI backend
├── requirements.txt          # Python dependencies
├── package.json             # Node.js dependencies
├── src/
│   ├── App.tsx             # Main React component
│   └── index.css           # Styles
├── dist/                    # Built React app
└── README.md               # Dashboard docs
```

### API Endpoints

```
GET  /                           - Web dashboard
GET  /strategies                 - List available strategies
GET  /config                     - Get current config
POST /config                     - Update config
POST /backtest/start             - Start backtest
GET  /backtest/status/{run_id}  - Get status
DELETE /backtest/{run_id}        - Cancel backtest
GET  /backtest/results/{run_id} - Get results
WebSocket /ws                    - Live console output
```

### Results File

After each backtest, results are saved to `results/{run_id}.json`:

```json
{
  "total_pnl": 5000.0,
  "win_rate": 65.0,
  "profit_factor": 2.14,
  "max_drawdown": 12.5,
  "sharpe_ratio": 1.5,
  "total_trades": 100,
  "trades": [...],
  "equity_curve": [...],
  "logs": [...]
}
```

---

## Configuration

### Main Config (`config/config.json`)

```json
{
  "name": "SMC Spot Trading",
  "account": {
    "initial_capital": 10000,
    "risk_per_trade": 0.5,
    "max_drawdown": 15.0,
    "max_positions": 1
  },
  "trading": {
    "symbol": "BTC/USDT",
    "timeframes": ["4h", "15m"],
    "exchange": "binance"
  },
  "period": {
    "start_date": "2025-09-01",
    "end_date": "2025-10-20"
  },
  "strategy": {
    "name": "smc_strategy"
  }
}
```

### Key Parameters

| Parameter | Description | Default |
|-----------|---|---|
| `initial_capital` | Starting balance | 10000 |
| `risk_per_trade` | Max risk per trade (%) | 0.5 |
| `max_drawdown` | Stop trading if drawdown exceeds (%) | 15.0 |
| `symbol` | Trading pair | BTC/USDT |
| `timeframes` | Supported timeframes | ["4h", "15m"] |
| `start_date` | Backtest start date | - |
| `end_date` | Backtest end date | - |
| `strategy.name` | Strategy to use | smc_strategy |

---

## Strategies

### Available Strategies

#### SMCStrategy
**File**: `strategies/smc_strategy.py`

Features:
- Multi-timeframe analysis (4H bias, 15m entries)
- Order block detection with strength rating
- Fair value gap analysis
- Adaptive stop loss calculation
- Dynamic position sizing
- Trailing stop management

**Best For**: Experienced SMC traders

#### SimpleTestStrategy
**File**: `strategies/simple_test_strategy.py`

Features:
- Simple moving average crossover
- Fixed interval signals
- Basic risk management

**Best For**: Engine testing and validation

### Creating Your Strategy

```python
# strategies/my_strategy.py
from strategies.base_strategy import StrategyBase

class MyStrategy(StrategyBase):
    def generate_signals(self, market_data):
        signals = []
        
        low_df = market_data.get('15m')
        if low_df is None or len(low_df) < 2:
            return signals
        
        current_price = low_df['close'].iloc[-1]
        avg_price = low_df['close'].mean()
        
        if current_price > avg_price * 1.05:
            signals.append({
                'direction': 'LONG',
                'entry_price': current_price,
                'stop_loss': current_price * 0.98,
                'take_profit': current_price * 1.05,
                'reason': 'Price above 5% average',
                'confidence': 0.6
            })
        
        return signals
```

Then update `config/config.json`:
```json
{
  "strategy": {
    "name": "my_strategy"
  }
}
```

---

## Development

### Project Structure

```
smc-bot/
├── engine/                      # Core system 🔒
│   ├── backtest_engine.py      # Main orchestrator
│   ├── risk_manager.py         # Risk management
│   ├── position.py             # Trade objects
│   ├── logger.py               # Logging
│   ├── metrics.py              # Performance metrics
│   ├── data_loader.py          # Binance data
│   ├── smc_analysis.py         # SMC tools
│   └── live_trading.py         # Live trading
│
├── strategies/                  # Custom strategies ✏️
│   ├── base_strategy.py        # Abstract base
│   ├── smc_strategy.py         # SMC implementation
│   └── simple_test_strategy.py # Test strategy
│
├── config/                      # Configuration ✏️
│   ├── config.json             # Main config
│   └── live_trading_config.json
│
├── web-dashboard/              # Web UI
│   ├── server.py               # FastAPI backend
│   ├── src/App.tsx             # React frontend
│   └── dist/                   # Built app
│
├── tests/                       # Test suite
├── data_cache/                 # Cached market data
├── results/                    # Backtest results
├── main.py                     # CLI entry point
└── README.md                   # This file
```

### Core Philosophy

```
STABLE CORE (engine/)     → DO NOT MODIFY 🔒
        ↓
STRATEGY LAYER            → MODIFY HERE ✏️
        ↓
CONFIGURATION (JSON)      → TUNE HERE ✏️
        ↓
OUTPUT (Results)
```

**Rule 1**: Only modify:
- `strategies/` - Your trading logic
- `config/` - Parameters
- `tests/` - Your tests

**Rule 2**: Never modify:
- `engine/` - Core system
- `main.py` - Entry point
- `strategies/base_strategy.py` - Interface

---

## Testing

### Run Tests

```bash
# Linux/macOS
source venv/bin/activate
python main.py test

# Windows
venv\Scripts\activate
python main.py test
```

### Run Specific Tests

```bash
# All tests
pytest tests/ -v

# Only strategies
pytest tests/test_strategies.py -v

# With coverage
pytest tests/ --cov=engine --cov=strategies --cov-report=html
```

### Writing Tests

```python
# tests/test_strategies.py
import pytest
from strategies.my_strategy import MyStrategy

class TestMyStrategy:
    def test_generates_signals(self, sample_ohlcv_data):
        strategy = MyStrategy()
        signals = strategy.generate_signals({'15m': sample_ohlcv_data})
        
        assert isinstance(signals, list)
        for signal in signals:
            assert 'direction' in signal
            assert signal['direction'] in ['LONG', 'SHORT']
```

---

## Command Reference

### Linux / macOS

```bash
# Setup
source venv/bin/activate
pip install -r deps/requirements.txt

# Backtesting
python main.py backtest                    # Default config
python main.py backtest config/my.json     # Custom config

# Web Dashboard
cd web-dashboard
npm run build                              # Build frontend
python server.py                           # Start server

# Testing
python main.py test                        # All tests
pytest tests/test_strategies.py -v         # Specific tests

# Live Trading
python main.py live --sandbox              # Paper trading
python main.py live                        # Real money ⚠️
```

### Windows

```batch
REM Setup
venv\Scripts\activate
pip install -r deps\requirements.txt

REM Backtesting
python main.py backtest                    REM Default config
python main.py backtest config\my.json     REM Custom config

REM Web Dashboard
cd web-dashboard
npm run build                              REM Build frontend
python server.py                           REM Start server

REM Testing
python main.py test                        REM All tests
pytest tests\test_strategies.py -v         REM Specific tests

REM Live Trading
python main.py live --sandbox              REM Paper trading
python main.py live                        REM Real money ⚠️
```

---

## Performance Metrics

| Metric | Description |
|--------|---|
| **Win Rate** | % of profitable trades |
| **Profit Factor** | Gross profit / Gross loss |
| **Total PnL** | Net profit or loss |
| **Max Drawdown** | Largest peak-to-trough decline |
| **Sharpe Ratio** | Risk-adjusted return |
| **Average Win** | Mean profit per winning trade |
| **Average Loss** | Mean loss per losing trade |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError | Run `pip install -r deps/requirements.txt` |
| Port 8000 in use | Linux: `lsof -ti:8000 \| xargs kill -9` or Windows: `taskkill /F /IM python.exe` |
| Strategy not generating signals | Check strategy logic, add debug prints |
| No trades executed | Review signal validation, check RiskManager settings |
| Tests failing | Run `pytest tests/ -v` for detailed output |
| High drawdown | Reduce `risk_per_trade` in config |

---

## Risk Management

1. **Never risk more than 0.5%** per trade
2. **Always use stop losses** - no exceptions
3. **Maximum drawdown limit** - stops trading if exceeded
4. **Daily loss limit** - stops trading if daily loss exceeds limit
5. **Max consecutive losses** - stops after N consecutive losses

### Before Live Trading

- [ ] Win rate > 50% and Sharpe ratio > 0
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Tested in sandbox mode for at least 1 week
- [ ] Stop losses and take profits properly set
- [ ] Risk per trade set conservatively (0.5%)
- [ ] Maximum drawdown limit enabled
- [ ] Monitoring setup in place

---

## Key Design Principles

1. **Separation of Concerns** - Each component has single responsibility
2. **Open/Closed Principle** - Open for extension (strategies), closed for modification (core)
3. **Test Driven** - Core components thoroughly tested
4. **Configuration Over Code** - Behavior controlled via JSON
5. **No External Dependencies in Core** - Easy to understand and maintain

---

## Next Steps

1. Run a backtest: `python main.py backtest`
2. Check results: Open `results/backtest_TIMESTAMP.json`
3. Try web dashboard: `cd web-dashboard && npm run build && python server.py`
4. Create your strategy: Implement in `strategies/my_strategy.py`
5. Run tests: `pytest tests/ -v`
6. Test live (sandbox): `python main.py live --sandbox`

---

## Disclaimer

This software is for educational and research purposes only. Trading cryptocurrencies involves substantial risk of loss. Always do your own research and consider your risk tolerance before trading. Live trading warning: Never trade with real money until thoroughly tested in sandbox mode.

---

**Last Updated**: October 24, 2025  
**Status**: ✅ Production Ready  
**Python**: 3.8+  
**Tests**: 88 passed