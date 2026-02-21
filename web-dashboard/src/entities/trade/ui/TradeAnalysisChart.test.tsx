import { render } from '@testing-library/react';
import { vi } from 'vitest';
import TradeAnalysisChart from './TradeAnalysisChart';

// Mock recharts because it requires full DOM/SVG support to render completely
vi.mock('recharts', async () => {
    const OriginalModule = await vi.importActual<any>('recharts');
    return {
        ...OriginalModule,
        ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
        BarChart: ({ children }: any) => <div data-testid="barchart">{children}</div>,
        Bar: () => <div data-testid="bar" />,
        XAxis: () => <div data-testid="xaxis" />,
        YAxis: () => <div data-testid="yaxis" />,
        Tooltip: () => <div data-testid="tooltip" />,
        CartesianGrid: () => <div data-testid="cartesian-grid" />,
        Cell: () => <div data-testid="cell" />
    };
});

describe('TradeAnalysisChart', () => {
    it('renders without crashing even with empty trades', () => {
        const mockOnClick = vi.fn();
        const { getByTestId } = render(<TradeAnalysisChart trades={[]} onTradeClick={mockOnClick} />);

        expect(getByTestId('barchart')).toBeInTheDocument();
    });

    it('renders correctly with given trades', () => {
        const mockOnClick = vi.fn();
        const trades = [
            { pnl: 50, entry_time: "2026-02-21T10:00:00" },
            { pnl: -20, entry_time: "2026-02-21T11:00:00" }
        ];

        const { getByTestId } = render(<TradeAnalysisChart trades={trades} onTradeClick={mockOnClick} />);

        expect(getByTestId('barchart')).toBeInTheDocument();
    });
});
