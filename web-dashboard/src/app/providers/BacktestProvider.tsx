import React, { useEffect, useRef } from 'react';
import { ConfigProvider, useConfigContext } from './config/ConfigProvider';
import { ConsoleProvider } from './console/ConsoleProvider';
import { useConsoleContext } from './console/ConsoleProvider';
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
        setIsRunning, setIsConfigDisabled, setIsLiveRunning, setIsLiveStopping,
        isLiveRunning, isRunning, isInitialLoadComplete, restoreRuntimeConfig,
    } = useConfigContext();

    const { backtestStatus, checkBacktestStatus, setBacktestStatus, setResults } = useResultsContext();
    const { setConsoleOutput } = useConsoleContext();

    useEffect(() => {
        if (!isInitialLoadComplete) {
            return;
        }

        let ignore = false;

        const restoreRuntimeState = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/runtime/state`);
                if (!response.ok || ignore) {
                    return;
                }

                const data = await response.json();
                const activeBacktest = data?.backtest;
                const activeLive = data?.live;
                const consoleLines = Array.isArray(data?.console?.lines) ? data.console.lines : [];

                const hasActiveBacktest = Boolean(activeBacktest?.run_id && activeBacktest?.status === "running");
                const hasActiveLive = Boolean(activeLive?.is_running);

                if ((hasActiveBacktest || hasActiveLive) && !ignore) {
                    setConsoleOutput(consoleLines.map((line: unknown) => String(line)));
                    setResults(null);
                }

                if (hasActiveBacktest && !ignore) {
                    setIsRunning(true);
                    setIsConfigDisabled(true);
                    setBacktestStatus({
                        run_id: activeBacktest.run_id,
                        status: activeBacktest.status,
                        progress: activeBacktest.progress,
                        message: activeBacktest.message,
                        error: activeBacktest.error,
                        config: activeBacktest.config,
                    });
                    if (activeBacktest?.config) {
                        restoreRuntimeConfig(activeBacktest.config);
                    }
                }

                if (hasActiveLive && !ignore) {
                    setIsLiveRunning(true);
                    setIsLiveStopping(Boolean(activeLive?.stop_requested));
                    setIsConfigDisabled(true);
                    if (activeLive?.config) {
                        restoreRuntimeConfig(activeLive.config);
                    }
                }

                if (!hasActiveBacktest && !ignore) {
                    setIsRunning(false);
                }
                if (!hasActiveLive && !ignore) {
                    setIsLiveRunning(false);
                    setIsLiveStopping(false);
                }
                if (!hasActiveBacktest && !hasActiveLive && !ignore) {
                    setIsConfigDisabled(false);
                }
            } catch (error) {
                if (!ignore) {
                    console.error("Failed to restore runtime state:", error);
                }
            }
        };

        restoreRuntimeState();
        return () => {
            ignore = true;
        };
    }, [
        isInitialLoadComplete,
        restoreRuntimeConfig,
        setConsoleOutput,
        setIsConfigDisabled,
        setIsLiveRunning,
        setIsLiveStopping,
        setIsRunning,
        setBacktestStatus,
        setResults,
    ]);

    // Status Polling
    useEffect(() => {
        let interval: ReturnType<typeof setInterval> | undefined;
        let controller: AbortController | null = null;

        const pollStatus = () => {
            if (!backtestStatus?.run_id) {
                return;
            }
            controller?.abort();
            controller = new AbortController();
            checkBacktestStatus(backtestStatus.run_id, setIsRunning, setIsConfigDisabled, controller.signal);
        };

        if (backtestStatus?.status === "running" && backtestStatus.run_id) {
            pollStatus();
            interval = setInterval(pollStatus, 1000);
        }
        return () => {
            if (interval) {
                clearInterval(interval);
            }
            controller?.abort();
        };
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
