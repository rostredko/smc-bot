import React, { useEffect, useState } from 'react';
import {
    Box, Card, CardHeader, CardContent, Typography, Table, TableBody, TableCell,
    TableContainer, TableHead, TableRow, Paper, IconButton, Collapse, Button, Stack,
    Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, TextField, CircularProgress
} from '@mui/material';
import {
    KeyboardArrowDown, KeyboardArrowUp, History, NavigateBefore, NavigateNext,
    FirstPage, LastPage, DeleteOutline, FileCopyOutlined
} from '@mui/icons-material';

import { BacktestSummary } from '../model/types';
import { fetchBacktestHistory, fetchDetailedResults, saveUserConfigTemplate, deleteBacktestHistory } from '../api/historyApi';
import TradeAnalysisChart from '../../../entities/trade/ui/TradeAnalysisChart';
import TradeDetailsModal from '../../../features/trade-details/ui/TradeDetailsModal';
import { useConfigContext } from '../../../app/providers/config/ConfigProvider';

// General Settings mapping
const GENERAL_SETTINGS = [
    { label: "Initial Capital", key: "initial_capital", format: (v: any) => `$${v}` },
    { label: "Risk Per Trade", key: "risk_per_trade", suffix: "%" },
    { label: "Max Drawdown", key: "max_drawdown", suffix: "%" },
    { label: "Leverage", key: "leverage", suffix: "x" },
    { label: "Symbol", key: "symbol" },
    { label: "Timeframes", key: "timeframes", format: (v: any) => Array.isArray(v) ? v.join(', ') : v },
    { label: "Start Date", key: "start_date" },
    { label: "End Date", key: "end_date" },
    { label: "Trailing Stop Dist", key: "trailing_stop_distance" },
    { label: "Breakeven Trigger", key: "breakeven_trigger_r", suffix: "R" },
    { label: "Dynamic Sizing", key: "dynamic_position_sizing" },
];

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
    const { loadUserConfigs } = useConfigContext();
    const [history, setHistory] = useState<BacktestSummary[]>([]);
    const [openRows, setOpenRows] = useState<Record<string, boolean>>({});
    const [page, setPage] = useState(1);
    const [pageSize] = useState(10);
    const [totalPages, setTotalPages] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [detailedResults, setDetailedResults] = useState<Record<string, any>>({});
    const [selectedTrade, setSelectedTrade] = useState<any | null>(null);
    const [isTradeModalOpen, setIsTradeModalOpen] = useState(false);

    const loadData = async (currentPage: number = 1) => {
        setLoading(true);
        try {
            const data = await fetchBacktestHistory(currentPage, pageSize);
            setHistory(data.history || []);
            if (data.pagination) {
                setTotalPages(data.pagination.total_pages);
                setTotalCount(data.pagination.total_count);
                setPage(data.pagination.page);
            }
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData(page);
    }, [page]);

    useEffect(() => {
        const interval = setInterval(() => loadData(page), 10000);
        return () => clearInterval(interval);
    }, [page]);

    const toggleRow = async (filename: string) => {
        const isCurrentlyOpen = openRows[filename];
        setOpenRows(prev => ({ ...prev, [filename]: !isCurrentlyOpen }));

        if (!isCurrentlyOpen && !detailedResults[filename]) {
            try {
                const data = await fetchDetailedResults(filename);
                setDetailedResults(prev => ({ ...prev, [filename]: data }));
            } catch (error) {
                console.error(error);
            }
        }
    };

    const handleTradeClick = (trade: any) => {
        if (trade) {
            setSelectedTrade(trade);
            setIsTradeModalOpen(true);
        }
    };

    const formatDate = (isoString: string) => {
        try { return new Date(isoString).toLocaleString(); } catch { return isoString; }
    };

    const formatPnL = (val: number, initialCapital: number) => {
        const percentage = (val / initialCapital) * 100;
        return (
            <span style={{ color: val >= 0 ? 'green' : 'red', fontWeight: 'bold' }}>
                {val >= 0 ? '+' : ''}${val.toFixed(2)} ({val >= 0 ? '+' : ''}{percentage.toFixed(2)}%)
            </span>
        );
    };

    const getConfigValue = (config: any, key: string) => {
        if (!config) return undefined;
        if (key in config) return config[key];
        if (key in (config.strategy_config || {})) return config.strategy_config[key];
        if (key in (config.account || {})) return config.account[key];
        if (key in (config.trading || {})) return config.trading[key];
        return undefined;
    };

    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [itemToDelete, setItemToDelete] = useState<string | null>(null);
    const [saveDialogOpen, setSaveDialogOpen] = useState(false);
    const [itemToSave, setItemToSave] = useState<BacktestSummary | null>(null);
    const [saveTemplateName, setSaveTemplateName] = useState("");
    const [saveError, setSaveError] = useState("");

    const handleSaveClick = (e: React.MouseEvent, item: BacktestSummary) => {
        e.stopPropagation();
        setItemToSave(item);
        setSaveTemplateName("");
        setSaveError("");
        setSaveDialogOpen(true);
    };

    const handleSaveConfirm = async () => {
        if (!itemToSave || !saveTemplateName.trim() || !/^[a-zA-Z0-9_-]+$/.test(saveTemplateName)) {
            setSaveError("Invalid name. Use only letters, numbers, dashes, and underscores.");
            return;
        }
        try {
            await saveUserConfigTemplate(saveTemplateName, itemToSave.configuration);
            loadUserConfigs(); // Update context so the load dialog sees it
            setSaveDialogOpen(false);
            setItemToSave(null);
        } catch (error: any) {
            setSaveError(error.message || "Network error occurred.");
        }
    };

    const handleDeleteClick = (e: React.MouseEvent, filename: string) => {
        e.stopPropagation();
        setItemToDelete(filename);
        setDeleteDialogOpen(true);
    };

    const handleDeleteConfirm = async () => {
        if (!itemToDelete) return;
        try {
            await deleteBacktestHistory(itemToDelete);
            loadData(page);
        } catch (error) {
            console.error(error);
        } finally {
            setDeleteDialogOpen(false);
            setItemToDelete(null);
        }
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardHeader
                title={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <History />
                        <Typography variant="h6">Recent Backtests</Typography>
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
                                <TableCell align="center">Actions</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {history.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={8} align="center">
                                        <Typography color="textSecondary" sx={{ py: 2 }}>No history found</Typography>
                                    </TableCell>
                                </TableRow>
                            ) : (
                                history.map((item, index) => {
                                    const previousRun = history[index + 1];

                                    return (
                                        <React.Fragment key={item.filename}>
                                            <TableRow
                                                hover
                                                onClick={() => toggleRow(item.filename)}
                                                sx={{
                                                    '& > *': { borderBottom: '1px solid #e0e0e0' },
                                                    cursor: 'pointer',
                                                    '&:hover': { backgroundColor: 'action.hover' }
                                                }}
                                            >
                                                <TableCell>
                                                    <IconButton size="small">
                                                        {openRows[item.filename] ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
                                                    </IconButton>
                                                </TableCell>
                                                <TableCell component="th" scope="row">{formatDate(item.timestamp)}</TableCell>
                                                <TableCell>{item.strategy}</TableCell>
                                                <TableCell>
                                                    <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                                                        {(() => {
                                                            const start = getConfigValue(item.configuration, 'start_date');
                                                            const end = getConfigValue(item.configuration, 'end_date');
                                                            if (start && end) {
                                                                const mapDate = (d: string) => { try { const [y, m, d_] = d.split('-'); return `${d_}/${m}/${y}`; } catch { return d; } };
                                                                return `${mapDate(String(start))} - ${mapDate(String(end))}`;
                                                            }
                                                            return '-';
                                                        })()}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell>{formatPnL(item.total_pnl, item.initial_capital)}</TableCell>
                                                <TableCell align="right">{(item.win_rate * 100).toFixed(1)}%</TableCell>
                                                <TableCell align="right" sx={{ color: 'red' }}>{item.max_drawdown.toFixed(2)}%</TableCell>
                                                <TableCell align="center">
                                                    <IconButton size="small" onClick={(e) => handleSaveClick(e, item)} title="Save as template" sx={{ '&:hover': { color: 'primary.main' }, mr: 1 }}>
                                                        <FileCopyOutlined fontSize="small" />
                                                    </IconButton>
                                                    <IconButton size="small" onClick={(e) => handleDeleteClick(e, item.filename)} title="Delete backtest" sx={{ '&:hover': { color: 'error.main' } }}>
                                                        <DeleteOutline fontSize="small" />
                                                    </IconButton>
                                                </TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={8}>
                                                    <Collapse in={openRows[item.filename]} timeout="auto" unmountOnExit>
                                                        <Box sx={{ margin: 2 }}>
                                                            <Box sx={{ display: 'flex', gap: 4, mb: 2, flexWrap: 'wrap' }}>
                                                                <Box sx={{ minWidth: 200, maxWidth: 250 }}>
                                                                    <Typography variant="subtitle2" gutterBottom color="primary">Key Metrics</Typography>
                                                                    <Typography variant="body2">Initial Capital: ${item.initial_capital.toLocaleString()}</Typography>
                                                                    <Typography variant="body2">Profit Factor: {item.profit_factor.toFixed(2)}</Typography>
                                                                    <Typography variant="body2">Sharpe Ratio: {item.sharpe_ratio?.toFixed(2) || 'N/A'}</Typography>
                                                                    <Typography variant="body2">Total Trades: {item.total_trades}</Typography>
                                                                    <Typography variant="body2" sx={{ color: 'green' }}>Wins: {item.winning_trades} (Avg: ${item.avg_win?.toFixed(2)})</Typography>
                                                                    <Typography variant="body2" sx={{ color: 'red' }}>Losses: {item.losing_trades} (Avg: ${item.avg_loss?.toFixed(2)})</Typography>

                                                                    <Box sx={{ mt: 2 }}>
                                                                        <Typography variant="subtitle2" gutterBottom color="primary">General Settings</Typography>
                                                                        {GENERAL_SETTINGS.map((setting) => {
                                                                            const val = getConfigValue(item.configuration, setting.key);
                                                                            if (val === undefined) return null;
                                                                            const prevVal = previousRun ? getConfigValue(previousRun.configuration, setting.key) : undefined;
                                                                            const isChanged = previousRun && String(val) !== String(prevVal);
                                                                            let displayVal = String(val);
                                                                            if (setting.format) displayVal = setting.format(val);
                                                                            else if (setting.suffix) displayVal += setting.suffix;

                                                                            return (
                                                                                <Typography key={setting.key} variant="body2" sx={{ fontSize: '0.8rem', fontWeight: isChanged ? 'bold' : 'normal', color: isChanged ? 'text.primary' : 'text.secondary' }}>
                                                                                    {setting.label}: {displayVal}
                                                                                </Typography>
                                                                            );
                                                                        })}
                                                                    </Box>
                                                                </Box>

                                                                <Box sx={{ flex: 1 }}>
                                                                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                                                                        {STRATEGY_SECTIONS.map((section) => {
                                                                            const hasKeys = section.keys.some(k => getConfigValue(item.configuration, k) !== undefined);
                                                                            if (!hasKeys) return null;
                                                                            return (
                                                                                <Box key={section.title} sx={{ minWidth: 200, mb: 2 }}>
                                                                                    <Typography variant="subtitle2" gutterBottom color="primary" sx={{ fontSize: '0.9rem' }}>{section.title}</Typography>
                                                                                    {section.keys.map(key => {
                                                                                        const val = getConfigValue(item.configuration, key);
                                                                                        if (val === undefined) return null;
                                                                                        const prevVal = previousRun ? getConfigValue(previousRun.configuration, key) : undefined;
                                                                                        const isChanged = previousRun && String(val) !== String(prevVal);
                                                                                        return (
                                                                                            <Typography key={key} variant="body2" sx={{ fontSize: '0.8rem', fontWeight: isChanged ? 'bold' : 'normal', color: isChanged ? 'text.primary' : 'text.secondary' }}>
                                                                                                {key}: {String(val)}
                                                                                            </Typography>
                                                                                        );
                                                                                    })}
                                                                                </Box>
                                                                            );
                                                                        })}
                                                                    </Box>
                                                                </Box>
                                                            </Box>

                                                            <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
                                                                <Typography variant="subtitle2" gutterBottom color="primary">Trade Analysis</Typography>
                                                                {!detailedResults[item.filename] ? (
                                                                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress size={30} /></Box>
                                                                ) : detailedResults[item.filename].trades?.length > 0 ? (
                                                                    <Box sx={{ mt: 2 }}>
                                                                        <TradeAnalysisChart trades={detailedResults[item.filename].trades} onTradeClick={handleTradeClick} height={200} />
                                                                    </Box>
                                                                ) : (
                                                                    <Typography variant="body2" color="textSecondary">No trade data available.</Typography>
                                                                )}
                                                            </Box>
                                                            <Box sx={{ mt: 3 }}>
                                                                <Typography variant="caption" display="block" color="textSecondary">File: {item.filename}</Typography>
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

                {totalPages > 1 && (
                    <Stack direction="row" spacing={1} alignItems="center" justifyContent="center" sx={{ mt: 2 }}>
                        <Button variant="outlined" size="small" startIcon={<FirstPage />} disabled={page <= 1 || loading} onClick={() => setPage(1)}>First</Button>
                        <Button variant="outlined" size="small" startIcon={<NavigateBefore />} disabled={page <= 1 || loading} onClick={() => setPage(p => Math.max(1, p - 1))}>Previous</Button>
                        <Typography variant="body2" color="textSecondary" sx={{ minWidth: '200px', textAlign: 'center' }}>{loading ? 'Loading...' : `Page ${page} of ${totalPages} (${totalCount} total)`}</Typography>
                        <Button variant="outlined" size="small" endIcon={<NavigateNext />} disabled={page >= totalPages || loading} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Next</Button>
                        <Button variant="outlined" size="small" endIcon={<LastPage />} disabled={page >= totalPages || loading} onClick={() => setPage(totalPages)}>Last</Button>
                    </Stack>
                )}

                <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#fff' } }}>
                    <DialogTitle sx={{ borderBottom: '1px solid #333' }}>Save Configuration Template</DialogTitle>
                    <DialogContent sx={{ mt: 2 }}>
                        <DialogContentText sx={{ mb: 2, color: '#aaa' }}>Enter a name for this template to quickly load it later. Use only letters, numbers, dashes, and underscores.</DialogContentText>
                        <TextField autoFocus margin="dense" label="Template Name" type="text" fullWidth variant="outlined" value={saveTemplateName} onChange={(e) => { setSaveTemplateName(e.target.value); setSaveError(""); }} error={!!saveError} helperText={saveError} sx={{ input: { color: '#fff' }, label: { color: '#aaa' }, '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#555' }, '&:hover fieldset': { borderColor: '#888' } } }} />
                    </DialogContent>
                    <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                        <Button onClick={() => setSaveDialogOpen(false)} sx={{ color: '#aaa' }}>Cancel</Button>
                        <Button onClick={handleSaveConfirm} color="primary" variant="contained">Save</Button>
                    </DialogActions>
                </Dialog>

                <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#fff' } }}>
                    <DialogTitle sx={{ borderBottom: '1px solid #333' }}>Confirm Deletion</DialogTitle>
                    <DialogContent sx={{ mt: 2 }}>
                        <DialogContentText sx={{ color: '#aaa' }}>Are you sure you want to delete this backtest result? This action cannot be undone.</DialogContentText>
                    </DialogContent>
                    <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                        <Button onClick={() => setDeleteDialogOpen(false)} sx={{ color: '#aaa' }}>Cancel</Button>
                        <Button onClick={handleDeleteConfirm} color="error" variant="contained">Delete</Button>
                    </DialogActions>
                </Dialog>

                <TradeDetailsModal open={isTradeModalOpen} onClose={() => setIsTradeModalOpen(false)} selectedTrade={selectedTrade} />
            </CardContent>
        </Card>
    );
};

export default BacktestHistoryList;
