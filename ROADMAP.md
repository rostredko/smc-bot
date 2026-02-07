# SMC Trading Bot - Project Roadmap

## 1. Current State (As of Feb 2026)

The project is a **specialized backtesting & research platform** designed for validating Smart Money Concepts (SMC) and Price Action strategies using the `backtesting.py` library.

**Note**: This branch/project is strictly for **backtesting and simulation**. The core library (`backtesting.py`) is optimized for statistical analysis and does not support live trading. Live execution will be handled in a separate project/branch.

- **Core Engine**: A wrapper around `backtesting.py` for high-performance simulation.
- **Frontend**: React-based dashboard for deep-dive analysis of strategy performance.
- **Strategies**:
    - **Production**: `PriceActionStrategy` (Verified).
    - **Analysis**: `MarketStructureAnalyzer`, `OrderBlockDetector`.
- **Infrastructure**: Local execution with file-based caching.

## 2. Architecture Overview

We follow a modular research-oriented architecture:

1.  **Domain/Strategy Layer**: Pure logic for pattern recognition and signal generation.
2.  **Simulation Layer**: Uses `backtesting.py` to simulate market mechanics (orders, liquidity, spreads).
3.  **Analysis Layer**: Aggregates results, calculates advanced metrics (Sharpe, Sortino, Drawdown ranges).
4.  **Interface Layer**: Web dashboard for visualization and parameter tuning.

## 3. Roadmap

### Phase 1: Stabilization & Visualization (Current)
- [x] **Core Engine Reliability**: Robust backtesting with `PriceActionStrategy`.
- [ ] **Dashboard Enhancement**:
    - Fix UI freezing issues (large datasets).
    - Improve log visualization and chart interactivity.
    - Persist configurations.
- [ ] **Documentation**: Maintain up-to-date `PROJECT_STRUCTURE.md`.

### Phase 2: Advanced Analytics & Optimization (Next)
- [ ] **Deep Dive Metrics**: Add heatmaps, monthly breakdown, and trade duration analysis.
- [ ] **Walk-Forward Optimization**: Automated parameter tuning to avoid overfitting.
- [ ] **Multi-Timeframe Debugging**: visual overlay of HTF bias vs LTF entries.
- [ ] **Export Tools**: Generate comprehensive PDF/HTML reports for strategy validation.

### Phase 3: Research Expansion (Future)
- [ ] **Multi-Exchange Data**: easy import of data from various sources (CSV, other APIs).
- [ ] **Machine Learning Integration**: Feature engineering playground for signal filtering.
- [ ] **Strategy Portfolio**: Simulating multiple strategies running in parallel (paper-mode style).

## 4. Final Goal

To build an **institutional-grade research laboratory** that allows us to:
1.  Mathematically prove the edge of SMC/Price Action strategies.
2.  Optimize parameters with high confidence using robust statistical methods.
3.  Generate "Production-Ready" strategy logic that can be ported to a live execution engine.
