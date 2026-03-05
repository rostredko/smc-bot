export interface BacktestSummary {
    filename: string;
    timestamp: string;
    total_pnl: number;
    initial_capital: number;
    win_rate: number;
    max_drawdown: number;
    total_trades: number;
    profit_factor: number;
    sharpe_ratio?: number;
    avg_win?: number;
    avg_loss?: number;
    winning_trades?: number;
    losing_trades?: number;
    strategy: string;
    is_live?: boolean;
    configuration: any;
    loaded_template_name?: string | null;
    risk_per_trade?: number;
    adx_threshold?: string | number;
    rsi_momentum_threshold?: string | number;
    // Live trading session timing
    session_start?: string;
    session_end?: string;
    session_duration_mins?: number;
}
