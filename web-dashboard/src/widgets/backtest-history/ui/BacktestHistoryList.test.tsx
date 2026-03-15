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
        });
        useResultsContextMock.mockReturnValue({
            backtestStatus: null,
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
        });
        rerender(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(1);
        });

        useConfigContextMock.mockReturnValue({
            loadUserConfigs: vi.fn(),
            isLiveRunning: false,
            isLiveStopping: false,
        });
        rerender(<BacktestHistoryList />);

        await waitFor(() => {
            expect(fetchBacktestHistoryMock).toHaveBeenCalledTimes(2);
        });
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
});
