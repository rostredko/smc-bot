import React, { useMemo, useCallback, useState, lazy, Suspense } from 'react';
import { Box, Card, CardHeader, CardContent, Grid, Paper, Typography, TableContainer, Table, TableHead, TableRow, TableCell, TableBody, Button, IconButton, Tooltip as MuiTooltip, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, TextField } from '@mui/material';
import { FileCopyOutlined, ContentCopy } from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useResultsContext } from '../../../app/providers/results/ResultsProvider';
import { CustomTooltip, CustomPieTooltip } from '../../../shared/ui/ChartTooltips';
import { formatVariantParamsShort, variantParamsToTemplateName } from '../../../shared/lib/formatVariantParams';
import TradeAnalysisChart from '../../../entities/trade/ui/TradeAnalysisChart';
const TradeDetailsModal = lazy(() => import('../../../features/trade-details/ui/TradeDetailsModal'));

const toFiniteNumber = (value: number | null | undefined): number | null => {
    if (value == null) return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
};

const metricDecimals = (value: number): number => {
    const abs = Math.abs(value);
    if (abs === 0) return 2;
    if (abs >= 1) return 2;
    if (abs >= 0.1) return 3;
    if (abs >= 0.01) return 4;
    return 6;
};

const formatMetric = (value: number | null | undefined): string => {
    const numeric = toFiniteNumber(value);
    if (numeric == null) return '-';
    return numeric.toFixed(metricDecimals(numeric));
};

const formatCurrency = (value: number | null | undefined): string => {
    const numeric = toFiniteNumber(value);
    if (numeric == null) return '-';
    const sign = numeric < 0 ? '-' : '';
    return `${sign}$${Math.abs(numeric).toFixed(metricDecimals(numeric))}`;
};

const formatPercent = (value: number | null | undefined): string => {
    const numeric = toFiniteNumber(value);
    if (numeric == null) return '-';
    return `${numeric.toFixed(metricDecimals(numeric))}%`;
};

const formatWinRatePercent = (value: number | null | undefined): string => {
    const numeric = toFiniteNumber(value);
    if (numeric == null) return '-';
    const pct = numeric * 100;
    return `${pct.toFixed(metricDecimals(pct))}%`;
};

const MemoizedLineChart = React.memo(({ data }: { data: any[] }) => (
    <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Line type="monotone" dataKey="equity" stroke="#8884d8" strokeWidth={2} isAnimationActive={false} />
        </LineChart>
    </ResponsiveContainer>
));

