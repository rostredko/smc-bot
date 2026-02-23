/**
 * TradeOHLCVChart
 *
 * Renders a Plotly candlestick chart with optional indicator subplots.
 * Indicators are fetched from the backend (/api/ohlcv?ema_period=...&rsi_period=...&adx_period=...)
 * and computed there using TA-Lib — identical to what the strategy used during backtesting.
 *
 * Only indicators that are **enabled** in strategyConfig are displayed:
 *   use_trend_filter → EMA overlay on price
 *   use_rsi_filter   → RSI subplot
 *   use_adx_filter   → ADX subplot
 *
 * Trade markers / SL / TP / trailing stop are shown on the price panel.
 */
import React, { useEffect, useState, useMemo } from 'react';
import Plot from 'react-plotly.js';
import { Box, CircularProgress, Typography } from '@mui/material';
import { API_BASE } from '../../../shared/api/config';
import type { OHLCVCandle } from '../../../shared/model/types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface IndicatorSeries {
    values: Array<{ time: string; value: number }>;
    period?: number;
    overbought?: number;
    oversold?: number;
    threshold?: number;
    timeframe?: string;
}

interface OHLCVResponse {
    candles: OHLCVCandle[];
    indicators: {
        ema?: IndicatorSeries;
        rsi?: IndicatorSeries;
        adx?: IndicatorSeries;
    };
}

export interface TradeOHLCVChartProps {
    trade: any;
    symbol: string;
    /** LTF timeframe for candles + RSI/ADX */
    timeframe: string;
    /** HTF timeframe for EMA (e.g. '4h' when candles are '1h'); defaults to timeframe */
    emaTimeframe?: string;
    /** strategy_config from backtest results — controls which indicators to show */
    strategyConfig?: Record<string, any>;
    height?: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toIso(str: string | null | undefined): string {
    if (!str) return '';
    // Normalize space separator and strip microseconds
    const s = str.replace(' ', 'T').split('.')[0];
    // If no timezone offset present, treat as UTC by appending 'Z'.
    // Backtrader/server timestamps are stored in UTC without tz-info.
    // Without this, JS Date() parses naive strings as LOCAL time,
    // causing a 2-bar (2-hour) offset on UTC+2 systems.
    if (!s.endsWith('Z') && !s.includes('+')) return s + 'Z';
    return s;
}


// ─── Component ────────────────────────────────────────────────────────────────

const TradeOHLCVChart: React.FC<TradeOHLCVChartProps> = ({
    trade,
    symbol,
    timeframe,
    emaTimeframe,
    strategyConfig = {},
    height = 500,
}) => {
    const [data, setData] = useState<OHLCVResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // ── Derive indicator params from strategy config ─────────────────────────
    // For old backtests (no configuration), show all indicators with defaults
    const indParams = useMemo(() => {
        const cfg = strategyConfig;
        const hasConfig = cfg && Object.keys(cfg).length > 0;
        const useDefaults = !hasConfig;
        return {
            emaPeriod: useDefaults || cfg.use_trend_filter ? (cfg?.trend_ema_period ?? 200) : 0,
            rsiPeriod: useDefaults || cfg.use_rsi_filter ? (cfg?.rsi_period ?? 14) : 0,
            rsiOb: cfg?.rsi_overbought ?? 70,
            rsiOs: cfg?.rsi_oversold ?? 30,
            adxPeriod: useDefaults || cfg.use_adx_filter ? (cfg?.adx_period ?? 14) : 0,
            adxThreshold: cfg?.adx_threshold ?? 25,
        };
    }, [strategyConfig]);

    // ── Fetch OHLCV + indicators ─────────────────────────────────────────────
    useEffect(() => {
        if (!trade) return;

        let cancelled = false;
        setLoading(true);
        setError(null);

        const entryIso = toIso(trade.entry_time);
        const exitIso = toIso(trade.exit_time);

        const params = new URLSearchParams({
            symbol,
            timeframe,
            context_bars: '25',
            ...(entryIso ? { start: entryIso } : {}),
            ...(exitIso ? { end: exitIso } : {}),
            // Indicator params (0 = disabled on backend)
            ema_period: String(indParams.emaPeriod),
            ...(emaTimeframe ? { ema_timeframe: emaTimeframe } : {}),
            rsi_period: String(indParams.rsiPeriod),
            rsi_overbought: String(indParams.rsiOb),
            rsi_oversold: String(indParams.rsiOs),
            adx_period: String(indParams.adxPeriod),
            adx_threshold: String(indParams.adxThreshold),
        });

        fetch(`${API_BASE}/api/ohlcv?${params}`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json() as Promise<OHLCVResponse>;
            })
            .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
            .catch(err => { if (!cancelled) { setError(err.message ?? 'Failed to load'); setLoading(false); } });

        return () => { cancelled = true; };
    }, [trade, symbol, timeframe, emaTimeframe, indParams]);

