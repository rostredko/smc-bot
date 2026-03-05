import React, { useMemo } from 'react';
import { Card, CardHeader, CardContent, Grid, Paper, Typography, TableContainer, Table, TableHead, TableRow, TableCell, TableBody } from '@mui/material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useResultsContext } from '../../../app/providers/results/ResultsProvider';
import { CustomTooltip, CustomPieTooltip } from '../../../shared/ui/ChartTooltips';
import { lazy, Suspense } from 'react';
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
    const { results, equityData, pieData, handleBarClick, selectedTrade, isTradeModalOpen, setIsTradeModalOpen } = useResultsContext();

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

    if (!results) return null;

    return (
        <>
            <Suspense fallback={null}>
                <TradeDetailsModal
                    open={isTradeModalOpen}
                    onClose={() => setIsTradeModalOpen(false)}
                    selectedTrade={selectedTrade}
                    symbol={chartSymbol}
                    timeframes={chartTimeframes}
                    strategyConfig={chartStrategyConfig}
                    exchangeType={exchangeType}
                    backtestStart={backtestStart}
                    backtestEnd={backtestEnd}
                />
            </Suspense>


            {/* Performance Metrics */}
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

            {/* Charts */}
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

            {/* Trade Analysis */}
            <Grid item xs={12} mt={3}>
                <Card>
                    <CardHeader title="Trade Analysis" />
                    <CardContent>
                        <TradeAnalysisChart trades={results.trades || []} onTradeClick={handleBarClick} />
                    </CardContent>
                </Card>
            </Grid>

            {/* Detailed Results Table */}
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
        </>
    );
};

export default ResultsPanel;