const MemoizedPieChart = React.memo(({ data }: { data: any[] }) => (
    <ResponsiveContainer width="100%" height={300}>
        <PieChart>
            <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
                isAnimationActive={false}
            >
                {data.map((entry: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
            </Pie>
            <Tooltip content={<CustomPieTooltip />} />
        </PieChart>
    </ResponsiveContainer>
));

const ResultsPanel: React.FC = () => {
    const { results, backtestStatus, equityData, pieData, handleBarClick, selectedTrade, setSelectedTrade, isTradeModalOpen, setIsTradeModalOpen } = useResultsContext();
    // useMemo must run before early return (rules of hooks)
    const chartSymbol = useMemo(
        () => results?.configuration?.symbol ?? 'BTC/USDT',
        [results?.configuration]
    );
    const chartTimeframes = useMemo(
        () => results?.configuration?.timeframes ?? ['1h'],
        [results?.configuration]
    );
    const chartStrategyConfig = useMemo(
        () => results?.configuration?.strategy_config ?? {},
        [results?.configuration]
    );
    const isLiveResult = useMemo(
        () => Boolean((results as any)?.is_live || (results as any)?.session_start || (results as any)?.session_end),
        [results]
    );
    const exchangeType = useMemo(
        () => results?.configuration?.exchange_type ?? 'future',
        [results?.configuration]
    );
    const backtestStart = useMemo(
        () => isLiveResult ? undefined : (results?.configuration?.start_date ?? undefined),
        [isLiveResult, results?.configuration]
    );
    const backtestEnd = useMemo(
        () => isLiveResult ? undefined : (results?.configuration?.end_date ?? undefined),
        [isLiveResult, results?.configuration]
    );

    const isOptimization = (results as any)?.run_mode === 'optimize' && Array.isArray((results as any)?.variants) && (results as any).variants.length > 0;
    const variants = (results as any)?.variants ?? [];

    const [saveDialogOpen, setSaveDialogOpen] = useState(false);
    const [variantToSave, setVariantToSave] = useState<any>(null);
    const [saveTemplateName, setSaveTemplateName] = useState('');
    const [saveError, setSaveError] = useState('');

    const buildConfigFromVariant = useCallback((variant: any) => {
        const cfg = results?.configuration ?? {};
        const params = variant.params || {};
        const baseSt = cfg.strategy_config ?? {};
        const tf = variant.timeframe ? variant.timeframe.split('/') : cfg.timeframes;
        // Strip any list values from base (opt config has risk_reward_ratio: [1.5,2,2.5]) and override with variant scalars
        const cleanBase: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(baseSt)) {
            cleanBase[k] = Array.isArray(v) && params[k] !== undefined ? params[k] : v;
        }
        const strategyConfig = { ...cleanBase, ...params };
        const toSave: any = {
            ...cfg,
            strategy_config: strategyConfig,
            timeframes: tf || cfg.timeframes,
        };
        if (typeof params.trailing_stop_distance === 'number') {
            toSave.trailing_stop_distance = params.trailing_stop_distance;
        }
        // Single-run config: strip optimize fields so loaded template runs as single
        delete toSave.run_mode;
        delete toSave.opt_params;
        delete toSave.opt_target_metric;
        delete toSave.opt_timeframes;
        toSave.run_mode = 'single';
        return toSave;
    }, [results?.configuration]);

    const handleSaveClick = (variant: any) => {
        setVariantToSave(variant);
        setSaveTemplateName(variantParamsToTemplateName(variant.params) || '');
        setSaveError('');
        setSaveDialogOpen(true);
    };

    const handleSaveConfirm = async () => {
        if (!variantToSave || !saveTemplateName.trim() || !/^[a-zA-Z0-9_-]+$/.test(saveTemplateName)) {
            setSaveError('Invalid name. Use only letters, numbers, dashes, and underscores.');
            return;
        }
        try {
            const { saveUserConfigTemplate } = await import('../../backtest-history/api/historyApi');
            await saveUserConfigTemplate(saveTemplateName.trim(), buildConfigFromVariant(variantToSave));
            setSaveDialogOpen(false);
            setVariantToSave(null);
        } catch (e: any) {
            setSaveError(e?.message || 'Failed to save template.');
        }
    };

    const handleCopyResultsToJson = useCallback(() => {
        if (!results) return;
        const base = isOptimization
            ? { variants: (results as any).variants, configuration: results.configuration }
            : { ...results, trades: results.trades ?? [] };
        const toCopy = {
            run_id: backtestStatus?.run_id ?? (results as any)?.run_id,
            loaded_template_name: results?.configuration?.loaded_template_name,
            ...base,
        };
        const json = JSON.stringify(toCopy, null, 2);
        navigator.clipboard.writeText(json).then(
            () => console.log('Results copied to clipboard'),
            () => console.warn('Failed to copy')
        );
    }, [results, isOptimization, backtestStatus?.run_id]);

    if (!results) return null;

    return (
        <>
            {isOptimization && variants[0] && (
                <Grid item xs={12} mt={3}>
                    <Card>
                        <CardHeader
                            title={`Optimization Results (${variants.length} variants)`}
                            subheader={
                                <Typography component="span" variant="body2" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
                                    Best: {formatVariantParamsShort(variants[0].params)} · Sharpe {formatMetric(variants[0].sharpe_ratio)}, PF {formatMetric(variants[0].profit_factor)}, Max DD {formatPercent(variants[0].max_drawdown)}, Trades {variants[0].total_trades ?? '-'}, Win Rate {variants[0].win_rate != null ? (variants[0].win_rate > 1 ? `${variants[0].win_rate.toFixed(1)}%` : `${(variants[0].win_rate * 100).toFixed(1)}%`) : '-'}, PnL {formatCurrency(variants[0].total_pnl)}
                                </Typography>
                            }
                            action={
                                <MuiTooltip title="Copy results to JSON">
                                    <IconButton onClick={handleCopyResultsToJson} size="small" color="primary">
                                        <ContentCopy />
                                    </IconButton>
                                </MuiTooltip>
                            }
                        />
                        <CardContent>
                            <TableContainer>
                                <Table size="small">
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>#</TableCell>
                                            {variants.some((v: any) => v.timeframe) && <TableCell>TF</TableCell>}
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
                                        {variants.slice(0, 50).map((v: any, i: number) => {
                                            const paramStr = formatVariantParamsShort(v.params);
                                            const seenBefore = variants.slice(0, i).some((prev: any) => formatVariantParamsShort(prev.params) === paramStr);
                                            const label = seenBefore ? `${paramStr} · ${v.run_id || `#${i + 1}`}` : paramStr;
                                            const isBest = i === 0;
                                            const wr = v.win_rate;
                                            const winRateStr = wr != null ? (wr > 1 ? `${wr.toFixed(1)}%` : `${(wr * 100).toFixed(1)}%`) : '-';
                                            return (
                                            <TableRow key={i} sx={isBest ? { bgcolor: 'rgba(76, 175, 80, 0.15)' } : undefined}>
                                                <TableCell>{i + 1}</TableCell>
                                                {variants.some((x: any) => x.timeframe) && <TableCell>{v.timeframe || '-'}</TableCell>}
                                                <TableCell sx={{ maxWidth: 200 }} title={JSON.stringify(v.params)}>
                                                    {label}
                                                </TableCell>
                                                <TableCell>{formatMetric(v.sharpe_ratio)}</TableCell>
                                                <TableCell>{formatMetric(v.profit_factor)}</TableCell>
                                                <TableCell>{formatPercent(v.max_drawdown)}</TableCell>
                                                <TableCell>{v.total_trades}</TableCell>
                                                <TableCell>{winRateStr}</TableCell>
                                                <TableCell>{formatCurrency(v.total_pnl)}</TableCell>
                                                <TableCell align="right">
                                                    <Button size="small" startIcon={<FileCopyOutlined />} onClick={() => handleSaveClick(v)}>Save</Button>
                                                </TableCell>
                                            </TableRow>
                                            );
                                        })}
                                    </TableBody>
                                </Table>
                            </TableContainer>
                            {variants.length > 50 && <Typography variant="caption" color="textSecondary">Showing top 50 of {variants.length}</Typography>}
                        </CardContent>
                    </Card>
                </Grid>
            )}

            <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#fff' } }}>
                <DialogTitle sx={{ borderBottom: '1px solid #333' }}>Save Configuration Template</DialogTitle>
                <DialogContent sx={{ mt: 2 }}>
                    <DialogContentText sx={{ mb: 2, color: '#aaa' }}>Enter a name for this template to quickly load it later. Use only letters, numbers, dashes, and underscores.</DialogContentText>
                    <TextField autoFocus margin="dense" label="Template Name" type="text" fullWidth variant="outlined" value={saveTemplateName} onChange={(e) => { setSaveTemplateName(e.target.value); setSaveError(''); }} error={!!saveError} helperText={saveError} sx={{ input: { color: '#fff' }, label: { color: '#aaa' }, '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#555' }, '&:hover fieldset': { borderColor: '#888' } } }} />
                </DialogContent>
                <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                    <Button onClick={() => setSaveDialogOpen(false)} sx={{ color: '#aaa' }}>Cancel</Button>
                    <Button onClick={handleSaveConfirm} color="primary" variant="contained">Save</Button>
                </DialogActions>
            </Dialog>

            <Suspense fallback={null}>
                <TradeDetailsModal
                    open={isTradeModalOpen}
                    onClose={() => setIsTradeModalOpen(false)}
                    selectedTrade={selectedTrade}
                    trades={results?.trades ?? []}
                    onSelectTrade={setSelectedTrade}
                    symbol={chartSymbol}
                    timeframes={chartTimeframes}
                    strategyConfig={chartStrategyConfig}
                    exchangeType={exchangeType}
                    backtestStart={backtestStart}
                    backtestEnd={backtestEnd}
                />
            </Suspense>


            {/* Performance Metrics */}
            {!isOptimization && (
            <Grid item xs={12} mt={3}>
                <Card>
                    <CardHeader title="Performance Metrics" />
                    <CardContent>
                        <Grid container spacing={2}>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color={results.total_pnl >= 0 ? "success.main" : "error.main"}>
                                        {formatCurrency(results.total_pnl)}
                                    </Typography>
                                    <Typography variant="body2">Total PnL</Typography>
                                </Paper>
                            </Grid>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color="primary.main">
                                        {formatWinRatePercent(results.win_rate)}
                                    </Typography>
                                    <Typography variant="body2">Win Rate</Typography>
                                </Paper>
                            </Grid>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color="warning.main">
                                        {formatMetric(results.profit_factor)}
                                    </Typography>
                                    <Typography variant="body2">Profit Factor</Typography>
                                </Paper>
                            </Grid>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color="error.main">
                                        {formatPercent(results.max_drawdown)}
                                    </Typography>
                                    <Typography variant="body2">Max Drawdown</Typography>
                                </Paper>
                            </Grid>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color="info.main">
                                        {formatMetric(results.sharpe_ratio)}
                                    </Typography>
                                    <Typography variant="body2">Sharpe Ratio</Typography>
                                </Paper>
                            </Grid>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color="primary.main">
                                        {results.total_trades}
                                    </Typography>
                                    <Typography variant="body2">Total Trades</Typography>
                                </Paper>
                            </Grid>
                            <Grid item xs={6} md={2}>
                                <Paper sx={{ p: 2, textAlign: 'center' }}>
                                    <Typography variant="h6" color="secondary.main">
                                        {results.signals_generated || 0}
                                    </Typography>
                                    <Typography variant="body2">Signals Generated</Typography>
                                </Paper>
                            </Grid>
                        </Grid>
                    </CardContent>
                </Card>
            </Grid>
            )}

            {/* Charts */}
            {!isOptimization && (
            <Grid item xs={12} mt={3}>
                <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                        <Card>
                            <CardHeader title="Equity Curve" />
                            <CardContent>
                                <MemoizedLineChart data={equityData} />
                            </CardContent>
                        </Card>
                    </Grid>

                    <Grid item xs={12} md={6}>
                        <Card>
                            <CardHeader title="Trade Distribution" />
                            <CardContent>
                                <MemoizedPieChart data={pieData} />
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            </Grid>
            )}

            {/* Trade Analysis */}
            {!isOptimization && (
            <Grid item xs={12} mt={3}>
                <Card>
                    <CardHeader title="Trade Analysis" />
                    <CardContent>
                        <TradeAnalysisChart trades={results.trades || []} onTradeClick={handleBarClick} />
                    </CardContent>
                </Card>
            </Grid>
            )}

            {/* Detailed Results Table */}
            {!isOptimization && (
            <Grid item xs={12} mt={3}>
                <Card>
                    <CardHeader title="Detailed Results" />
                    <CardContent>
                        <TableContainer>
                            <Table>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Metric</TableCell>
                                        <TableCell>Value</TableCell>
                                        <TableCell>Description</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    <TableRow>
                                        <TableCell>Total PnL</TableCell>
                                        <TableCell>{formatCurrency(results.total_pnl)}</TableCell>
                                        <TableCell>Overall profit/loss</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Win Rate</TableCell>
                                        <TableCell>{formatWinRatePercent(results.win_rate)}</TableCell>
                                        <TableCell>Percentage of winning trades</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Profit Factor</TableCell>
                                        <TableCell>{formatMetric(results.profit_factor)}</TableCell>
                                        <TableCell>Gross profit / Gross loss</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Max Drawdown</TableCell>
                                        <TableCell>{formatPercent(results.max_drawdown)}</TableCell>
                                        <TableCell>Maximum peak-to-trough decline</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Sharpe Ratio</TableCell>
                                        <TableCell>{formatMetric(results.sharpe_ratio)}</TableCell>
                                        <TableCell>Risk-adjusted return</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Total Trades</TableCell>
                                        <TableCell>{results.total_trades}</TableCell>
                                        <TableCell>Number of executed trades</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Winning Trades</TableCell>
                                        <TableCell>{results.winning_trades || 0}</TableCell>
                                        <TableCell>Number of profitable trades</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Losing Trades</TableCell>
                                        <TableCell>{results.losing_trades || 0}</TableCell>
                                        <TableCell>Number of losing trades</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Average Win</TableCell>
                                        <TableCell>{formatMetric(results.avg_win)}</TableCell>
                                        <TableCell>Average profit per winning trade</TableCell>
                                    </TableRow>
                                    <TableRow>
                                        <TableCell>Average Loss</TableCell>
                                        <TableCell>{formatMetric(results.avg_loss)}</TableCell>
                                        <TableCell>Average loss per losing trade</TableCell>
                                    </TableRow>
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </CardContent>
                </Card>
            </Grid>
            )}
        </>
    );
};

export default ResultsPanel;