    // ── Build Plotly figure ──────────────────────────────────────────────────
    const figure = useMemo(() => {
        if (!data?.candles.length || !trade) return null;

        const { candles, indicators } = data;
        const times = candles.map(c => c.time);
        const opens = candles.map(c => c.open);
        const highs = candles.map(c => c.high);
        const lows = candles.map(c => c.low);
        const closes = candles.map(c => c.close);

        const hasRsi = Boolean(indicators.rsi?.values?.length);
        const hasAdx = Boolean(indicators.adx?.values?.length);

        // Layout: price panel is taller; RSI + ADX each get a small panel below
        const subplotCount = 1 + (hasRsi ? 1 : 0) + (hasAdx ? 1 : 0);
        const priceRatio = subplotCount === 1 ? 1 : subplotCount === 2 ? 0.65 : 0.55;
        const smallRatio = subplotCount === 3 ? 0.2 : 0.3;

        // Build row heights
        const rowHeights: number[] = [priceRatio];
        if (hasRsi) rowHeights.push(smallRatio);
        if (hasAdx) rowHeights.push(smallRatio);

        const totalChartHeight = height;

        // ── Traces ────────────────────────────────────────────────────────

        // 1. Candlestick (row 1)
        const traces: any[] = [
            {
                type: 'candlestick',
                x: times, open: opens, high: highs, low: lows, close: closes,
                name: symbol,
                xaxis: 'x', yaxis: 'y',
                increasing: { line: { color: '#26a69a', width: 1 }, fillcolor: '#26a69a' },
                decreasing: { line: { color: '#ef5350', width: 1 }, fillcolor: '#ef5350' },
                hovertemplate: '<b>%{x}</b><br>O:%{open:.2f} H:%{high:.2f} L:%{low:.2f} C:%{close:.2f}<extra></extra>',
            },
        ];

        // 2. EMA overlay on price panel
        if (indicators.ema?.values?.length) {
            const emaData = indicators.ema;
            const emaLabel = `EMA ${emaData.period}${emaData.timeframe ? ` (${emaData.timeframe})` : ''}`;
            traces.push({
                type: 'scatter',
                x: emaData.values.map(p => p.time),
                y: emaData.values.map(p => p.value),
                mode: 'lines',
                name: emaLabel,
                xaxis: 'x', yaxis: 'y',
                line: { color: '#42a5f5', width: 1.5 },
                hovertemplate: `${emaLabel}: $%{y:.2f}<extra></extra>`,
                opacity: 0.85,
            });
        }

        // 3. Entry / exit markers
        const isWin = trade.pnl >= 0;
        traces.push(
            {
                type: 'scatter', xaxis: 'x', yaxis: 'y',
                x: [toIso(trade.entry_time)], y: [trade.entry_price],
                mode: 'markers', name: 'Entry',
                marker: { symbol: 'triangle-up', size: 14, color: '#4caf50', line: { color: '#fff', width: 1 } },
                hovertemplate: `<b>ENTRY</b><br>$${trade.entry_price?.toFixed(2)}<extra></extra>`,
            },
            {
                type: 'scatter', xaxis: 'x', yaxis: 'y',
                x: [toIso(trade.exit_time)], y: [trade.exit_price],
                mode: 'markers', name: 'Exit',
                marker: { symbol: 'triangle-down', size: 14, color: isWin ? '#4caf50' : '#f44336', line: { color: '#fff', width: 1 } },
                hovertemplate: `<b>EXIT</b> (${trade.exit_reason || 'Unknown'})<br>$${trade.exit_price?.toFixed(2)}<extra></extra>`,
            }
        );

        // 4. Trailing SL step-line
        if (trade.sl_history?.length) {
            const slTimes: string[] = [];
            const slPrices: number[] = [];

            trade.sl_history.forEach((h: any) => {
                slTimes.push(toIso(h.time ?? trade.entry_time));
                slPrices.push(h.price);
            });
            if (trade.exit_time && slTimes.length) {
                slTimes.push(toIso(trade.exit_time));
                slPrices.push(slPrices[slPrices.length - 1]);
            }

            traces.push({
                type: 'scatter', xaxis: 'x', yaxis: 'y',
                x: slTimes, y: slPrices,
                mode: 'lines', name: 'Trailing SL',
                line: { color: '#ff9800', width: 2, dash: 'dot', shape: 'hv' },
                hovertemplate: 'Trailing SL: $%{y:.2f}<extra></extra>',
                opacity: 0.9,
            });
        }

        // 5. RSI
        let rsiAxisIdx = 2;
        if (hasRsi) {
            const rsiData = indicators.rsi!;
            const rsiAxis = `y${rsiAxisIdx}`;
            traces.push(
                {
                    type: 'scatter',
                    x: rsiData.values.map(p => p.time),
                    y: rsiData.values.map(p => p.value),
                    mode: 'lines', name: `RSI ${rsiData.period}`,
                    xaxis: 'x', yaxis: rsiAxis,
                    line: { color: '#ce93d8', width: 1.5 },
                    hovertemplate: `RSI: %{y:.1f}<extra></extra>`,
                }
            );
            if (hasAdx) rsiAxisIdx = 2; // RSI is always y2 if present
        }

        // 6. ADX
        if (hasAdx) {
            const adxData = indicators.adx!;
            const adxAxisIdx = hasRsi ? 3 : 2;
            const adxAxis = `y${adxAxisIdx}`;
            traces.push({
                type: 'scatter',
                x: adxData.values.map(p => p.time),
                y: adxData.values.map(p => p.value),
                mode: 'lines', name: `ADX ${adxData.period}`,
                xaxis: 'x', yaxis: adxAxis,
                line: { color: '#ffb74d', width: 1.5 },
                hovertemplate: `ADX: %{y:.1f}<extra></extra>`,
            });
        }

        // ── SL / TP shapes & annotations ──────────────────────────────────
        const xMin = times[0];
        const xMax = times[times.length - 1];
        const shapes: any[] = [];
        const annotations: any[] = [];

        if (trade.stop_loss) {
            shapes.push({ type: 'line', xref: 'x', yref: 'y', x0: xMin, x1: xMax, y0: trade.stop_loss, y1: trade.stop_loss, line: { color: '#f44336', width: 1.5, dash: 'dot' } });
            annotations.push({ x: xMax, y: trade.stop_loss, xanchor: 'right', yanchor: 'bottom', xref: 'x', yref: 'y', text: `SL $${trade.stop_loss.toFixed(2)}`, showarrow: false, font: { color: '#f44336', size: 11 } });
        }
        if (trade.take_profit) {
            shapes.push({ type: 'line', xref: 'x', yref: 'y', x0: xMin, x1: xMax, y0: trade.take_profit, y1: trade.take_profit, line: { color: '#4caf50', width: 1.5, dash: 'dot' } });
            annotations.push({ x: xMax, y: trade.take_profit, xanchor: 'right', yanchor: 'bottom', xref: 'x', yref: 'y', text: `TP $${trade.take_profit.toFixed(2)}`, showarrow: false, font: { color: '#4caf50', size: 11 } });
        }

        // RSI reference lines
        if (hasRsi) {
            const rsiData = indicators.rsi!;
            const rsiY = `y${rsiAxisIdx}`;
            const rsiX = 'x';
            const ob = rsiData.overbought ?? 70;
            const os = rsiData.oversold ?? 30;
            shapes.push(
                { type: 'line', xref: rsiX, yref: rsiY, x0: xMin, x1: xMax, y0: ob, y1: ob, line: { color: '#f44336', width: 1, dash: 'dash' } },
                { type: 'line', xref: rsiX, yref: rsiY, x0: xMin, x1: xMax, y0: os, y1: os, line: { color: '#4caf50', width: 1, dash: 'dash' } },
                { type: 'line', xref: rsiX, yref: rsiY, x0: xMin, x1: xMax, y0: 50, y1: 50, line: { color: '#555', width: 1, dash: 'dot' } }
            );
        }

        // ADX threshold line
        if (hasAdx) {
            const adxAxisIdx = hasRsi ? 3 : 2;
            const adxY = `y${adxAxisIdx}`;
            const thr = indicators.adx!.threshold ?? 25;
            shapes.push({
                type: 'line', xref: 'x', yref: adxY,
                x0: xMin, x1: xMax, y0: thr, y1: thr,
                line: { color: '#ffb74d', width: 1, dash: 'dash' }
            });
        }

        // ── Shared helper: snap trade entry/exit to nearest indicator candle ─
        // The trade timestamps may lack timezone info while OHLCV times are UTC.
        // Using the snapped candle time for BOTH vertical lines and markers
        // guarantees they always align perfectly.
        const entryIsoTime = toIso(trade.entry_time);
        const exitIsoTime = toIso(trade.exit_time);

        const makeNearestFinder = (values: Array<{ time: string; value: number }>) =>
            (iso: string): { time: string; value: number } | null => {
                if (!iso || !values.length) return null;
                const target = new Date(iso).getTime();
                let best: { time: string; value: number } | null = null;
                let bestDiff = Infinity;
                for (const p of values) {
                    const diff = Math.abs(new Date(p.time).getTime() - target);
                    if (diff < bestDiff) { bestDiff = diff; best = p; }
                }
                return best;
            };

        // Snap entry/exit to nearest RSI candle (empty array if RSI disabled)
        const rsiNearestFn = hasRsi
            ? makeNearestFinder(indicators.rsi!.values)
            : () => null;
        const rsiEntry = rsiNearestFn(entryIsoTime);
        const rsiExit = rsiNearestFn(exitIsoTime);

        // Snap entry/exit to nearest ADX candle
        const adxNearestFn = hasAdx
            ? makeNearestFinder(indicators.adx!.values)
            : () => null;
        const adxEntry = adxNearestFn(entryIsoTime);
        const adxExit = adxNearestFn(exitIsoTime);

        // ── Entry / Exit vertical lines on indicator subpanels ────────────
        // Using snapped times so lines and dots are always co-located.
        const subpanelAxes: Array<{ yAxis: string; snappedEntry: string | null; snappedExit: string | null }> = [];
        if (hasRsi) subpanelAxes.push({ yAxis: `y${rsiAxisIdx}`, snappedEntry: rsiEntry?.time ?? null, snappedExit: rsiExit?.time ?? null });
        if (hasAdx) subpanelAxes.push({ yAxis: `y${hasRsi ? 3 : 2}`, snappedEntry: adxEntry?.time ?? null, snappedExit: adxExit?.time ?? null });

        subpanelAxes.forEach(({ yAxis, snappedEntry, snappedExit }) => {
            if (snappedEntry) {
                shapes.push({
                    type: 'line', xref: 'x', yref: `${yAxis} domain`,
                    x0: snappedEntry, x1: snappedEntry, y0: 0, y1: 1,
                    line: { color: '#4caf50', width: 1.5, dash: 'dot' },
                    opacity: 0.7,
                });
            }
            if (snappedExit) {
                shapes.push({
                    type: 'line', xref: 'x', yref: `${yAxis} domain`,
                    x0: snappedExit, x1: snappedExit, y0: 0, y1: 1,
                    line: { color: trade.pnl >= 0 ? '#4caf50' : '#f44336', width: 1.5, dash: 'dot' },
                    opacity: 0.7,
                });
            }
        });

        // ── RSI marker dots at entry/exit ─────────────────────────────────
        if (hasRsi && (rsiEntry || rsiExit)) {
            const rsiAxis = `y${rsiAxisIdx}`;
            const xs = [rsiEntry?.time, rsiExit?.time].filter(Boolean) as string[];
            const ys = [rsiEntry?.value, rsiExit?.value].filter(v => v !== undefined) as number[];
            traces.push({
                type: 'scatter', xaxis: 'x', yaxis: rsiAxis,
                x: xs, y: ys,
                mode: 'markers', name: 'RSI signal', showlegend: false,
                marker: {
                    size: 9,
                    color: [
                        rsiEntry ? '#4caf50' : null,
                        rsiExit ? (trade.pnl >= 0 ? '#4caf50' : '#f44336') : null,
                    ].filter(Boolean),
                    symbol: ['triangle-up', 'triangle-down'],
                    line: { color: '#fff', width: 1.5 },
                },
                hovertemplate: 'RSI @ signal: %{y:.1f}<extra></extra>',
            } as any);
        }

        // ── ADX marker dots at entry/exit ─────────────────────────────────
        if (hasAdx && (adxEntry || adxExit)) {
            const adxAxisIdx = hasRsi ? 3 : 2;
            const adxAxis = `y${adxAxisIdx}`;
            const xs = [adxEntry?.time, adxExit?.time].filter(Boolean) as string[];
            const ys = [adxEntry?.value, adxExit?.value].filter(v => v !== undefined) as number[];
            traces.push({
                type: 'scatter', xaxis: 'x', yaxis: adxAxis,
                x: xs, y: ys,
                mode: 'markers', name: 'ADX signal', showlegend: false,
                marker: {
                    size: 9,
                    color: [
                        adxEntry ? '#4caf50' : null,
                        adxExit ? (trade.pnl >= 0 ? '#4caf50' : '#f44336') : null,
                    ].filter(Boolean),
                    symbol: ['triangle-up', 'triangle-down'],
                    line: { color: '#fff', width: 1.5 },
                },
                hovertemplate: 'ADX @ signal: %{y:.1f}<extra></extra>',
            } as any);
        }

        // ── Layout ────────────────────────────────────────────────────────

        // Build yaxis definitions dynamically
        const commonAxisStyle = { gridcolor: '#2a2a2a', linecolor: '#333', showgrid: true, zeroline: false };

        // Calculate subplot domains bottom-up
        const totalRatio = rowHeights.reduce((s, v) => s + v, 0);
        const gap = 0.02;
        const domains: Array<[number, number]> = [];
        let cursor = 0;
        for (let i = rowHeights.length - 1; i >= 0; i--) {
            const h = rowHeights[i] / totalRatio;
            domains.unshift([cursor, cursor + h - gap]);
            cursor += h;
        }
        // domains[0] = price (topmost), domains[1] = rsi if present, domains[2] = adx if present

        const layoutYAxes: Record<string, any> = {
            yaxis: {
                ...commonAxisStyle,
                domain: domains[0],
                tickprefix: '$', tickformat: '.2f',
            },
        };

        let axNum = 2;
        if (hasRsi) {
            layoutYAxes[`yaxis${axNum}`] = {
                ...commonAxisStyle,
                domain: domains[axNum - 1],
                range: [0, 100],
                tickvals: [30, 50, 70],
                ticksuffix: '',
                title: { text: `RSI ${indicators.rsi!.period}`, font: { size: 10, color: '#ce93d8' } },
            };
            axNum++;
        }
        if (hasAdx) {
            layoutYAxes[`yaxis${axNum}`] = {
                ...commonAxisStyle,
                domain: domains[axNum - 1],
                range: [0, 80],
                title: { text: `ADX ${indicators.adx!.period}`, font: { size: 10, color: '#ffb74d' } },
            };
        }

        const layout: any = {
            template: 'plotly_dark',
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: '#1a1a1a',
            height: totalChartHeight,
            font: { color: '#ccc', size: 11, family: 'Inter, system-ui, sans-serif' },
            margin: { t: 10, b: 40, l: 65, r: 10 },
            xaxis: {
                type: 'date',
                rangeslider: { visible: false },
                gridcolor: '#2a2a2a',
                linecolor: '#333',
                showgrid: true,
                anchor: 'free',    // span all rows
                overlaying: undefined,
            },
            ...layoutYAxes,
            legend: {
                bgcolor: 'rgba(0,0,0,0)',
                orientation: 'h',
                x: 0, y: 1.02, xanchor: 'left', yanchor: 'bottom',
                font: { size: 10 },
            },
            shapes,
            annotations,
            hovermode: 'x unified',
            dragmode: 'pan',
            grid: subplotCount > 1 ? {
                rows: subplotCount,
                columns: 1,
                pattern: 'independent',
                roworder: 'top to bottom',
            } : undefined,
        };

        return { traces, layout };
    }, [data, trade, symbol, height]);

    // ── Render ───────────────────────────────────────────────────────────────
    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height }}>
                <CircularProgress size={28} />
                <Typography variant="body2" sx={{ ml: 2, color: '#aaa' }}>Loading chart…</Typography>
            </Box>
        );
    }

    if (error) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height, flexDirection: 'column', gap: 1 }}>
                <Typography variant="body2" sx={{ color: '#f44336' }}>⚠ Could not load chart data</Typography>
                <Typography variant="caption" sx={{ color: '#666' }}>{error}</Typography>
            </Box>
        );
    }

    if (!figure) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height }}>
                <Typography variant="body2" sx={{ color: '#888' }}>No chart data available.</Typography>
            </Box>
        );
    }

    return (
        <Plot
            data={figure.traces}
            layout={figure.layout}
            config={{
                displayModeBar: true,
                modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
                displaylogo: false,
                scrollZoom: true,
                responsive: true,
            }}
            style={{ width: '100%' }}
            useResizeHandler
        />
    );
};

export default React.memo(TradeOHLCVChart);
