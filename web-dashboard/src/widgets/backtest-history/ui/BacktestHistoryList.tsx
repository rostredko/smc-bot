import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    Box, Card, CardHeader, CardContent, Typography, Table, TableBody, TableCell,
    TableContainer, TableHead, TableRow, Paper, IconButton, Collapse, Button, Stack,
    Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, TextField, CircularProgress, Chip, Tooltip
} from '@mui/material';
import {
    KeyboardArrowDown, KeyboardArrowUp, History, NavigateBefore, NavigateNext,
    FirstPage, LastPage, DeleteOutline, FileCopyOutlined, ArrowUpward, ArrowDownward, ContentCopy, Refresh
} from '@mui/icons-material';

import { BacktestSummary } from '../model/types';
import { fetchBacktestHistory, fetchDetailedResults, saveUserConfigTemplate, deleteBacktestHistory } from '../api/historyApi';
import { formatVariantParamsShort, variantParamsToTemplateName } from '../../../shared/lib/formatVariantParams';
import TradeAnalysisChart from '../../../entities/trade/ui/TradeAnalysisChart';
import TradeDetailsModal from '../../../features/trade-details/ui/TradeDetailsModal';
import { useConfigContext } from '../../../app/providers/config/ConfigProvider';
import { useResultsContext } from '../../../app/providers/results/ResultsProvider';

const shouldIgnoreTransientFetchError = (error: unknown) => {
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return true;
    }

    const message = error instanceof Error ? error.message.toLowerCase() : String(error ?? '').toLowerCase();
    return message.includes('failed to fetch') || message.includes('load failed');
};

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
    { label: "Position Cap Adverse", key: "position_cap_adverse" },
];

const STRATEGY_SECTIONS = [
    { title: "Technical Entry Filters", keys: ["use_rsi_filter", "rsi_period", "rsi_overbought", "rsi_oversold", "use_rsi_momentum", "rsi_momentum_threshold", "use_adx_filter", "adx_period", "adx_threshold", "use_trend_filter", "trend_ema_period"] },
    { title: "Entry & Risk", keys: ["min_range_factor", "min_wick_to_range", "max_body_to_range", "risk_reward_ratio", "sl_buffer_atr", "atr_period"] },
    { title: "Patterns", keys: ["pattern_hammer", "pattern_inverted_hammer", "pattern_shooting_star", "pattern_hanging_man", "pattern_bullish_engulfing", "pattern_bearish_engulfing"] },
];

const formatLiveDuration = (mins: number | null | undefined): string => {
    if (mins == null) return 'N/A';
    if (mins < 60) {
        return `${Math.round(mins * 10) / 10} min`;
    }
    const totalMinutes = Math.round(mins);
    const hours = Math.floor(totalMinutes / 60);
    const remainingMins = totalMinutes % 60;

    if (hours < 24) {
        return remainingMins > 0 ? `${hours}h ${remainingMins}m` : `${hours}h`;
    }

    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
};

const getLoadedTemplateName = (item: BacktestSummary) => {
    return item.loaded_template_name ?? item.configuration?.loaded_template_name ?? null;
};

