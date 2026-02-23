export interface Strategy {
    name: string;
    display_name: string;
    description: string;
    config_schema: Record<string, any>;
}

export interface BacktestConfig {
    initial_capital: number;
    risk_per_trade: number;
    max_drawdown: number;
    max_positions: number;
    leverage: number;
    symbol: string;
    timeframes: string[];
    start_date: string;
    end_date: string;
    strategy: string;
    strategy_config: Record<string, any>;
    trailing_stop_distance: number;
    breakeven_trigger_r: number;
    dynamic_position_sizing: boolean;
}

export interface BacktestStatus {
    run_id: string;
    status: string;
    progress: number;
    message: string;
    results?: any;
    error?: string;
}

export interface BacktestResults {
    total_pnl: number;
    win_rate: number;
    profit_factor: number;
    max_drawdown: number;
    sharpe_ratio: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    avg_win: number;
    avg_loss: number;
    signals_generated: number;
    initial_capital: number;
    equity_curve: Array<{ date: string, equity: number }>;
    trades: Array<any>;
    /** Backtest configuration (symbol, timeframes, etc.) */
    configuration?: Record<string, any>;
}

/** A single OHLCV candlestick bar, as returned by /api/ohlcv */
export interface OHLCVCandle {
    time: string;   // ISO-8601 datetime string (UTC)
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}



export const DEFAULT_CONFIG: BacktestConfig = {
    initial_capital: 10000,
    risk_per_trade: 1.5,
    max_drawdown: 30.0,
    max_positions: 1,
    leverage: 10.0,
    symbol: "BTC/USDT",
    timeframes: ["4h", "1h"],
    start_date: "2025-01-01",
    end_date: "2025-12-31",
    strategy: "",
    strategy_config: {},
    trailing_stop_distance: 0.04,
    breakeven_trigger_r: 1.5,
    dynamic_position_sizing: true
};
