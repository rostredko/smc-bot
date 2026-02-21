import React, { useEffect } from 'react';
import { ConfigProvider, useConfigContext } from './config/ConfigProvider';
import { ConsoleProvider } from './console/ConsoleProvider';
import { ResultsProvider, useResultsContext } from './results/ResultsProvider';


// --------------------------------------------------------------------------
// This file now acts as an aggregator for initialization logic if needed,
// but components should consume from specific providers instead of a global one.
// We keep BacktestProvider to wrap the app with the sub-providers.
// --------------------------------------------------------------------------

// Optional: A "Global" context just for orchestration, but we will mostly
// use the sub-contexts directly in the components to prevent re-renders.
export const AppOrchestrator: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const {
        setIsRunning, setIsConfigDisabled,
    } = useConfigContext();

    const { backtestStatus, checkBacktestStatus } = useResultsContext();

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