const BacktestHistoryList: React.FC = () => {
    const { loadUserConfigs, isLiveRunning, isLiveStopping, isRunning } = useConfigContext();
    const { backtestStatus, results } = useResultsContext();
    const [history, setHistory] = useState<BacktestSummary[]>([]);
    const [openRows, setOpenRows] = useState<Record<string, boolean>>({});
    const [page, setPage] = useState(1);
    const [pageSize] = useState(10);
    const [totalPages, setTotalPages] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [sortField, setSortField] = useState<string | undefined>(undefined);
    const [sortDirection, setSortDirection] = useState<'asc' | 'desc' | undefined>(undefined);
    const [detailedResults, setDetailedResults] = useState<Record<string, any>>({});
    const [selectedTrade, setSelectedTrade] = useState<any | null>(null);
    const [isTradeModalOpen, setIsTradeModalOpen] = useState(false);
    const [tradeModalConfig, setTradeModalConfig] = useState<{ symbol: string; timeframes: string[]; strategyConfig: Record<string, any>; exchangeType: string; backtestStart?: string; backtestEnd?: string } | null>(null);
    const [tradeModalTrades, setTradeModalTrades] = useState<any[]>([]);
    const [expandedForChart, setExpandedForChart] = useState<Record<string, boolean>>({});
    const lastHistorySyncRunRef = useRef<string>('');
    const prevLiveBusyRef = useRef<boolean>(false);
    const prevBacktestRunRef = useRef<boolean>(false);
    const lastResultsSyncRunRef = useRef<string>('');

    const loadData = useCallback(async (currentPage: number = 1, field?: string, direction?: 'asc' | 'desc') => {
        setLoading(true);
        try {
            const data = await fetchBacktestHistory(currentPage, pageSize, field ?? sortField, direction ?? sortDirection);
            setHistory(data.history || []);
            if (data.pagination) {
                setTotalPages(data.pagination.total_pages);
                setTotalCount(data.pagination.total_count);
                setPage(data.pagination.page);
            }
        } catch (error) {
            if (!shouldIgnoreTransientFetchError(error)) {
                console.error(error);
            }
        } finally {
            setLoading(false);
        }
    }, [pageSize, sortField, sortDirection]);

    useEffect(() => {
        loadData(page);
    }, [loadData, page]);

    useEffect(() => {
        setExpandedForChart({});
    }, [page]);

    // Refresh history when backtest completes or is cancelled (from status update)
    useEffect(() => {
        const runId = backtestStatus?.run_id;
        const status = backtestStatus?.status;
        if (!runId || !status) return;
        if (status !== 'completed' && status !== 'cancelled') return;

        const syncKey = `${runId}:${status}`;
        if (lastHistorySyncRunRef.current === syncKey) return;
        lastHistorySyncRunRef.current = syncKey;

        const delay = page !== 1 ? 100 : 500;
        const t1 = setTimeout(() => loadData(1), delay);
        // Retry after 1.5s in case MongoDB write was slow
        const t2 = setTimeout(() => loadData(1), delay + 1500);
        return () => {
            clearTimeout(t1);
            clearTimeout(t2);
        };
    }, [backtestStatus?.run_id, backtestStatus?.status, page, loadData]);

    // Refresh history when backtest stops (isRunning: true -> false) — catches stop + completion even if status update missed
    useEffect(() => {
        const wasRunning = prevBacktestRunRef.current;
        prevBacktestRunRef.current = isRunning;
        if (!wasRunning || isRunning) return;

        if (page !== 1) setPage(1);
        const t1 = setTimeout(() => loadData(1), 300);
        const t2 = setTimeout(() => loadData(1), 1800);
        return () => {
            clearTimeout(t1);
            clearTimeout(t2);
        };
    }, [isRunning, page, loadData]);

    useEffect(() => {
        if (!results) return;

        const runId = backtestStatus?.run_id ?? (results as { run_id?: string })?.run_id;
        const status = backtestStatus?.status;
        if (!runId || (status !== 'completed' && status !== 'cancelled')) return;

        if (lastResultsSyncRunRef.current === runId) return;
        lastResultsSyncRunRef.current = runId;

        if (page !== 1) {
            setPage(1);
        }
        const t1 = setTimeout(() => loadData(1), 100);
        const t2 = setTimeout(() => loadData(1), 1200);
        return () => {
            clearTimeout(t1);
            clearTimeout(t2);
        };
    }, [results, backtestStatus?.run_id, backtestStatus?.status, page, loadData]);

    useEffect(() => {
        const isLiveBusy = isLiveRunning || isLiveStopping;
        const wasLiveBusy = prevLiveBusyRef.current;
        prevLiveBusyRef.current = isLiveBusy;

        if (!wasLiveBusy || isLiveBusy) return;

        if (page !== 1) {
            setPage(1);
            return;
        }
        loadData(1);
    }, [isLiveRunning, isLiveStopping, page, loadData]);

    useEffect(() => {
        if (history.length === 0) return;
        const currentFilenames = new Set(history.map((h) => h.filename));
        setDetailedResults((prev) => {
            const next = { ...prev };
            let changed = false;
            for (const key of Object.keys(next)) {
                if (!currentFilenames.has(key)) {
                    delete next[key];
                    changed = true;
                }
            }
            return changed ? next : prev;
        });
    }, [page, history]);

    const handleSort = (field: string) => {
        let newDirection: 'asc' | 'desc' | undefined;
        if (sortField === field) {
            if (sortDirection === 'desc') newDirection = 'asc';
            else if (sortDirection === 'asc') newDirection = undefined;
            else newDirection = 'desc';
        } else {
            newDirection = 'desc';
        }

        setSortField(newDirection ? field : undefined);
        setSortDirection(newDirection);
        setPage(1); // Reset to first page
        loadData(1, newDirection ? field : undefined, newDirection);
    };

    const toggleRow = async (filename: string) => {
        const isCurrentlyOpen = openRows[filename];
        setOpenRows(prev => ({ ...prev, [filename]: !isCurrentlyOpen }));

        if (!isCurrentlyOpen && !detailedResults[filename]) {
            try {
                const data = await fetchDetailedResults(filename);
                setDetailedResults(prev => ({ ...prev, [filename]: data }));
            } catch (error) {
                if (!shouldIgnoreTransientFetchError(error)) {
                    console.error(error);
                }
            }
        }
    };

    const getConfigValue = useCallback((config: any, key: string) => {
        if (!config) return undefined;
        const c = config.configuration ?? config;
        if (key in c) return c[key];
        if (key in (c.strategy_config || {})) return c.strategy_config[key];
        if (key in (c.account || {})) return c.account[key];
        if (key in (c.trading || {})) return c.trading[key];
        return undefined;
    }, []);

    const handleTradeClick = useCallback((trade: any, configOrResults?: any, isLive: boolean = false) => {
        if (trade) {
            setSelectedTrade(trade);
            const config = configOrResults?.configuration ?? configOrResults;
            setTradeModalConfig(config ? {
                symbol: getConfigValue(config, 'symbol') ?? 'BTC/USDT',
                timeframes: (() => {
                    const tf = getConfigValue(config, 'timeframes');
                    return Array.isArray(tf) ? tf : ['1h'];
                })(),
                strategyConfig: config?.strategy_config ?? config?.strategyConfig ?? {},
                exchangeType: getConfigValue(config, 'exchange_type') ?? 'future',
                backtestStart: isLive ? undefined : getConfigValue(config, 'start_date'),
                backtestEnd: isLive ? undefined : getConfigValue(config, 'end_date'),
            } : null);
            setTradeModalTrades(configOrResults?.trades ?? []);
            setIsTradeModalOpen(true);
        }
    }, [getConfigValue]);

    const formatDate = (isoString: string | undefined) => {
        if (isoString == null) return '-';
        try { return new Date(isoString).toLocaleString(); } catch { return String(isoString); }
    };

    const formatPnL = (val: number | undefined, initialCapital: number | undefined) => {
        if (val == null || initialCapital == null || initialCapital === 0) return <span>-</span>;
        const percentage = (val / initialCapital) * 100;
        return (
            <span style={{ color: val >= 0 ? 'green' : 'red', fontWeight: 'bold' }}>
                {val >= 0 ? '+' : ''}${val.toFixed(2)} ({val >= 0 ? '+' : ''}{percentage.toFixed(2)}%)
            </span>
        );
    };

    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [itemToDelete, setItemToDelete] = useState<string | null>(null);
    const [saveDialogOpen, setSaveDialogOpen] = useState(false);
    const [itemToSave, setItemToSave] = useState<BacktestSummary | null>(null);
    const [variantToSave, setVariantToSave] = useState<{ variant: any; item: BacktestSummary } | null>(null);
    const [saveTemplateName, setSaveTemplateName] = useState("");
    const [saveError, setSaveError] = useState("");

    const handleSaveClick = (e: React.MouseEvent, item: BacktestSummary) => {
        e.stopPropagation();
        setItemToSave(item);
        setVariantToSave(null);
        setSaveTemplateName("");
        setSaveError("");
        setSaveDialogOpen(true);
    };

    const handleVariantSaveClick = (e: React.MouseEvent, variant: any, item: BacktestSummary) => {
        e.stopPropagation();
        setItemToSave(null);
        setVariantToSave({ variant, item });
        setSaveTemplateName(variantParamsToTemplateName(variant.params) || "");
        setSaveError("");
        setSaveDialogOpen(true);
    };

    const handleSaveConfirm = async () => {
        if (!saveTemplateName.trim() || !/^[a-zA-Z0-9_-]+$/.test(saveTemplateName)) {
            setSaveError("Invalid name. Use only letters, numbers, dashes, and underscores.");
            return;
        }
        const config = variantToSave
            ? (() => {
                const cfg = variantToSave.item.configuration || {};
                const baseSt = cfg.strategy_config ?? {};
                const params = variantToSave.variant.params ?? {};
                const cleanBase: Record<string, unknown> = {};
                for (const [k, v] of Object.entries(baseSt)) {
                    cleanBase[k] = Array.isArray(v) && params[k] !== undefined ? params[k] : v;
                }
                const strategyConfig = { ...cleanBase, ...params };
                const out: Record<string, unknown> = { ...cfg, strategy_config: strategyConfig };
                // Single-run config: strip optimize fields so loaded template runs as single
                delete out.run_mode;
                delete out.opt_params;
                delete out.opt_target_metric;
                delete out.opt_timeframes;
                out.run_mode = 'single';
                if (typeof params.trailing_stop_distance === 'number') {
                    out.trailing_stop_distance = params.trailing_stop_distance;
                }
                return out;
            })()
            : itemToSave?.configuration;
        if (!config) return;
        try {
            await saveUserConfigTemplate(saveTemplateName, config);
            loadUserConfigs();
            setSaveDialogOpen(false);
            setItemToSave(null);
            setVariantToSave(null);
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
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', flexWrap: 'wrap', gap: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <History />
                            <Typography variant="h6">History</Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                                {totalCount > 0 ? `${totalCount} runs stored in history` : 'No runs stored yet'}
                            </Typography>
                        </Box>
                        <Tooltip title="Refresh list">
                            <IconButton size="small" onClick={() => loadData(page)} disabled={loading}>
                                <Refresh fontSize="small" />
                            </IconButton>
                        </Tooltip>
                    </Box>
                }
            />
            <CardContent sx={{ overflowX: 'auto', px: { xs: 1, sm: 2 } }}>
                <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto', minWidth: 0 }}>
                    <Table size="small" sx={{ minWidth: 520 }}>
                        <TableHead>
                            <TableRow>
                                <TableCell width="50px" />
                                <TableCell sx={{ cursor: 'pointer', '&:hover': { color: 'primary.main' } }} onClick={() => handleSort('created_at')}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        Time
                                        {sortField === 'created_at' && sortDirection === 'desc' ? <ArrowDownward fontSize="small" color="primary" /> :
                                            sortField === 'created_at' && sortDirection === 'asc' ? <ArrowUpward fontSize="small" color="primary" /> :
                                                <Box sx={{ display: 'flex', flexDirection: 'column', opacity: 0.3 }}><KeyboardArrowUp sx={{ fontSize: 14, mb: -1 }} /><KeyboardArrowDown sx={{ fontSize: 14 }} /></Box>}
                                    </Box>
                                </TableCell>
                                <TableCell sx={{ cursor: 'pointer', '&:hover': { color: 'primary.main' } }} onClick={() => handleSort('strategy')}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        Strategy
                                        {sortField === 'strategy' && sortDirection === 'desc' ? <ArrowDownward fontSize="small" color="primary" /> :
                                            sortField === 'strategy' && sortDirection === 'asc' ? <ArrowUpward fontSize="small" color="primary" /> :
                                                <Box sx={{ display: 'flex', flexDirection: 'column', opacity: 0.3 }}><KeyboardArrowUp sx={{ fontSize: 14, mb: -1 }} /><KeyboardArrowDown sx={{ fontSize: 14 }} /></Box>}
                                    </Box>
                                </TableCell>
                                <TableCell>Period</TableCell>
                                <TableCell sx={{ cursor: 'pointer', '&:hover': { color: 'primary.main' } }} onClick={() => handleSort('total_pnl')}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        PnL
                                        {sortField === 'total_pnl' && sortDirection === 'desc' ? <ArrowDownward fontSize="small" color="primary" /> :
                                            sortField === 'total_pnl' && sortDirection === 'asc' ? <ArrowUpward fontSize="small" color="primary" /> :
                                                <Box sx={{ display: 'flex', flexDirection: 'column', opacity: 0.3 }}><KeyboardArrowUp sx={{ fontSize: 14, mb: -1 }} /><KeyboardArrowDown sx={{ fontSize: 14 }} /></Box>}
                                    </Box>
                                </TableCell>
                                <TableCell align="right" sx={{ cursor: 'pointer', '&:hover': { color: 'primary.main' } }} onClick={() => handleSort('win_rate')}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 0.5 }}>
                                        {sortField === 'win_rate' && sortDirection === 'desc' ? <ArrowDownward fontSize="small" color="primary" /> :
                                            sortField === 'win_rate' && sortDirection === 'asc' ? <ArrowUpward fontSize="small" color="primary" /> :
                                                <Box sx={{ display: 'flex', flexDirection: 'column', opacity: 0.3 }}><KeyboardArrowUp sx={{ fontSize: 14, mb: -1 }} /><KeyboardArrowDown sx={{ fontSize: 14 }} /></Box>}
                                        Win Rate
                                    </Box>
                                </TableCell>
                                <TableCell align="right" sx={{ cursor: 'pointer', '&:hover': { color: 'primary.main' } }} onClick={() => handleSort('max_drawdown')}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 0.5 }}>
                                        {sortField === 'max_drawdown' && sortDirection === 'desc' ? <ArrowDownward fontSize="small" color="primary" /> :
                                            sortField === 'max_drawdown' && sortDirection === 'asc' ? <ArrowUpward fontSize="small" color="primary" /> :
                                                <Box sx={{ display: 'flex', flexDirection: 'column', opacity: 0.3 }}><KeyboardArrowUp sx={{ fontSize: 14, mb: -1 }} /><KeyboardArrowDown sx={{ fontSize: 14 }} /></Box>}
                                        Drawdown
                                    </Box>
                                </TableCell>
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
                                                <TableCell sx={{ minWidth: { xs: 100, sm: 120 } }}>
                                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', minWidth: 0 }}>
                                                        <span style={{ wordBreak: 'break-word' }}>{item.is_optimization_batch ? `${item.strategy} (${item.variants_count ?? 0} variants)` : item.strategy}</span>
                                                        {item.is_live && <Chip label="LIVE" size="small" color="secondary" sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0 }} />}
                                                        {item.is_optimization_batch && <Chip label="OPTIMIZE" size="small" color="info" sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0 }} />}
                                                        {getLoadedTemplateName(item) && (
                                                            <Chip
                                                                label={getLoadedTemplateName(item)}
                                                                size="small"
                                                                variant="outlined"
                                                                color="primary"
                                                                sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0, maxWidth: '100%' }}
                                                            />
                                                        )}
                                                    </Box>
                                                </TableCell>
                                                <TableCell>
                                                    <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                                                        {(() => {
                                                            if (item.is_live) return 'Live Run';
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
                                                <TableCell align="right">{item.win_rate != null ? (item.win_rate * 100).toFixed(1) : '-'}%</TableCell>
                                                <TableCell align="right" sx={{ color: 'red' }}>{item.max_drawdown != null ? item.max_drawdown.toFixed(2) : '-'}%</TableCell>
                                                <TableCell align="center">
                                                    <IconButton size="small" onClick={(e) => handleSaveClick(e, item)} title="Save as template" sx={{ '&:hover': { color: 'primary.main' }, mr: 1 }}>
                                                        <FileCopyOutlined fontSize="small" />
                                                    </IconButton>
                                                    <IconButton size="small" onClick={(e) => handleDeleteClick(e, item.filename)} title="Delete backtest" sx={{ '&:hover': { color: 'error.main' } }}>
                                                        <DeleteOutline fontSize="small" />
                                                    </IconButton>
                                                </TableCell>
                                            </TableRow>
                                            <TableRow onClick={(e) => e.stopPropagation()}>
                                                <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={8}>
                                                    <Collapse
                                                        in={openRows[item.filename]}
                                                        timeout="auto"
                                                        unmountOnExit
                                                        onEntered={() => {
                                                            requestAnimationFrame(() => {
                                                                setExpandedForChart((p) => ({ ...p, [item.filename]: true }));
                                                            });
                                                        }}
                                                        onExited={() => setExpandedForChart((p) => ({ ...p, [item.filename]: false }))}
                                                    >
                                                        <Box sx={{ margin: 2 }}>
                                                            {getLoadedTemplateName(item) && (
                                                                <Box sx={{ mb: 2 }}>
                                                                    <Chip
                                                                        label={getLoadedTemplateName(item)}
                                                                        size="small"
                                                                        variant="outlined"
                                                                        color="primary"
                                                                        sx={{ height: 20, fontSize: '0.65rem' }}
                                                                    />
                                                                </Box>
                                                            )}
                                                            {item.is_optimization_batch && Array.isArray(detailedResults[item.filename]?.variants) && detailedResults[item.filename].variants.length > 0 && (
                                                                <Box sx={{ mb: 3 }}>
                                                                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
                                                                        <Typography variant="subtitle2">Variants</Typography>
                                                                        <Tooltip title="Copy to JSON">
                                                                            <IconButton
                                                                                size="small"
                                                                                onClick={() => {
                                                                                    const data = detailedResults[item.filename];
                                                                                    const toCopy = { variants: data.variants, configuration: data.configuration };
                                                                                    navigator.clipboard.writeText(JSON.stringify(toCopy, null, 2)).then(
                                                                                        () => console.log('Results copied to clipboard'),
                                                                                        () => console.warn('Failed to copy')
                                                                                    );
                                                                                }}
                                                                            >
                                                                                <ContentCopy />
                                                                            </IconButton>
                                                                        </Tooltip>
                                                                    </Box>
                                                                    <TableContainer sx={{ maxHeight: 300, mb: 2 }}>
                                                                        <Table size="small" stickyHeader>
                                                                            <TableHead>
                                                                                <TableRow>
                                                                                    <TableCell>#</TableCell>
                                                                                    <TableCell>Variants</TableCell>
                                                                                    <TableCell>Sharpe</TableCell>
                                                                                    <TableCell>Profit Factor</TableCell>
                                                                                    <TableCell>Max DD</TableCell>
                                                                                    <TableCell>Trades</TableCell>
                                                                                    <TableCell>Win Rate</TableCell>
                                                                                    <TableCell>PnL</TableCell>
                                                                                    <TableCell align="right">Actions</TableCell>
                                                                                </TableRow>
                                                                            </TableHead>
                                                                            <TableBody>
                                                                                {detailedResults[item.filename].variants.slice(0, 30).map((v: any, i: number) => {
                                                                                    const wr = v.win_rate;
                                                                                    const winRateStr = wr != null ? (wr > 1 ? `${wr.toFixed(1)}%` : `${(wr * 100).toFixed(1)}%`) : '-';
                                                                                    return (
                                                                                    <TableRow key={i} sx={i === 0 ? { bgcolor: 'rgba(76, 175, 80, 0.15)' } : undefined}>
                                                                                        <TableCell>{i + 1}</TableCell>
                                                                                        <TableCell sx={{ maxWidth: 150 }} title={JSON.stringify(v.params)}>{formatVariantParamsShort(v.params)}</TableCell>
                                                                                        <TableCell>{v.sharpe_ratio?.toFixed(2) ?? '-'}</TableCell>
                                                                                        <TableCell>{v.profit_factor?.toFixed(2) ?? '-'}</TableCell>
                                                                                        <TableCell>{v.max_drawdown?.toFixed(2) ?? '-'}%</TableCell>
                                                                                        <TableCell>{v.total_trades ?? '-'}</TableCell>
                                                                                        <TableCell>{winRateStr}</TableCell>
                                                                                        <TableCell>${v.total_pnl?.toFixed(2) ?? '-'}</TableCell>
                                                                                        <TableCell align="right">
                                                                                            <Button size="small" startIcon={<FileCopyOutlined />} onClick={(e) => handleVariantSaveClick(e, v, item)}>Save</Button>
                                                                                        </TableCell>
                                                                                    </TableRow>
                                                                                    );
                                                                                })}
                                                                            </TableBody>
                                                                        </Table>
                                                                    </TableContainer>
                                                                    {detailedResults[item.filename].variants.length > 30 && <Typography variant="caption">Showing top 30 of {detailedResults[item.filename].variants.length}</Typography>}
                                                                </Box>
                                                            )}
                                                            <Box sx={{ display: 'flex', gap: 4, mb: 2, flexWrap: 'wrap' }}>
                                                                <Box sx={{ minWidth: 200, maxWidth: 250 }}>
                                                                    <Typography variant="subtitle2" gutterBottom color="primary">Key Metrics</Typography>
                                                                    <Typography variant="body2">Initial Capital: ${(item.initial_capital ?? 0).toLocaleString()}</Typography>
                                                                    <Typography variant="body2">Profit Factor: {item.profit_factor != null ? item.profit_factor.toFixed(2) : 'N/A'}</Typography>
                                                                    <Typography variant="body2">Sharpe Ratio: {item.sharpe_ratio?.toFixed(2) || 'N/A'}</Typography>
                                                                    <Typography variant="body2">Total Trades: {item.total_trades}</Typography>
                                                                    <Typography variant="body2" sx={{ color: 'green' }}>Wins: {item.winning_trades} (Avg: ${item.avg_win?.toFixed(2)})</Typography>
                                                                    <Typography variant="body2" sx={{ color: 'red' }}>Losses: {item.losing_trades} (Avg: ${item.avg_loss?.toFixed(2)})</Typography>

                                                                    <Box sx={{ mt: 2 }}>
                                                                        <Typography variant="subtitle2" gutterBottom color="primary">General Settings</Typography>
                                                                        {item.is_live && (item.session_start || item.session_end) && (
                                                                            <Box sx={{ mb: 1, p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                                                                                <Typography variant="body2" sx={{ fontSize: '0.8rem', fontWeight: 'bold', color: 'primary.main', mb: 0.5 }}>
                                                                                    📅 Session Period
                                                                                </Typography>
                                                                                {item.session_start && (
                                                                                    <Typography variant="body2" sx={{ fontSize: '0.78rem', color: 'text.secondary' }}>
                                                                                        Start: {formatDate(item.session_start)}
                                                                                    </Typography>
                                                                                )}
                                                                                {item.session_end && (
                                                                                    <Typography variant="body2" sx={{ fontSize: '0.78rem', color: 'text.secondary' }}>
                                                                                        End: {formatDate(item.session_end)}
                                                                                    </Typography>
                                                                                )}
                                                                                {item.session_duration_mins != null && (
                                                                                    <Typography variant="body2" sx={{ fontSize: '0.78rem', color: 'text.secondary' }}>
                                                                                        Duration: {formatLiveDuration(item.session_duration_mins)}
                                                                                    </Typography>
                                                                                )}
                                                                                {getConfigValue(item.configuration, 'exchange') && (
                                                                                    <Typography variant="body2" sx={{ fontSize: '0.78rem', color: 'text.secondary' }}>
                                                                                        Exchange: <span style={{ textTransform: 'capitalize' }}>{String(getConfigValue(item.configuration, 'exchange'))}</span>
                                                                                    </Typography>
                                                                                )}
                                                                            </Box>
                                                                        )}
                                                                        {GENERAL_SETTINGS.filter(s => !(item.is_live && (s.key === "start_date" || s.key === "end_date"))).map((setting) => {
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
                                                                        {expandedForChart[item.filename] ? (
                                                                            <TradeAnalysisChart
                                                                                key={item.filename}
                                                                                trades={detailedResults[item.filename].trades}
                                                                                onTradeClick={(t) => handleTradeClick(t, detailedResults[item.filename], !!item.is_live)}
                                                                                height={200}
                                                                            />
                                                                        ) : (
                                                                            <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                                                                <CircularProgress size={24} />
                                                                            </Box>
                                                                        )}
                                                                    </Box>
                                                                ) : (
                                                                    <Typography variant="body2" color="textSecondary">No trade data available.</Typography>
                                                                )}
                                                            </Box>
                                                            <Box sx={{ mt: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
                                                                <Typography variant="caption" display="block" color="textSecondary">
                                                                    Session ID: {item.filename?.replace(/\.json$/i, '') ?? item.filename}
                                                                </Typography>
                                                                <IconButton
                                                                    size="small"
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        const id = item.filename?.replace(/\.json$/i, '') ?? item.filename;
                                                                        navigator.clipboard.writeText(id);
                                                                    }}
                                                                    title="Copy Session ID (use as _id in MongoDB)"
                                                                    sx={{ p: 0.25 }}
                                                                >
                                                                    <FileCopyOutlined sx={{ fontSize: 14 }} />
                                                                </IconButton>
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

                <Dialog open={saveDialogOpen} onClose={() => { setSaveDialogOpen(false); setItemToSave(null); setVariantToSave(null); }} PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#fff' } }}>
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
                        <DialogContentText sx={{ color: '#aaa' }}>Are you sure you want to delete this run? This action cannot be undone.</DialogContentText>
                    </DialogContent>
                    <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                        <Button onClick={() => setDeleteDialogOpen(false)} sx={{ color: '#aaa' }}>Cancel</Button>
                        <Button onClick={handleDeleteConfirm} color="error" variant="contained">Delete</Button>
                    </DialogActions>
                </Dialog>

                <TradeDetailsModal
                    open={isTradeModalOpen}
                    onClose={() => setIsTradeModalOpen(false)}
                    selectedTrade={selectedTrade}
                    trades={tradeModalTrades}
                    onSelectTrade={setSelectedTrade}
                    symbol={tradeModalConfig?.symbol ?? 'BTC/USDT'}
                    timeframes={tradeModalConfig?.timeframes ?? ['1h']}
                    strategyConfig={tradeModalConfig?.strategyConfig ?? {}}
                    exchangeType={tradeModalConfig?.exchangeType ?? 'future'}
                    backtestStart={tradeModalConfig?.backtestStart}
                    backtestEnd={tradeModalConfig?.backtestEnd}
                />
            </CardContent>
        </Card>
    );
};

export default BacktestHistoryList;
