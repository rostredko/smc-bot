import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Grid } from '@mui/material';

import ResultsPanel from './ResultsPanel';

const useResultsContextMock = vi.fn();

vi.mock('../../../app/providers/results/ResultsProvider', () => ({
    useResultsContext: () => useResultsContextMock(),
}));

vi.mock('../../../entities/trade/ui/TradeAnalysisChart', () => ({
    default: () => null,
}));

vi.mock('../../../features/trade-details/ui/TradeDetailsModal', () => ({
    default: () => null,
}));

const optimizationResults = {
    run_mode: 'optimize',
    variants: [
        {
            run_id: 'opt_0',
            params: { risk_reward_ratio: 2.5, sl_buffer_atr: 1, trailing_stop_distance: 0.02 },
            sharpe_ratio: 0.111,
            profit_factor: 28.57,
            max_drawdown: 0.6,
            total_trades: 2,
            win_rate: 50,
            total_pnl: 116.27,
        },
        {
            run_id: 'opt_1',
            params: { risk_reward_ratio: 2, sl_buffer_atr: 1.3, trailing_stop_distance: 0.02 },
            sharpe_ratio: 0.11,
            profit_factor: 22.83,
            max_drawdown: 0.6,
            total_trades: 2,
            win_rate: 50,
            total_pnl: 91.82,
        },
    ],
    configuration: {},
};

describe('ResultsPanel', () => {
    it('renders optimization table with Variants, Profit Factor, Win Rate columns', () => {
        useResultsContextMock.mockReturnValue({
            results: optimizationResults,
            backtestStatus: null,
            equityData: [],
            pieData: [],
            handleBarClick: vi.fn(),
            selectedTrade: null,
            setSelectedTrade: vi.fn(),
            isTradeModalOpen: false,
            setIsTradeModalOpen: vi.fn(),
        });

        render(
            <Grid container>
                <ResultsPanel />
            </Grid>
        );

        expect(screen.getByText(/Optimization Results \(2 variants\)/)).toBeInTheDocument();
        expect(screen.getByText(/Best:.*rr 2\.5 slb 1 tsd 0\.02/)).toBeInTheDocument();
        expect(screen.getByText('Variants')).toBeInTheDocument();
        expect(screen.getByText('Profit Factor')).toBeInTheDocument();
        expect(screen.getByText('Win Rate')).toBeInTheDocument();
        expect(screen.getByText('rr 2.5 slb 1 tsd 0.02')).toBeInTheDocument();
        expect(screen.getByText('rr 2 slb 1.3 tsd 0.02')).toBeInTheDocument();
        expect(screen.getAllByText('50.0%').length).toBeGreaterThanOrEqual(1);
    });

    it('renders Save button for each variant', () => {
        useResultsContextMock.mockReturnValue({
            results: optimizationResults,
            backtestStatus: null,
            equityData: [],
            pieData: [],
            handleBarClick: vi.fn(),
            selectedTrade: null,
            setSelectedTrade: vi.fn(),
            isTradeModalOpen: false,
            setIsTradeModalOpen: vi.fn(),
        });

        render(
            <Grid container>
                <ResultsPanel />
            </Grid>
        );

        const saveButtons = screen.getAllByRole('button', { name: /save/i });
        expect(saveButtons.length).toBeGreaterThanOrEqual(2);
    });

    it('returns null when results are empty', () => {
        useResultsContextMock.mockReturnValue({
            results: null,
            backtestStatus: null,
            equityData: [],
            pieData: [],
            handleBarClick: vi.fn(),
            selectedTrade: null,
            setSelectedTrade: vi.fn(),
            isTradeModalOpen: false,
            setIsTradeModalOpen: vi.fn(),
        });

        const { container } = render(<ResultsPanel />);

        expect(container.firstChild).toBeNull();
    });
});
