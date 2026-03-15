import { renderHook, act } from '@testing-library/react';
import { useResultsContext, ResultsProvider } from './ResultsProvider';
import { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const wrapper = ({ children }: { children: ReactNode }) => (
    <ResultsProvider>{children}</ResultsProvider>
);

describe('ResultsProvider hook', () => {
    beforeEach(() => {
        vi.stubGlobal('fetch', vi.fn());
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('returns empty lists for charts initially', () => {
        const { result } = renderHook(() => useResultsContext(), { wrapper });
        expect(result.current.pieData).toEqual([]);
        expect(result.current.equityData).toEqual([
            { date: "Start", equity: 10000 },
            { date: "End", equity: 10000 }
        ]);
    });

    it('processes pieData correctly from results', () => {
        const { result } = renderHook(() => useResultsContext(), { wrapper });

        act(() => {
            result.current.setResults({
                winning_trades: 15,
                losing_trades: 10,
                strategy: "Test",
                total_trades: 25,
                configuration: {},
                logs: []
            } as any);
        });

        expect(result.current.pieData).toEqual([
            { name: "Winning Trades", value: 15, color: "#4caf50" },
            { name: "Losing Trades", value: 10, color: "#f44336" }
        ]);
    });

    it('processes equityData correctly from results', () => {
        const { result } = renderHook(() => useResultsContext(), { wrapper });

        act(() => {
            result.current.setResults({
                initial_capital: 10000,
                total_pnl: 500,
                equity_curve: [
                    { date: "2026-02-21T10:00:00Z", equity: 10200 },
                    { date: "2026-02-22T10:00:00Z", equity: 10500 }
                ],
                trades: [],
                total_trades: 0,
                configuration: {},
                logs: []
            } as any);
        });

        expect(result.current.equityData[0].equity).toBe(10200);
        expect(result.current.equityData[1].equity).toBe(10500);
    });

    it('does not reset running UI state on transient polling failure', async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
        vi.stubGlobal('fetch', fetchMock);
        const setIsRunning = vi.fn();
        const setIsConfigDisabled = vi.fn();
        const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

        const { result } = renderHook(() => useResultsContext(), { wrapper });

        await act(async () => {
            await result.current.checkBacktestStatus('bt_1', setIsRunning, setIsConfigDisabled);
        });

        expect(setIsRunning).not.toHaveBeenCalled();
        expect(setIsConfigDisabled).not.toHaveBeenCalled();
        expect(consoleSpy).not.toHaveBeenCalled();
    });

    it('unlocks the UI when the polled run no longer exists', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: false,
            status: 404,
            json: async () => ({ detail: 'Backtest not found' }),
        });
        vi.stubGlobal('fetch', fetchMock);
        const setIsRunning = vi.fn();
        const setIsConfigDisabled = vi.fn();

        const { result } = renderHook(() => useResultsContext(), { wrapper });

        await act(async () => {
            await result.current.checkBacktestStatus('bt_missing', setIsRunning, setIsConfigDisabled);
        });

        expect(setIsRunning).toHaveBeenCalledWith(false);
        expect(setIsConfigDisabled).toHaveBeenCalledWith(false);
    });
});
