import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BacktestHistoryList from './BacktestHistoryList';

const fetchBacktestHistoryMock = vi.fn();
const fetchDetailedResultsMock = vi.fn();
const saveUserConfigTemplateMock = vi.fn();
const deleteBacktestHistoryMock = vi.fn();
const useConfigContextMock = vi.fn();
const useResultsContextMock = vi.fn();

vi.mock('../api/historyApi', () => ({
    fetchBacktestHistory: (...args: unknown[]) => fetchBacktestHistoryMock(...args),
    fetchDetailedResults: (...args: unknown[]) => fetchDetailedResultsMock(...args),
    saveUserConfigTemplate: (...args: unknown[]) => saveUserConfigTemplateMock(...args),
    deleteBacktestHistory: (...args: unknown[]) => deleteBacktestHistoryMock(...args),
}));

vi.mock('../../../app/providers/config/ConfigProvider', () => ({
    useConfigContext: () => useConfigContextMock(),
}));

vi.mock('../../../app/providers/results/ResultsProvider', () => ({
    useResultsContext: () => useResultsContextMock(),
}));

vi.mock('../../../entities/trade/ui/TradeAnalysisChart', () => ({
    default: () => null,
}));

vi.mock('../../../features/trade-details/ui/TradeDetailsModal', () => ({
    default: () => null,
}));

const historyPayload = {
    history: [],
    pagination: {
        total_pages: 1,
        total_count: 0,
        page: 1,
    },
};

describe('BacktestHistoryList', () => {
    beforeEach(() => {
        fetchBacktestHistoryMock.mockReset();
        fetchDetailedResultsMock.mockReset();
        saveUserConfigTemplateMock.mockReset();
        deleteBacktestHistoryMock.mockReset();
        useConfigContextMock.mockReset();
        useResultsContextMock.mockReset();

        fetchBacktestHistoryMock.mockResolvedValue(historyPayload);
        useConfigContextMock.mockReturnValue({
            loadUserConfigs: vi.fn(),
            isLiveRunning: false,
            isLiveStopping: false,
            isRunning: false,
        });
        useResultsContextMock.mockReturnValue({
            backtestStatus: null,
            results: null,
        });
    });

    it('refreshes history when a live session finishes', async () => {
        const { rerender } = render(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(1);
        });

        useConfigContextMock.mockReturnValue({
            loadUserConfigs: vi.fn(),
            isLiveRunning: true,
            isLiveStopping: false,
            isRunning: false,
        });
        rerender(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(1);
        });

        useConfigContextMock.mockReturnValue({
            loadUserConfigs: vi.fn(),
            isLiveRunning: false,
            isLiveStopping: false,
            isRunning: false,
        });
        rerender(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(2);
        });
    });

    it('refreshes history when completed results arrive for the active backtest', async () => {
        const { rerender } = render(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(1);
        });

        useResultsContextMock.mockReturnValue({
            backtestStatus: {
                run_id: 'run-42',
                status: 'completed',
            },
            results: {
                run_id: 'run-42',
                total_pnl: 123,
            },
        });

        rerender(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(2);
        }, { timeout: 2000 });
    });

    it('does not duplicate trailing stop and breakeven fields across detail sections', async () => {
        fetchBacktestHistoryMock.mockResolvedValue({
            history: [
                {
                    filename: 'run-1.json',
                    timestamp: '2026-03-15T18:00:00Z',
                    strategy: 'bt_price_action',
                    is_live: false,
                    total_pnl: 120,
                    initial_capital: 10000,
                    win_rate: 0.5,
                    max_drawdown: 5,
                    total_trades: 10,
                    winning_trades: 5,
                    losing_trades: 5,
                    avg_win: 40,
                    avg_loss: -20,
                    profit_factor: 1.5,
                    sharpe_ratio: 1.1,
                    configuration: {
                        start_date: '2026-01-01',
                        end_date: '2026-02-01',
                        trailing_stop_distance: 0.04,
                        breakeven_trigger_r: 1.5,
                        strategy_config: {
                            risk_reward_ratio: 2,
                        },
                    },
                },
            ],
            pagination: {
                total_pages: 1,
                total_count: 1,
                page: 1,
            },
        });
        fetchDetailedResultsMock.mockResolvedValue({ trades: [] });

        render(<BacktestHistoryList />);

        await waitFor(() => {
            expect(screen.getByText('bt_price_action')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('bt_price_action'));

        await waitFor(() => {
            expect(screen.getAllByText(/Trailing Stop Dist:/)).toHaveLength(1);
            expect(screen.getAllByText(/Breakeven Trigger:/)).toHaveLength(1);
        });

        expect(screen.queryByText(/trailing_stop_distance:/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/breakeven_trigger_r:/i)).not.toBeInTheDocument();
    });

    it('renders optimization variants table with Variants, Profit Factor, Win Rate and highlights best row', async () => {
        fetchBacktestHistoryMock.mockResolvedValue({
            history: [
                {
                    filename: 'opt-run.json',
                    timestamp: '2026-03-17T14:25:00Z',
                    strategy: 'bt_price_action',
                    is_optimization_batch: true,
                    variants_count: 2,
                    total_pnl: 116.27,
                    initial_capital: 10000,
                    win_rate: 50,
                    max_drawdown: 0.6,
                    total_trades: 2,
                    winning_trades: 1,
                    losing_trades: 1,
                    profit_factor: 28.57,
                    sharpe_ratio: 0.11,
                    configuration: {},
                },
            ],
            pagination: { total_pages: 1, total_count: 1, page: 1 },
        });
        fetchDetailedResultsMock.mockResolvedValue({
            variants: [
                {
                    run_id: 'opt_0',
                    params: { risk_reward_ratio: 2.5, sl_buffer_atr: 1, trailing_stop_distance: 0.02 },
                    sharpe_ratio: 0.11,
                    profit_factor: 28.57,
                    max_drawdown: 0.6,
                    total_trades: 2,
                    win_rate: 50,
                    total_pnl: 116.27,
                },
                {
                    run_id: 'opt_1',
                    params: { risk_reward_ratio: 2, sl_buffer_atr: 1.3, trailing_stop_distance: 0.02 },
                    sharpe_ratio: 0.1,
                    profit_factor: 22.83,
                    max_drawdown: 0.6,
                    total_trades: 2,
                    win_rate: 50,
                    total_pnl: 91.82,
                },
            ],
            configuration: {},
        });

        render(<BacktestHistoryList />);

        await waitFor(() => {
            expect(screen.getByText('bt_price_action (2 variants)')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('bt_price_action (2 variants)'));

        expect(fetchDetailedResultsMock).toHaveBeenCalledWith('opt-run.json');

        await waitFor(() => {
            expect(screen.getAllByText('Variants').length).toBeGreaterThanOrEqual(1);
        }, { timeout: 3000 });

        expect(screen.getByText('Profit Factor')).toBeInTheDocument();
        expect(screen.getAllByText('Win Rate').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('rr 2.5 slb 1 tsd 0.02')).toBeInTheDocument();
        expect(screen.getByText('rr 2 slb 1.3 tsd 0.02')).toBeInTheDocument();
        expect(screen.getAllByText('50.0%').length).toBeGreaterThanOrEqual(1);

        const saveButtons = screen.getAllByRole('button', { name: /save/i });
        expect(saveButtons.length).toBeGreaterThanOrEqual(2);
    });
});
