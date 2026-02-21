import React, { useMemo } from 'react';
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Cell
} from 'recharts';

interface TradeAnalysisChartProps {
    trades: any[];
    onTradeClick: (trade: any) => void;
    height?: number;
}

const CustomTradeTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        const data = payload[0].payload;
        return (
            <div style={{
                backgroundColor: '#1e1e1e',
                border: '1px solid #333',
                borderRadius: '4px',
                padding: '12px',
                boxShadow: '0 4px 6px rgba(0,0,0,0.3)',
                color: '#fff'
            }}>
                <p style={{ margin: 0, fontWeight: 'bold', borderBottom: '1px solid #444', paddingBottom: '4px', marginBottom: '8px' }}>
                    Trade #{label}
                </p>
                <p style={{ margin: 0, fontSize: '0.9rem' }}>
                    <span style={{ color: '#aaa' }}>Date:</span> {data.date}
                </p>
                <p style={{ margin: 0, fontSize: '0.9rem', color: data.pnl >= 0 ? '#4caf50' : '#f44336' }}>
                    <span style={{ color: '#aaa' }}>PnL:</span> ${data.pnl?.toFixed(2)}
                </p>
                <p style={{ margin: '8px 0 0 0', fontSize: '0.8rem', color: '#888', fontStyle: 'italic' }}>
                    Click for details
                </p>
            </div>
        );
    }
    return null;
};

const TradeAnalysisChart: React.FC<TradeAnalysisChartProps> = ({ trades, onTradeClick, height = 300 }) => {
    const tradeData = useMemo(() => {
        if (!trades || trades.length === 0) {
            return [
                { trade: 1, pnl: 0, type: "NO_TRADES", date: "", fullTrade: null }
            ];
        }
        return trades.map((trade, index) => ({
            trade: index + 1,
            pnl: trade.pnl || 0,
            type: trade.pnl > 0 ? "WIN" : "LOSS",
            date: trade.entry_time ? new Date(trade.entry_time).toLocaleDateString() : 'N/A',
            fullTrade: trade
        }));
    }, [trades]);

    return (
        <ResponsiveContainer width="100%" height={height}>
            <BarChart
                data={tradeData}
                onClick={(data) => {
                    if (data && data.activePayload && data.activePayload.length > 0) {
                        onTradeClick(data.activePayload[0].payload.fullTrade);
                    }
                }}
                style={{ cursor: 'pointer' }}
            >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="trade" />
                <YAxis />
                <Tooltip content={<CustomTradeTooltip />} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
                <Bar dataKey="pnl" fill="#8884d8" isAnimationActive={false}>
                    {
                        tradeData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#4caf50' : '#f44336'} />
                        ))
                    }
                </Bar>
            </BarChart>
        </ResponsiveContainer>
    );
};

export default React.memo(TradeAnalysisChart);
