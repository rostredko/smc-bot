/**
 * TradeAnalysisChart
 *
 * Bar chart of trade PnL using Plotly.js.
 * Green bars = winning trades, red bars = losing trades.
 * Clicking a bar triggers onTradeClick with the full trade object.
 *
 * Public interface is identical to the old recharts version so no
 * consumer (ResultsPanel, BacktestHistoryList, etc.) needs changes.
 */
import React, { useMemo } from 'react';
import Plot from 'react-plotly.js';

interface TradeAnalysisChartProps {
    trades: any[];
    onTradeClick: (trade: any) => void;
    height?: number;
}

const TradeAnalysisChart: React.FC<TradeAnalysisChartProps> = ({
    trades,
    onTradeClick,
    height = 300,
}) => {
    const { x, y, colors, customdata } = useMemo(() => {
        if (!trades || trades.length === 0) {
            return { x: [], y: [], colors: [], customdata: [] };
        }
        return trades.reduce(
            (acc, trade, index) => {
                const pnl = trade.pnl ?? 0;
                acc.x.push(index + 1);
                acc.y.push(pnl);
                acc.colors.push(pnl >= 0 ? '#26a69a' : '#ef5350');
                acc.customdata.push({
                    date: trade.entry_time
                        ? new Date(trade.entry_time).toLocaleDateString()
                        : 'N/A',
                    fullTrade: trade,
                });
                return acc;
            },
            { x: [] as number[], y: [] as number[], colors: [] as string[], customdata: [] as any[] }
        );
    }, [trades]);

    if (!trades || trades.length === 0) {
        return (
            <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#888' }}>
                No trade data available.
            </div>
        );
    }

    return (
        <Plot
            data={[
                {
                    type: 'bar',
                    x,
                    y,
                    marker: { color: colors },
                    customdata: customdata.map((d: { date: string; fullTrade: any }) => [d.date, d.fullTrade]),
                    hovertemplate: [
                        '<b>Trade #%{x}</b><br>',
                        'Date: %{customdata[0]}<br>',
                        'PnL: <b>$%{y:.2f}</b>',
                        '<br><i>Click for details</i>',
                        '<extra></extra>',
                    ].join(''),
                    name: 'PnL',
                } as any,
            ]}
            layout={{
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
                    tickformat: '.0f',
                },
                showlegend: false,
                hovermode: 'closest',
            } as any}
            config={{
                displayModeBar: false,
                scrollZoom: false,
                responsive: true,
            }}
            style={{ width: '100%' }}
            useResizeHandler
            onClick={(event) => {
                const point = event.points?.[0];
                if (point && point.customdata) {
                    const [, fullTrade] = (point.customdata as unknown) as [string, any];
                    if (fullTrade) onTradeClick(fullTrade);
                }
            }}
        />
    );
};

export default React.memo(TradeAnalysisChart);
