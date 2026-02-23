import React, { createContext, useContext, useState, useMemo, useCallback } from 'react';
import { BacktestResults, BacktestStatus } from '../../../shared/model/types';
import { API_BASE } from '../../../shared/api/config';

export interface UseResultsReturn {
    backtestStatus: BacktestStatus | null;
    results: BacktestResults | null;
    selectedTrade: any | null;
    isTradeModalOpen: boolean;
    pieData: any[];
    equityData: any[];

    setBacktestStatus: React.Dispatch<React.SetStateAction<BacktestStatus | null>>;
    setResults: React.Dispatch<React.SetStateAction<BacktestResults | null>>;
    setSelectedTrade: React.Dispatch<React.SetStateAction<any | null>>;
    setIsTradeModalOpen: React.Dispatch<React.SetStateAction<boolean>>;
    handleBarClick: (trade: any) => void;
    checkBacktestStatus: (runId: string, setIsRunning: (r: boolean) => void, setIsConfigDisabled: (c: boolean) => void) => Promise<void>;
}

export const ResultsContext = createContext<UseResultsReturn | null>(null);

export const useResultsContext = () => {
    const context = useContext(ResultsContext);
    if (!context) throw new Error("useResultsContext must be used within ResultsProvider");
    return context;
};

export const ResultsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [backtestStatus, setBacktestStatus] = useState<BacktestStatus | null>(null);
    const [results, setResults] = useState<BacktestResults | null>(null);
    const [selectedTrade, setSelectedTrade] = useState<any | null>(null);
    const [isTradeModalOpen, setIsTradeModalOpen] = useState(false);

    const handleBarClick = useCallback((trade: any) => {
        if (trade) {
            setSelectedTrade(trade);
            setIsTradeModalOpen(true);
        }
    }, []);

    const checkBacktestStatus = useCallback(async (runId: string, setIsRunning: (r: boolean) => void, setIsConfigDisabled: (c: boolean) => void) => {
        try {
            const response = await fetch(`${API_BASE}/backtest/status/${runId}`);
            const status = await response.json();
            setBacktestStatus(status);

            if (!response.ok) {
                setIsRunning(false);
                setIsConfigDisabled(false);
                return;
            }
            if (status?.status === "completed" || status?.status === "cancelled") {
                setIsRunning(false);
                setIsConfigDisabled(false);
                setResults(status.results);
            } else if (status?.status === "failed") {
                setIsRunning(false);
                setIsConfigDisabled(false);
            }
        } catch (error) {
            console.error("Failed to check status:", error);
            setIsRunning(false);
            setIsConfigDisabled(false);
        }
    }, []);

    const equityData = useMemo(() => {
        if (!results?.equity_curve || results.equity_curve.length === 0) {
            return [
                { date: "Start", equity: results?.initial_capital || 10000 },
                { date: "End", equity: (results?.initial_capital || 10000) + (results?.total_pnl || 0) }
            ];
        }
        return results.equity_curve.map(point => ({
            date: new Date(point.date).toLocaleDateString(),
            equity: point.equity
        }));
    }, [results]);

    const pieData = useMemo(() => {
        if (!results) return [];
        const winning = results.winning_trades || 0;
        const losing = results.losing_trades || 0;

        if (winning === 0 && losing === 0) {
            return [{ name: "No Trades", value: 1, color: "#9e9e9e" }];
        }

        return [
            { name: "Winning Trades", value: winning, color: "#4caf50" },
            { name: "Losing Trades", value: losing, color: "#f44336" }
        ];
    }, [results]);

    const value = {
        backtestStatus, results, selectedTrade, isTradeModalOpen, pieData, equityData,
        setBacktestStatus, setResults, setSelectedTrade, setIsTradeModalOpen, handleBarClick, checkBacktestStatus
    };

    return (
        <ResultsContext.Provider value={value}>
            {children}
        </ResultsContext.Provider>
    );
};
