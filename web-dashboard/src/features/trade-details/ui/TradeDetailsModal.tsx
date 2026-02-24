import React, { lazy, Suspense, useEffect, useState, useMemo } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Box,
    Typography,
    Chip,
    Grid,
    Paper,
    Stack,
    Divider,
    Button,
    CircularProgress
} from '@mui/material';
import { InfoOutlined } from '@mui/icons-material';
import MuiTooltip from '@mui/material/Tooltip';
import { API_BASE } from '../../../shared/api/config';

const TradeOHLCVChart = lazy(() => import('../../../entities/trade/ui/TradeOHLCVChart'));

interface TradeDetailsModalProps {
    open: boolean;
    onClose: () => void;
    selectedTrade: any | null;
    symbol?: string;
    timeframes?: string[];
    strategyConfig?: Record<string, any>;
    exchangeType?: string;
    backtestStart?: string;
    backtestEnd?: string;
}

function timeframeToMinutes(tf: string): number {
    const map: Record<string, number> = {
        '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
        '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720,
        '1d': 1440, '3d': 4320, '1w': 10080,
    };
    return map[tf] ?? 60;
}

function pickSmallestTimeframe(timeframes: string[]): string {
    if (!timeframes || timeframes.length === 0) return '1h';
    return timeframes.slice().sort((a, b) => timeframeToMinutes(a) - timeframeToMinutes(b))[0];
}

function pickLargestTimeframe(timeframes: string[]): string | undefined {
    if (!timeframes || timeframes.length <= 1) return undefined;
    return timeframes.slice().sort((a, b) => timeframeToMinutes(b) - timeframeToMinutes(a))[0];
}

function toIso(str: string | null | undefined): string {
    if (!str) return '';
    const s = str.replace(' ', 'T').split('.')[0];
    if (!s.endsWith('Z') && !s.includes('+')) return s + 'Z';
    return s;
}

function valueAtTime(series: Array<{ time: string; value: number }> | undefined, targetIso: string): number | null {
    if (!series?.length || !targetIso) return null;
    const targetMs = new Date(targetIso).getTime();
    let best: { time: string; value: number } | null = null;
    let bestDiff = Infinity;
    for (const p of series) {
        const diff = Math.abs(new Date(p.time).getTime() - targetMs);
        if (diff < bestDiff) { bestDiff = diff; best = p; }
    }
    return best ? best.value : null;
}

