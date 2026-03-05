import React, { useEffect, useRef } from 'react';
import { ConfigProvider, useConfigContext } from './config/ConfigProvider';
import { ConsoleProvider } from './console/ConsoleProvider';
import { ResultsProvider, useResultsContext } from './results/ResultsProvider';
import { API_BASE } from '../../shared/api/config';


// --------------------------------------------------------------------------
// This file now acts as an aggregator for initialization logic if needed,
// but components should consume from specific providers instead of a global one.
// We keep BacktestProvider to wrap the app with the sub-providers.
// --------------------------------------------------------------------------

// Optional: A "Global" context just for orchestration, but we will mostly
// use the sub-contexts directly in the components to prevent re-renders.
export const AppOrchestrator: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const {
        setIsRunning, setIsConfigDisabled, isLiveRunning, isRunning,
    } = useConfigContext();

    const { backtestStatus, checkBacktestStatus, setResults } = useResultsContext();

    // Status Polling
    useEffect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (backtestStatus?.status === "running" && backtestStatus.run_id) {
            interval = setInterval(() => {
                checkBacktestStatus(backtestStatus.run_id, setIsRunning, setIsConfigDisabled);
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [backtestStatus?.status, backtestStatus?.run_id, checkBacktestStatus, setIsRunning, setIsConfigDisabled]);

    const prevLiveRunningRef = useRef<boolean>(isLiveRunning);
    useEffect(() => {
        let ignore = false;
        const wasRunning = prevLiveRunningRef.current;

        const loadLatestLiveResult = async () => {
            try {
                const historyResp = await fetch(`${API_BASE}/api/backtest/history?page=1&page_size=30`);
                if (!historyResp.ok || ignore) return;

                const historyData = await historyResp.json();
                const latestLive = (historyData?.history || []).find((item: any) => Boolean(item?.is_live));
                if (!latestLive?.filename || ignore) return;

                const detailsResp = await fetch(`${API_BASE}/results/${latestLive.filename}`);
                if (!detailsResp.ok || ignore) return;

                const details = await detailsResp.json();
                if (!ignore && !isLiveRunning && !isRunning && details) {
                    setResults(details);
                }
            } catch (error) {
                if (!ignore) {
                    console.error("Failed to load latest live result:", error);
                }
            }
        };

        if (wasRunning && !isLiveRunning) {
            // Live run finished: auto-populate ResultsPanel from latest persisted live result.
            loadLatestLiveResult();
        }
        prevLiveRunningRef.current = isLiveRunning;
        return () => {
            ignore = true;
        };
    }, [isLiveRunning, isRunning, setResults]);


    // We replace the original context with this orchestrator.
    // We'll export the wrapper that provides all three below.
    return <>{children}</>;
};

export const BacktestProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    return (
        <ConfigProvider>
            <ConsoleProvider>
                <ResultsProvider>
                    <AppOrchestrator>
                        {children}
                    </AppOrchestrator>
                </ResultsProvider>
            </ConsoleProvider>
        </ConfigProvider>
    );
};
