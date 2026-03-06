/**
 * TradeAnalysisChart
 *
 * Bar chart of trade PnL using Plotly.js.
 * Green bars = winning trades, red bars = losing trades.
 * Clicking a bar triggers onTradeClick with the full trade object.
 *
 * Uses click coordinates to resolve bar index (Plotly events are unreliable inside Collapse).
 */
import React, { useCallback, useMemo, useRef } from 'react';
import Plot from 'react-plotly.js';

const PLOT_LEFT_MARGIN = 60;
const PLOT_RIGHT_MARGIN = 10;

function toIso(input: string | null | undefined): string {
    if (!input) return '';
    const normalized = input.replace(' ', 'T');
    if (/[zZ]$/.test(normalized) || /[-+]\d{2}:\d{2}$/.test(normalized)) {
        return normalized;
    }
    return `${normalized}Z`;
}

function toUtcDateTimeDisplay(input: string | null | undefined): string {
    const iso = toIso(input);
    if (!iso) return 'N/A';
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return 'N/A';
    const mm = String(dt.getUTCMonth() + 1);
    const dd = String(dt.getUTCDate());
    const yyyy = String(dt.getUTCFullYear());
    const hh = String(dt.getUTCHours()).padStart(2, '0');
    const min = String(dt.getUTCMinutes()).padStart(2, '0');
    return `${mm}/${dd}/${yyyy} ${hh}:${min} UTC`;
}

interface TradeAnalysisChartProps {
    trades: any[];
    onTradeClick: (trade: any) => void;
    height?: number;
}

function extractPatternLabel(trade: any): string {
    const line: string | undefined = trade?.entry_context?.why_entry?.[0];
    if (typeof line === 'string' && line.trim().length > 0) {
        const prefix = 'Pattern: ';
        if (line.startsWith(prefix)) {
            return line.slice(prefix.length);
        }
        return line;
    }
    const reason: string | undefined = trade?.reason;
    if (typeof reason === 'string' && reason.trim().length > 0) {
        return reason;
    }
    return 'Unknown pattern';
}

const TradeAnalysisChart: React.FC<TradeAnalysisChartProps> = ({
    trades,
    onTradeClick,
    height = 300,
}) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const { x, y, colors, customdata, maxAbsPnl } = useMemo(() => {
        if (!trades || trades.length === 0) {
            return { x: [], y: [], colors: [], customdata: [], maxAbsPnl: 0 };
        }
        const aggregated = trades.reduce(
            (acc, trade, index) => {
                const pnl = trade.pnl ?? 0;
                acc.x.push(index + 1);
                acc.y.push(pnl);
                acc.colors.push(pnl >= 0 ? '#26a69a' : '#ef5350');
                acc.customdata.push({
                    date: toUtcDateTimeDisplay(trade.entry_time),
                    pattern: extractPatternLabel(trade),
                    fullTrade: trade,
                });
                return acc;
            },
            { x: [] as number[], y: [] as number[], colors: [] as string[], customdata: [] as any[] }
        );
        const maxAbs = aggregated.y.reduce(
            (max: number, value: number) => Math.max(max, Math.abs(value)),
            0
        );
        return { ...aggregated, maxAbsPnl: maxAbs };
    }, [trades]);

    const handleContainerClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        e.stopPropagation();
        const n = trades?.length ?? 0;
        if (n === 0) return;
        const el = containerRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const plotWidth = rect.width - PLOT_LEFT_MARGIN - PLOT_RIGHT_MARGIN;
        if (plotWidth <= 0) return;
        const relX = clickX - PLOT_LEFT_MARGIN;
        if (relX < 0) return;
        const idx = Math.min(Math.floor((relX / plotWidth) * n), n - 1);
        if (idx >= 0) onTradeClick(trades[idx]);
    }, [trades, onTradeClick]);

    const plotData = useMemo(() => [
        {
            type: 'bar' as const,
            x,
            y,
            marker: { color: colors },
            customdata: customdata.map((d: { date: string; pattern: string; fullTrade: any }) => [d.date, d.pattern, d.fullTrade]),
            hovertemplate: [
                '<b>Trade #%{x}</b><br>',
                'Date (UTC): %{customdata[0]}<br>',
                'Pattern: <b>%{customdata[1]}</b><br>',
                'PnL: <b>$%{y:.2f}</b>',
                '<br><i>Click for details</i>',
                '<extra></extra>',
            ].join(''),
            name: 'PnL',
        },
    ], [x, y, colors, customdata]);

    const plotLayout = useMemo(() => {
        let yTickFormat: string = '.0f';
        if (maxAbsPnl < 1) {
            yTickFormat = '.2f';
        } else if (maxAbsPnl < 10) {
            yTickFormat = '.1f';
        }

        return {
            template: 'plotly_dark',
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            height,
            margin: { t: 10, b: 40, l: 60, r: 10 },
            font: { color: '#ccc', size: 11, family: 'Inter, system-ui, sans-serif' },
            bargap: 0.15,
            xaxis: {
                title: { text: 'Trade #', standoff: 8 },
                gridcolor: '#2a2a2a',
                linecolor: '#333',
                tickmode: 'linear' as any,
                dtick: Math.max(1, Math.ceil(x.length / 20)),
            },
            yaxis: {
                title: { text: 'PnL ($)', standoff: 8 },
                gridcolor: '#2a2a2a',
                linecolor: '#333',
                zeroline: true,
                zerolinecolor: '#555',
                tickprefix: '$',
                tickformat: yTickFormat,
            },
            showlegend: false,
            hovermode: 'closest',
        };
    }, [height, x.length, maxAbsPnl]);

    const plotConfig = useMemo(() => ({
        displayModeBar: false,
        scrollZoom: false,
        responsive: true,
    }), []);

    if (!trades || trades.length === 0) {
        return (
            <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#888' }}>
                No trade data available.
            </div>
        );
    }

    return (
        <div ref={containerRef} style={{ position: 'relative', cursor: 'pointer' }} onClick={handleContainerClick}>
        <Plot
            data={plotData as any}
            layout={plotLayout as any}
            config={plotConfig}
            style={{ width: '100%' }}
            useResizeHandler
        />
        </div>
    );
};

export default React.memo(TradeAnalysisChart);