const TradeDetailsModal: React.FC<TradeDetailsModalProps> = ({
    open,
    onClose,
    selectedTrade,
    symbol = 'BTC/USDT',
    timeframes = ['1h'],
    strategyConfig = {},
    exchangeType = 'future',
    backtestStart,
    backtestEnd,
}) => {
    const chartTimeframe = pickSmallestTimeframe(timeframes);
    const emaTimeframe = pickLargestTimeframe(timeframes);
    const indParams = useMemo(() => {
        const cfg = strategyConfig;
        const hasConfig = cfg && Object.keys(cfg).length > 0;
        const useDefaults = !hasConfig;
        return {
            emaPeriod: useDefaults || cfg?.use_trend_filter ? (cfg?.trend_ema_period ?? 200) : 0,
            rsiPeriod: useDefaults || cfg?.use_rsi_filter ? (cfg?.rsi_period ?? 14) : 0,
            adxPeriod: useDefaults || cfg?.use_adx_filter ? (cfg?.adx_period ?? 14) : 0,
            atrPeriod: cfg?.atr_period ?? 14,
        };
    }, [strategyConfig]);

    const [indicatorsAtExitFallback, setIndicatorsAtExitFallback] = useState<Record<string, number> | null>(null);
    const [indicatorsAtExitLoading, setIndicatorsAtExitLoading] = useState(false);

    useEffect(() => {
        const needFetch = open && selectedTrade?.exit_time &&
            !selectedTrade?.exit_context?.indicators_at_exit &&
            (indParams.emaPeriod > 0 || indParams.rsiPeriod > 0 || indParams.adxPeriod > 0 || indParams.atrPeriod > 0);

        if (!needFetch) {
            setIndicatorsAtExitFallback(null);
            return;
        }

        let cancelled = false;
        setIndicatorsAtExitLoading(true);
        setIndicatorsAtExitFallback(null);

        const exitIso = toIso(selectedTrade.exit_time);
        const exitDate = new Date(exitIso);
        const startDate = new Date(exitDate.getTime() - 72 * 60 * 60 * 1000);
        const endDate = new Date(exitDate.getTime() + 2 * 60 * 60 * 1000);
        const startIso = startDate.toISOString().split('.')[0] + 'Z';
        const endIso = endDate.toISOString().split('.')[0] + 'Z';

        const params = new URLSearchParams({
            symbol,
            timeframe: chartTimeframe,
            start: startIso,
            end: endIso,
            context_bars: '25',
            exchange_type: exchangeType || 'future',
            ema_period: String(indParams.emaPeriod),
            ...(emaTimeframe ? { ema_timeframe: emaTimeframe } : {}),
            rsi_period: String(indParams.rsiPeriod),
            rsi_overbought: '70',
            rsi_oversold: '30',
            adx_period: String(indParams.adxPeriod),
            adx_threshold: '25',
            atr_period: String(indParams.atrPeriod),
            ...(backtestStart ? { backtest_start: backtestStart } : {}),
            ...(backtestEnd ? { backtest_end: backtestEnd } : {}),
        });

        fetch(`${API_BASE}/api/ohlcv?${params}`)
            .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
            .then((d: { candles?: Array<{ time: string }>; indicators?: Record<string, { values?: Array<{ time: string; value: number }>; period?: number }> }) => {
                if (cancelled) return;
                const ind: Record<string, number> = {};
                const indicators = d?.indicators ?? {};
                if (indicators.atr?.values?.length) {
                    const v = valueAtTime(indicators.atr.values, exitIso);
                    if (v != null) ind['ATR'] = Math.round(v * 10000) / 10000;
                }
                if (indicators.ema?.values?.length && indParams.emaPeriod > 0) {
                    const v = valueAtTime(indicators.ema.values, exitIso);
                    if (v != null) ind[`EMA_${indParams.emaPeriod}`] = Math.round(v * 100) / 100;
                }
                if (indicators.rsi?.values?.length && indParams.rsiPeriod > 0) {
                    const v = valueAtTime(indicators.rsi.values, exitIso);
                    if (v != null) ind['RSI'] = Math.round(v * 10) / 10;
                }
                if (indicators.adx?.values?.length && indParams.adxPeriod > 0) {
                    const v = valueAtTime(indicators.adx.values, exitIso);
                    if (v != null) ind['ADX'] = Math.round(v * 10) / 10;
                }
                setIndicatorsAtExitFallback(Object.keys(ind).length ? ind : null);
            })
            .catch(() => { if (!cancelled) setIndicatorsAtExitFallback(null); })
            .finally(() => { if (!cancelled) setIndicatorsAtExitLoading(false); });

        return () => { cancelled = true; };
    }, [open, selectedTrade?.exit_time, selectedTrade?.exit_context?.indicators_at_exit, symbol, chartTimeframe, emaTimeframe, exchangeType, backtestStart, backtestEnd, indParams]);

    return (
        <Dialog
            open={open}
            onClose={onClose}
            maxWidth="lg"
            fullWidth
            PaperProps={{
                sx: { bgcolor: '#1e1e1e', color: '#fff' }
            }}
        >
            {selectedTrade && (
                <>
                    <DialogTitle component="div" sx={{ borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Box display="flex" alignItems="center" gap={2}>
                            <Typography variant="h6">Trade #{selectedTrade.id}</Typography>
                            <Chip
                                label={selectedTrade.direction?.toUpperCase()}
                                color={selectedTrade.direction === 'LONG' ? 'success' : 'error'}
                                size="small"
                                variant="outlined"
                            />
                            <Chip
                                label={selectedTrade.pnl >= 0 ? "WIN" : "LOSS"}
                                color={selectedTrade.pnl >= 0 ? "success" : "error"}
                                size="small"
                            />
                        </Box>
                        <Typography variant="h5" color={selectedTrade.pnl >= 0 ? "success.main" : "error.main"}>
                            {selectedTrade.pnl >= 0 ? "+" : ""}${selectedTrade.pnl?.toFixed(2)} ({selectedTrade.pnl_percent?.toFixed(2)}%)
                        </Typography>
                    </DialogTitle>
                    <DialogContent sx={{ mt: 2 }}>
                        <Grid container spacing={3}>

                            <Grid item xs={12}>
                                <Paper variant="outlined" sx={{ p: 0, bgcolor: '#181818', borderColor: '#333', overflow: 'hidden' }}>
                                    <Typography
                                        variant="caption"
                                        sx={{ color: '#fff', opacity: 0.6, display: 'block', px: 2, pt: 1.5, pb: 0.5 }}
                                    >
                                        PRICE CHART · {symbol} · {chartTimeframe.toUpperCase()}
                                    </Typography>
                                    <Suspense fallback={
                                        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 420 }}>
                                            <CircularProgress size={28} />
                                        </Box>
                                    }>
                                        <TradeOHLCVChart
                                            trade={selectedTrade}
                                            symbol={symbol}
                                            timeframe={chartTimeframe}
                                            emaTimeframe={emaTimeframe}
                                            strategyConfig={strategyConfig}
                                            exchangeType={exchangeType}
                                            backtestStart={backtestStart}
                                            backtestEnd={backtestEnd}
                                            height={420}
                                        />
                                    </Suspense>
                                </Paper>
                            </Grid>

                            <Grid item xs={12}>
                                <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderColor: '#333' }}>
                                    <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">PnL CALCULATION</Typography>

                                    {(() => {
                                        const isLong = selectedTrade.direction === 'LONG';
                                        const exitPrice = selectedTrade.exit_price || 0;
                                        const entryPrice = selectedTrade.entry_price || 0;
                                        const size = selectedTrade.size || 0;
                                        const commission = selectedTrade.commission || 0;

                                        const priceDiff = isLong ? (exitPrice - entryPrice) : (entryPrice - exitPrice);
                                        const grossPnl = priceDiff * size;
                                        const pnlColor = grossPnl >= 0 ? '#4caf50' : '#f44336';

                                        return (
                                            <Box sx={{ fontFamily: 'Monospace', fontSize: '0.9rem', color: '#ccc' }}>
                                                <Box display="flex" justifyContent="space-between" mb={1}>
                                                    <span>Formula:</span>
                                                    <span style={{ color: '#aaa' }}>
                                                        ({isLong ? 'Exit' : 'Entry'} - {isLong ? 'Entry' : 'Exit'}) × Size - Comm
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between">
                                                    <span>Price Diff:</span>
                                                    <span>
                                                        ({isLong ? exitPrice.toFixed(2) : entryPrice.toFixed(2)} - {isLong ? entryPrice.toFixed(2) : exitPrice.toFixed(2)}) × {size.toFixed(4)}
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between" sx={{ borderBottom: '1px solid #444', pb: 1, mb: 1 }}>
                                                    <span>Gross PnL:</span>
                                                    <span style={{ color: pnlColor }}>
                                                        {grossPnl >= 0 ? '+' : ''}{grossPnl.toFixed(2)}
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between">
                                                    <span>Commission:</span>
                                                    <span style={{ color: '#f44336' }}>
                                                        -{commission.toFixed(2)}
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between" sx={{ borderTop: '1px solid #555', pt: 1, mt: 1, fontWeight: 'bold' }}>
                                                    <span>Net PnL:</span>
                                                    <span style={{ color: selectedTrade.pnl >= 0 ? '#4caf50' : '#f44336' }}>
                                                        {selectedTrade.pnl >= 0 ? '+' : ''}{selectedTrade.pnl?.toFixed(2)}
                                                    </span>
                                                </Box>
                                            </Box>
                                        );
                                    })()}
                                </Paper>
                            </Grid>

                            <Grid item xs={12} md={6}>
                                <Stack spacing={2}>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">ENTRY TIME</Typography>
                                        <Typography variant="body1">{selectedTrade.entry_time ? new Date(selectedTrade.entry_time).toLocaleString() : 'N/A'}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">ENTRY PRICE</Typography>
                                        <Typography variant="body1">${selectedTrade.entry_price?.toFixed(2)}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">SIZE</Typography>
                                        <Typography variant="body1">{selectedTrade.size?.toFixed(4)}</Typography>
                                    </Box>
                                </Stack>
                            </Grid>

                            <Grid item xs={12} md={6}>
                                <Stack spacing={2}>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">EXIT TIME</Typography>
                                        <Typography variant="body1">{selectedTrade.exit_time ? new Date(selectedTrade.exit_time).toLocaleString() : 'N/A'}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">EXIT PRICE</Typography>
                                        <Typography variant="body1">${selectedTrade.exit_price?.toFixed(2)}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">DURATION</Typography>
                                        <Typography variant="body1">
                                            {(() => {
                                                if (!selectedTrade.duration) return 'N/A';
                                                if (selectedTrade.duration.includes('day')) {
                                                    return selectedTrade.duration.split('.')[0];
                                                }
                                                const parts = selectedTrade.duration.split(':');
                                                if (parts.length >= 2) {
                                                    const h = parseInt(parts[0]);
                                                    const m = parseInt(parts[1]);
                                                    return `${h}h ${m}m`;
                                                }
                                                return selectedTrade.duration;
                                            })()}
                                        </Typography>
                                    </Box>
                                </Stack>
                            </Grid>

                            <Grid item xs={12}>
                                <Divider sx={{ borderColor: '#333', my: 1 }} />
                            </Grid>

                            <Grid item xs={6} md={3}>
                                <Typography variant="caption" color="gray">INITIAL STOP LOSS</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="body2">
                                        ${selectedTrade.stop_loss?.toFixed(2)}
                                    </Typography>
                                    <MuiTooltip
                                        title={<span style={{ whiteSpace: 'pre-wrap' }}>{selectedTrade.sl_calculation || "Calculation details not available"}</span>}
                                        arrow
                                        placement="top"
                                    >
                                        <InfoOutlined fontSize="small" sx={{ cursor: 'help', width: 16, height: 16, color: '#2196f3' }} />
                                    </MuiTooltip>
                                </Box>
                            </Grid>
                            <Grid item xs={6} md={3}>
                                <Typography variant="caption" color="gray">INITIAL TAKE PROFIT</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="body2">
                                        ${selectedTrade.take_profit?.toFixed(2)}
                                    </Typography>
                                    <MuiTooltip
                                        title={<span style={{ whiteSpace: 'pre-wrap' }}>{selectedTrade.tp_calculation || "Calculation details not available"}</span>}
                                        arrow
                                        placement="top"
                                    >
                                        <InfoOutlined fontSize="small" sx={{ cursor: 'help', width: 16, height: 16, color: '#2196f3' }} />
                                    </MuiTooltip>
                                </Box>
                            </Grid>
                            <Grid item xs={6} md={3}>
                                <Typography variant="caption" color="gray">COMMISSION</Typography>
                                <Typography variant="body2">${selectedTrade.commission?.toFixed(2) || '0.00'}</Typography>
                            </Grid>
                            <Grid item xs={12} md={3}>
                                <Typography variant="caption" color="gray">EXIT REASON</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="body2" sx={{
                                        color: selectedTrade.exit_reason === 'Take Profit' ? '#4caf50' :
                                            selectedTrade.exit_reason === 'Stop Loss' ? '#f44336' : 'white'
                                    }}>
                                        {selectedTrade.exit_reason || 'Unknown'}
                                    </Typography>
                                    {selectedTrade.sl_history && selectedTrade.sl_history.length > 0 && (
                                        <MuiTooltip
                                            title={
                                                <Box sx={{ p: 0.5, maxHeight: '300px', overflowY: 'auto' }}>
                                                    <Typography variant="subtitle2" sx={{ borderBottom: '1px solid rgba(255,255,255,0.2)', mb: 1, pb: 0.5 }}>
                                                        Trailing Stop History
                                                    </Typography>
                                                    {selectedTrade.sl_history.map((h: any, i: number) => {
                                                        const isFirst = i === 0;
                                                        const isLast = i === selectedTrade.sl_history.length - 1;

                                                        return (
                                                            <Box key={i} sx={{ mb: 1, '&:last-child': { mb: 0 } }}>
                                                                <Typography
                                                                    variant="caption"
                                                                    display="block"
                                                                    sx={{
                                                                        color: isFirst ? '#90caf9' : isLast ? '#a5d6a7' : '#b0bec5',
                                                                        fontWeight: (isFirst || isLast) ? 'bold' : 'normal'
                                                                    }}
                                                                >
                                                                    {h.reason}
                                                                </Typography>
                                                                <Typography
                                                                    variant="body2"
                                                                    sx={{
                                                                        fontFamily: 'monospace',
                                                                        color: (isFirst || isLast) ? 'white' : 'inherit',
                                                                        fontWeight: (isFirst || isLast) ? 'bold' : 'normal'
                                                                    }}
                                                                >
                                                                    ${h.price.toFixed(2)}
                                                                </Typography>
                                                            </Box>
                                                        );
                                                    })}
                                                </Box>
                                            }
                                            arrow
                                            placement="top"
                                        >
                                            <InfoOutlined fontSize="small" sx={{ cursor: 'help', width: 16, height: 16, color: '#2196f3' }} />
                                        </MuiTooltip>
                                    )}
                                </Box>
                            </Grid>

                            <Grid item xs={12} sx={{ mt: 2 }}>
                                <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: 1, borderLeft: '3px solid #64b5f6' }}>
                                    <Typography variant="subtitle2" color="#64b5f6" gutterBottom>
                                        TRADE ANALYSIS
                                    </Typography>
                                    {selectedTrade.narrative && (
                                        <Typography variant="body2" color="#e0e0e0" sx={{ fontStyle: 'italic', mb: 2 }}>
                                            "{selectedTrade.narrative}"
                                        </Typography>
                                    )}

                                    <Box sx={{ pt: 2, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                                        <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">ENTRY</Typography>
                                        {(() => {
                                            const sig = selectedTrade.entry_context?.indicators_at_entry ?? {};
                                            const exec = selectedTrade.execution_bar_indicators ?? {};
                                            const parts: string[] = [];
                                            for (const k of ['RSI', 'ADX']) {
                                                const s = sig[k], e = exec[k];
                                                if (s != null && e != null) parts.push(`${k} ${s}→${e}`);
                                            }
                                            return parts.length > 0 ? (
                                                <Typography variant="body2" sx={{ color: '#81c784', mb: 1, fontSize: '0.85rem' }}>
                                                    Signal (N) → execution (N+1): {parts.join(', ')}
                                                </Typography>
                                            ) : null;
                                        })()}
                                        <Typography variant="body2" color="#e0e0e0" sx={{ mb: 1 }}>
                                            {selectedTrade.reason || 'No specific reason recorded'}
                                        </Typography>
                                        {selectedTrade.entry_context?.why_entry?.length > 0 && (
                                            <Box component="ul" sx={{ m: 0, pl: 2.5, color: '#b0bec5', fontSize: '0.85rem', mb: 1 }}>
                                                {selectedTrade.entry_context.why_entry.map((line: string, i: number) => (
                                                    <li key={i}>{line}</li>
                                                ))}
                                            </Box>
                                        )}
                                        {selectedTrade.entry_context?.indicators_at_entry && Object.keys(selectedTrade.entry_context.indicators_at_entry).length > 0 && (
                                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 2 }}>
                                                {Object.entries(selectedTrade.entry_context.indicators_at_entry).map(([k, v]) => {
                                                    const disp = k.startsWith('EMA') ? `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(v);
                                                    return (
                                                        <Chip key={k} size="small" label={`${k}: ${disp}`} sx={{ fontSize: '0.75rem', height: 22, bgcolor: 'rgba(66,165,245,0.15)', color: '#90caf9', border: '1px solid rgba(66,165,245,0.3)' }} />
                                                    );
                                                })}
                                            </Box>
                                        )}

                                        <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block" style={{ marginTop: 12 }}>EXIT</Typography>
                                        <Typography variant="body2" color="#e0e0e0" sx={{ mb: 1 }}>
                                            {selectedTrade.exit_reason || 'Unknown'}
                                        </Typography>
                                        <Box component="ul" sx={{ m: 0, pl: 2.5, color: '#b0bec5', fontSize: '0.85rem', mb: 1 }}>
                                            {selectedTrade.exit_context?.why_exit?.length ? (
                                                selectedTrade.exit_context.why_exit.map((line: string, i: number) => <li key={i}>{line}</li>)
                                            ) : (
                                                <li>Exit: {selectedTrade.exit_reason || 'Unknown'} — no detailed context for this historical run.</li>
                                            )}
                                        </Box>
                                        {(() => {
                                            const exitInd = selectedTrade.exit_context?.indicators_at_exit ?? indicatorsAtExitFallback;
                                            return exitInd && Object.keys(exitInd).length > 0 ? (
                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
                                                    {Object.entries(exitInd).map(([k, v]) => {
                                                        const disp = k.startsWith('EMA') ? `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(v);
                                                        return (
                                                            <Chip key={k} size="small" label={`${k}: ${disp}`} sx={{ fontSize: '0.75rem', height: 22, bgcolor: 'rgba(255,152,0,0.15)', color: '#ffb74d', border: '1px solid rgba(255,152,0,0.3)' }} />
                                                        );
                                                    })}
                                                </Box>
                                            ) : indicatorsAtExitLoading ? (
                                                    <CircularProgress size={14} sx={{ color: '#ffb74d' }} />
                                                ) : null;
                                        })()}
                                    </Box>

                                    {selectedTrade.metadata && Object.keys(selectedTrade.metadata).length > 0 && (
                                        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                                            <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">ADDITIONAL CONTEXT</Typography>
                                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                                                {Object.entries(selectedTrade.metadata).map(([key, value]) => (
                                                    <Chip
                                                        key={key}
                                                        size="small"
                                                        label={`${key.replace(/_/g, ' ')}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`}
                                                        sx={{ fontSize: '0.75rem', bgcolor: 'rgba(255,255,255,0.08)', color: '#b0bec5', border: '1px solid rgba(255,255,255,0.1)' }}
                                                    />
                                                ))}
                                            </Box>
                                        </Box>
                                    )}
                                </Box>
                            </Grid>
                        </Grid>
                    </DialogContent>
                    <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                        <Button onClick={onClose} color="inherit">Close</Button>
                    </DialogActions>
                </>
            )}
        </Dialog>
    );
};

export default TradeDetailsModal;
