import { render } from '@testing-library/react';
import { vi } from 'vitest';
import TradeAnalysisChart from './TradeAnalysisChart';

// Mock react-plotly.js — it requires full browser DOM / WebGL which is unavailable in jsdom
vi.mock('react-plotly.js', () => ({
    default: (props: any) => (
        <div
            data-testid="plotly-chart"
            data-trace-count={props.data?.length ?? 0}
            onClick={() => {
                // Simulate a click on the first point for testing
                if (props.onClick && props.data?.[0]?.customdata?.length) {
                    props.onClick({
                        points: [{
                            customdata: props.data[0].customdata[0]
                        }]
                    });
                }
            }}
        />
    ),
}));

describe('TradeAnalysisChart', () => {
    it('renders without crashing even with empty trades', () => {
        const mockOnClick = vi.fn();
        const { container } = render(
            <TradeAnalysisChart trades={[]} onTradeClick={mockOnClick} />
        );
        // Empty trades renders the "no data" message, not the Plotly chart
        expect(container).toBeTruthy();
    });

    it('renders a Plotly chart with trade data', () => {
        const mockOnClick = vi.fn();
        const trades = [
            { pnl: 50, entry_time: '2026-02-21T10:00:00' },
            { pnl: -20, entry_time: '2026-02-21T11:00:00' },
        ];

        const { getByTestId } = render(
            <TradeAnalysisChart trades={trades} onTradeClick={mockOnClick} />
        );

        expect(getByTestId('plotly-chart')).toBeInTheDocument();
    });
});
