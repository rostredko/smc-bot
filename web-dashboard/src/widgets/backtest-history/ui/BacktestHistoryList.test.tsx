import { render, waitFor } from '@testing-library/react';
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
});
