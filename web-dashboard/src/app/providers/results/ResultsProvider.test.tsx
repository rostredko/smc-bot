import { renderHook, act } from '@testing-library/react';
import { useResultsContext, ResultsProvider } from './ResultsProvider';
import { ReactNode } from 'react';

const wrapper = ({ children }: { children: ReactNode }) => (
    <ResultsProvider>{children}</ResultsProvider>
);

describe('ResultsProvider hook', () => {
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
});
