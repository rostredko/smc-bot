
import React, { useEffect, useState } from 'react';
import {
    Box,
    Card,
    CardHeader,
    CardContent,
    Typography,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    IconButton,
    Collapse
} from '@mui/material';
import {
    KeyboardArrowDown,
    KeyboardArrowUp,
    History
} from '@mui/icons-material';

interface BacktestSummary {
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
    configuration: any; // Using any for flexibility with nested config
    risk_per_trade?: number; // Keep for backward compatibility if needed, though we use config now
    adx_threshold?: string | number;
    rsi_momentum_threshold?: string | number;
}

const API_BASE = "http://localhost:8000";

// General Settings mapping (based on dashboard form + JSON structure)
const GENERAL_SETTINGS = [
    { label: "Initial Capital", key: "initial_capital", format: (v: any) => `$${v}` },
    { label: "Risk Per Trade", key: "risk_per_trade", suffix: "%" },
    { label: "Max Drawdown", key: "max_drawdown", suffix: "%" },
    { label: "Leverage", key: "leverage", suffix: "x" },
    { label: "Symbol", key: "symbol" },
    { label: "Start Date", key: "start_date" },
    { label: "End Date", key: "end_date" },
    { label: "Trailing Stop Dist", key: "trailing_stop_distance" },
    { label: "Breakeven Trigger", key: "breakeven_trigger_r", suffix: "R" },
    { label: "Dynamic Sizing", key: "dynamic_position_sizing" },
];

// Sections mapping from App.tsx to ensure consistency
const STRATEGY_SECTIONS = [
    { title: "Core Settings", keys: ["mode", "allow_short"] },
    { title: "Timeframes", keys: ["high_timeframe", "low_timeframe"] },
    { title: "Volatility Filters", keys: ["volatility_filter_enabled", "atr_period", "atr_percentile_min", "atr_percentile_max", "sl_atr_multiplier", "min_signal_confidence"] },
    { title: "Technical Entry Filters", keys: ["use_rsi_filter", "rsi_period", "rsi_overbought", "rsi_oversold", "use_rsi_momentum", "rsi_momentum_threshold", "use_adx_filter", "adx_period", "adx_threshold", "use_trend_filter", "trend_ema_period"] },
    { title: "Pattern Settings", keys: ["min_range_factor", "min_wick_to_range", "max_body_to_range", "risk_reward_ratio", "sl_buffer_atr"] },
    { title: "Partial Take Profits", keys: ["use_partial_tp", "tp1_r", "tp1_pct", "tp2_r", "tp2_pct", "runner_pct"] },
    { title: "Exit Management", keys: ["trailing_stop_enabled", "trail_start", "trail_step", "breakeven_move_enabled"] },
    { title: "Market Structure", keys: ["require_structure_confirmation", "support_level_lookback_bars"] },
    { title: "Cooldown & Psychology", keys: ["cooldown_after_loss_bars", "reduce_risk_after_loss", "risk_reduction_after_loss"] },
    { title: "Exchange Settings", keys: ["min_notional", "taker_fee", "slippage_bp"] },
];

const BacktestHistoryList: React.FC = () => {
    const [history, setHistory] = useState<BacktestSummary[]>([]);
    const [openRows, setOpenRows] = useState<Record<string, boolean>>({});

    const fetchHistory = async () => {
        try {
            const response = await fetch(`${API_BASE}/api/backtest/history`);
            if (response.ok) {
                const data = await response.json();
                setHistory(data.history || []);
            }
        } catch (error) {
            console.error("Failed to fetch backtest history:", error);
        }
    };

    useEffect(() => {
        fetchHistory();
        // Poll every 10 seconds to keep updated
        const interval = setInterval(fetchHistory, 10000);
        return () => clearInterval(interval);
    }, []);

    const toggleRow = (filename: string) => {
        setOpenRows(prev => ({ ...prev, [filename]: !prev[filename] }));
    };

    const formatDate = (isoString: string) => {
        try {
            return new Date(isoString).toLocaleString();
        } catch (e) {
            return isoString;
        }
    };

    const formatPnL = (val: number, initialCapital: number) => {
        const percentage = (val / initialCapital) * 100;
        return (
            <span style={{ color: val >= 0 ? 'green' : 'red', fontWeight: 'bold' }}>
                {val >= 0 ? '+' : ''}${val.toFixed(2)} ({val >= 0 ? '+' : ''}{percentage.toFixed(2)}%)
            </span>
        );
    };

    // Helper to get value from config safely
    const getConfigValue = (config: any, key: string) => {
        if (!config) return undefined;
        // Check top level for general settings, strategy_config for strategy params
        if (key in (config || {})) return config[key]; // Prioritize root for general settings
        if (key in (config.strategy_config || {})) return config.strategy_config[key];
        if (key in (config.account || {})) return config.account[key];
        if (key in (config.trading || {})) return config.trading[key];
        return undefined;
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardHeader
                title={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <History />
                        <Typography variant="h6">Recent Backtests (Last 10)</Typography>
                    </Box>
                }
            />
            <CardContent>
                <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell width="50px" />
                                <TableCell>Time</TableCell>
                                <TableCell>Strategy</TableCell>
                                <TableCell>Period</TableCell>
                                <TableCell>PnL</TableCell>
                                <TableCell align="right">Win Rate</TableCell>
                                <TableCell align="right">Drawdown</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {history.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={7} align="center">
                                        <Typography color="textSecondary" sx={{ py: 2 }}>
                                            No history found
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            ) : (
                                history.map((item, index) => {
                                    // Previous run is the NEXT item in the list (since list is desc by time)
                                    const previousRun = history[index + 1];

                                    return (
                                        <React.Fragment key={item.filename}>
                                            <TableRow
                                                hover
                                                onClick={() => toggleRow(item.filename)}
                                                sx={{
                                                    '& > *': { borderBottom: 'unset' },
                                                    cursor: 'pointer',
                                                    '&:hover': { backgroundColor: 'action.hover' }
                                                }}
                                            >
                                                <TableCell>
                                                    <IconButton
                                                        aria-label="expand row"
                                                        size="small"
                                                    >
                                                        {openRows[item.filename] ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
                                                    </IconButton>
                                                </TableCell>
                                                <TableCell component="th" scope="row">
                                                    {formatDate(item.timestamp)}
                                                </TableCell>
                                                <TableCell>{item.strategy}</TableCell>
                                                <TableCell>
                                                    <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                                                        {(() => {
                                                            const start = getConfigValue(item.configuration, 'start_date');
                                                            const end = getConfigValue(item.configuration, 'end_date');
                                                            if (start && end) {
                                                                const formatDateShort = (d: string) => {
                                                                    try {
                                                                        const [y, m, d_] = d.split('-');
                                                                        return `${d_}/${m}/${y}`;
                                                                    } catch { return d; }
                                                                };
                                                                return `${formatDateShort(String(start))} - ${formatDateShort(String(end))}`;
                                                            }
                                                            return '-';
                                                        })()}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell>{formatPnL(item.total_pnl, item.initial_capital)}</TableCell>
                                                <TableCell align="right">{(item.win_rate * 100).toFixed(1)}%</TableCell>
                                                <TableCell align="right" sx={{ color: 'red' }}>{item.max_drawdown.toFixed(2)}%</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={7}>
                                                    <Collapse in={openRows[item.filename]} timeout="auto" unmountOnExit>
                                                        <Box sx={{ margin: 2 }}>
                                                            <Box sx={{ display: 'flex', gap: 4, mb: 2, flexWrap: 'wrap' }}>
                                                                {/* Metrics Column */}
                                                                <Box sx={{ minWidth: 200, maxWidth: 250 }}>
                                                                    <Typography variant="subtitle2" gutterBottom color="primary">
                                                                        Key Metrics
                                                                    </Typography>
                                                                    <Typography variant="body2">Initial Capital: ${item.initial_capital.toLocaleString()}</Typography>
                                                                    <Typography variant="body2">Profit Factor: {item.profit_factor.toFixed(2)}</Typography>
                                                                    <Typography variant="body2">Sharpe Ratio: {item.sharpe_ratio?.toFixed(2) || 'N/A'}</Typography>
                                                                    <Typography variant="body2">Total Trades: {item.total_trades}</Typography>
                                                                    <Typography variant="body2" sx={{ color: 'green' }}>Wins: {item.winning_trades} (Avg: ${item.avg_win?.toFixed(2)})</Typography>
                                                                    <Typography variant="body2" sx={{ color: 'red' }}>Losses: {item.losing_trades} (Avg: ${item.avg_loss?.toFixed(2)})</Typography>

                                                                    <Box sx={{ mt: 2 }}>
                                                                        <Typography variant="subtitle2" gutterBottom color="primary">
                                                                            General Settings
                                                                        </Typography>
                                                                        {GENERAL_SETTINGS.map((setting) => {
                                                                            const val = getConfigValue(item.configuration, setting.key);
                                                                            if (val === undefined) return null;

                                                                            const prevVal = previousRun ? getConfigValue(previousRun.configuration, setting.key) : undefined;
                                                                            const isChanged = previousRun && String(val) !== String(prevVal);

                                                                            let displayVal = String(val);
                                                                            if (setting.format) displayVal = setting.format(val);
                                                                            else if (setting.suffix) displayVal += setting.suffix;

                                                                            return (
                                                                                <Typography key={setting.key} variant="body2" sx={{
                                                                                    fontSize: '0.8rem',
                                                                                    fontWeight: isChanged ? 'bold' : 'normal',
                                                                                    color: isChanged ? 'text.primary' : 'text.secondary'
                                                                                }}>
                                                                                    {setting.label}: {displayVal}
                                                                                </Typography>
                                                                            );
                                                                        })}
                                                                    </Box>
                                                                </Box>

                                                                {/* Configuration Columns */}
                                                                <Box sx={{ flex: 1 }}>
                                                                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                                                                        {STRATEGY_SECTIONS.map((section) => {
                                                                            // Check if section has any relevant keys
                                                                            const hasKeys = section.keys.some(k => getConfigValue(item.configuration, k) !== undefined);
                                                                            if (!hasKeys) return null;

                                                                            return (
                                                                                <Box key={section.title} sx={{ minWidth: 200, mb: 2 }}>
                                                                                    <Typography variant="subtitle2" gutterBottom color="primary" sx={{ fontSize: '0.9rem' }}>
                                                                                        {section.title}
                                                                                    </Typography>
                                                                                    <Box>
                                                                                        {section.keys.map(key => {
                                                                                            const val = getConfigValue(item.configuration, key);
                                                                                            if (val === undefined) return null;

                                                                                            // Compare with previous
                                                                                            const prevVal = previousRun ? getConfigValue(previousRun.configuration, key) : undefined;
                                                                                            // Compare formatted strings to handle occasional type diffs (number vs string)
                                                                                            const isChanged = previousRun && String(val) !== String(prevVal);

                                                                                            return (
                                                                                                <Typography key={key} variant="body2" sx={{
                                                                                                    fontSize: '0.8rem',
                                                                                                    fontWeight: isChanged ? 'bold' : 'normal',
                                                                                                    color: isChanged ? 'text.primary' : 'text.secondary'
                                                                                                }}>
                                                                                                    {key}: {String(val)}
                                                                                                </Typography>
                                                                                            );
                                                                                        })}
                                                                                    </Box>
                                                                                </Box>
                                                                            );
                                                                        })}
                                                                    </Box>
                                                                </Box>
                                                            </Box>

                                                            <Box>
                                                                <Typography variant="caption" display="block" color="textSecondary">
                                                                    File: {item.filename}
                                                                </Typography>
                                                            </Box>
                                                        </Box>
                                                    </Collapse>
                                                </TableCell>
                                            </TableRow>
                                        </React.Fragment>
                                    );
                                })
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            </CardContent>
        </Card>
    );
};

export default BacktestHistoryList;
