import React, { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';
import { BacktestConfig, Strategy, DEFAULT_CONFIG } from '../../../shared/model/types';
import { API_BASE } from '../../../shared/api/config';
import { validateBacktestConfig } from '../../../shared/lib/validation';

export interface UseConfigReturn {
    strategies: Strategy[];
    selectedStrategy: string;
    config: BacktestConfig;
    strategyConfig: Record<string, any>;
    errors: Record<string, string>;
    isRunning: boolean;
    isLiveRunning: boolean;
    isLiveStopping: boolean;
    isConfigDisabled: boolean;
    loadDialogOpen: boolean;
    savedConfigs: string[];
    topSymbols: string[];
    loadedTemplateName: string | null;

    setStrategies: React.Dispatch<React.SetStateAction<Strategy[]>>;
    setSelectedStrategy: React.Dispatch<React.SetStateAction<string>>;
    setConfig: React.Dispatch<React.SetStateAction<BacktestConfig>>;
    setStrategyConfig: React.Dispatch<React.SetStateAction<Record<string, any>>>;
    setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>;
    setIsRunning: React.Dispatch<React.SetStateAction<boolean>>;
    setIsLiveRunning: React.Dispatch<React.SetStateAction<boolean>>;
    setIsLiveStopping: React.Dispatch<React.SetStateAction<boolean>>;
    setIsConfigDisabled: React.Dispatch<React.SetStateAction<boolean>>;
    setLoadDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setSavedConfigs: React.Dispatch<React.SetStateAction<string[]>>;

    loadStrategies: () => Promise<Strategy[]>;
    loadConfig: (currentStrategies?: Strategy[]) => Promise<void>;
    loadUserConfigs: () => Promise<void>;
    handleOpenLoadDialog: () => void;
    handleLoadConfig: (configName: string) => Promise<void>;
    handleDeleteConfig: (configName: string) => Promise<void>;
    handleReorderConfigs: (newOrder: string[]) => Promise<void>;
    resetDashboard: () => Promise<void>;
    startBacktest: (
        setConsoleOutput: (output: string[]) => void,
        setResults: (results: any) => void,
        setBacktestStatus: (status: any) => void
    ) => Promise<void>;
    stopBacktest: (currentRunId?: string) => Promise<void>;
    startLiveTrading: () => Promise<void>;
    stopLiveTrading: () => Promise<void>;
    checkLiveStatus: () => Promise<void>;
    handleStrategyChange: (strategyName: string) => void;
    handleConfigChange: (key: string, value: any) => void;
    handleStrategyConfigChange: (key: string, value: any) => void;
    resetStrategySettings: () => void;
}

export const ConfigContext = createContext<UseConfigReturn | null>(null);

export const useConfigContext = () => {
    const context = useContext(ConfigContext);
    if (!context) throw new Error("useConfigContext must be used within ConfigProvider");
    return context;
};

export const ConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [strategies, setStrategies] = useState<Strategy[]>([]);
    const [selectedStrategy, setSelectedStrategy] = useState<string>("");
    const [config, setConfig] = useState<BacktestConfig>(DEFAULT_CONFIG);
    const [strategyConfig, setStrategyConfig] = useState<Record<string, any>>({});
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [isRunning, setIsRunning] = useState(false);
    const [isLiveRunning, setIsLiveRunning] = useState(false);
    const [isLiveStopping, setIsLiveStopping] = useState(false);
    const [isConfigDisabled, setIsConfigDisabled] = useState(false);
    const [loadDialogOpen, setLoadDialogOpen] = useState(false);
    const [savedConfigs, setSavedConfigs] = useState<string[]>([]);
    const [topSymbols, setTopSymbols] = useState<string[]>([]);
    const [loadedTemplateName, setLoadedTemplateName] = useState<string | null>(null);
    const [activeBacktestRunId, setActiveBacktestRunId] = useState<string | null>(null);

    const strategyMap = useMemo(() => new Map(strategies.map(s => [s.name, s])), [strategies]);

    const getStrategyDefaults = useCallback((strategyDef: Strategy | undefined, overrides?: Record<string, any>) => {
        if (!strategyDef?.config_schema) return overrides ?? {};
        const defaults: Record<string, any> = {};
        Object.entries(strategyDef.config_schema).forEach(([key, schema]: [string, any]) => {
            defaults[key] = (schema as { default?: any }).default;
        });
        return { ...defaults, ...(overrides ?? {}) };
    }, []);

    useEffect(() => {
        const fetchTopSymbols = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/symbols/top`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.symbols) setTopSymbols(data.symbols);
                }
            } catch (error) { console.error(error); }
        };
        fetchTopSymbols();
    }, []);

    const loadStrategies = async () => {
        try {
            const response = await fetch(`${API_BASE}/strategies`);
            const data = await response.json();
            setStrategies(data.strategies || []);
            return data.strategies || [];
        } catch (error) {
            console.error(error);
            return [];
        }
    };

    const loadConfig = async (currentStrategies: Strategy[] = strategies) => {
        try {
            const response = await fetch(`${API_BASE}/config`);
            const data = await response.json();
            setConfig(prev => ({ ...prev, ...data }));
            if (data.strategy) {
                setSelectedStrategy(data.strategy);
                const strategyDef = currentStrategies.find(s => s.name === data.strategy);
                setStrategyConfig(getStrategyDefaults(strategyDef, data.strategy_config));
            } else {
                setStrategyConfig({});
            }
        } catch (error) { console.error(error); }
    };

    useEffect(() => {
        const loadData = async () => {
            const loadedStrategies = await loadStrategies();
            await loadConfig(loadedStrategies);
        };
        loadData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const loadUserConfigs = async () => {
        try {
            const response = await fetch(`${API_BASE}/api/user-configs`);
            if (response.ok) {
                const data = await response.json();
                setSavedConfigs(data.configs || []);
            }
        } catch (error) { console.error(error); }
    };

    const handleReorderConfigs = async (newOrder: string[]) => {
        setSavedConfigs(newOrder); // optimistic update
        try {
            const response = await fetch(`${API_BASE}/api/user-configs/reorder`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order: newOrder }),
            });
            if (response.ok) {
                const data = await response.json();
                setSavedConfigs(data.configs || newOrder);
            } else {
                await loadUserConfigs(); // revert on failure
            }
        } catch (error) {
            console.error(error);
            await loadUserConfigs(); // revert on error
        }
    };

    const handleOpenLoadDialog = () => {
        loadUserConfigs();
        setLoadDialogOpen(true);
    };

    const handleLoadConfig = async (configName: string) => {
        try {
            const response = await fetch(`${API_BASE}/api/user-configs/${configName}`);
            if (response.ok) {
                const data = await response.json();

                // Handle potentially nested strategy objects from older formats or direct DB injection
                const strategyName = typeof data.strategy === 'object' && data.strategy !== null
                    ? data.strategy.name
                    : data.strategy;

                const strategyConfigToLoad = typeof data.strategy === 'object' && data.strategy !== null && data.strategy.config
                    ? data.strategy.config
                    : data.strategy_config;

                setConfig(prev => ({
                    ...prev,
                    ...data,
                    strategy: strategyName,
                    strategy_config: strategyConfigToLoad
                }));

                if (strategyName) {
                    setSelectedStrategy(strategyName);
                    const strategyDef = strategyMap.get(strategyName);
                    setStrategyConfig(getStrategyDefaults(strategyDef, strategyConfigToLoad));
                } else {
                    setStrategyConfig({});
                }
                setLoadDialogOpen(false);
                setLoadedTemplateName(configName);
            }
        } catch (error) { console.error(error); }
    };

    const handleDeleteConfig = async (configName: string) => {
        if (!window.confirm(`Are you sure you want to delete "${configName}"?`)) return;
        try {
            const response = await fetch(`${API_BASE}/api/user-configs/${configName}`, { method: 'DELETE' });
            if (response.ok) loadUserConfigs();
        } catch (error) { console.error(error); }
    };

    const resetDashboard = async () => {
        setIsRunning(false);
        setIsConfigDisabled(false);
        setLoadedTemplateName(null);
        setConfig(DEFAULT_CONFIG);
        setSelectedStrategy("");
        setStrategyConfig({});
    };

    const resetStrategySettings = () => {
        setLoadedTemplateName(null);
        if (selectedStrategy && selectedStrategy.trim() !== "") {
            const strategy = strategyMap.get(selectedStrategy);
            setStrategyConfig(getStrategyDefaults(strategy));
            // Keep the selected strategy, just reset config fields
            setConfig({ ...DEFAULT_CONFIG, strategy: selectedStrategy });
        } else {
            setStrategyConfig({});
            setConfig(DEFAULT_CONFIG);
        }
    };

    const startBacktest = async (
        setConsoleOutput: (output: string[]) => void,
        setResults: (results: any) => void,
        setBacktestStatus: (status: any) => void
    ) => {
        const newErrors = validateBacktestConfig(config, topSymbols);
        if (Object.keys(newErrors).length > 0) {
            setErrors(newErrors);
            return;
        }
        setErrors({});

        try {
            setIsRunning(true);
            setIsConfigDisabled(true);
            setConsoleOutput([]);
            setResults(null);

            const requestBody = {
                config: {
                    ...config,
                    timeframes: config.timeframes.filter(t => t.trim() !== ""),
                    strategy_config: strategyConfig,
                    ...(loadedTemplateName ? { loaded_template_name: loadedTemplateName } : {}),
                }
            };

            const response = await fetch(`${API_BASE}/backtest/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestBody)
            });

            if (response.ok) {
                const data = await response.json();
                setActiveBacktestRunId(data.run_id ?? null);
                setBacktestStatus({
                    run_id: data.run_id,
                    status: "running",
                    progress: 0,
                    message: "Starting backtest..."
                });
            } else {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || `Backtest start failed: HTTP ${response.status}`);
            }
        } catch (error) {
            console.error("Failed to start backtest:", error);
            setActiveBacktestRunId(null);
            setIsRunning(false);
            setIsConfigDisabled(false);
        }
    };

    const stopBacktest = async (currentRunId?: string) => {
        try {
            const runId = currentRunId || activeBacktestRunId;
            if (runId) {
                await fetch(`${API_BASE}/backtest/${runId}`, { method: "DELETE" });
            } else {
                await fetch(`${API_BASE}/backtest/active/stop`, { method: "POST" });
            }
        } catch (error) { console.error("Failed to stop backtest:", error); }
    };

    const startLiveTrading = async () => {
        const newErrors = validateBacktestConfig(config, topSymbols);
        if (Object.keys(newErrors).length > 0) {
            setErrors(newErrors);
            return;
        }
        setErrors({});
        setIsLiveStopping(false);

        try {
            const requestBody = {
                config: {
                    ...config,
                    timeframes: config.timeframes.filter((t: string) => t.trim() !== ""),
                    strategy_config: strategyConfig,
                    ...(loadedTemplateName ? { loaded_template_name: loadedTemplateName } : {}),
                }
            };

            const response = await fetch(`${API_BASE}/api/live/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestBody)
            });
            if (response.ok) {
                setIsLiveRunning(true);
            } else {
                const err = await response.json();
                console.error("Failed to start live trading:", err);
            }
        } catch (error) {
            console.error("Failed to start live trading:", error);
        }
    };

    const stopLiveTrading = async () => {
        try {
            const response = await fetch(`${API_BASE}/api/live/stop`, { method: "POST" });
            if (response.ok) {
                setIsLiveStopping(true);
            }
        } catch (error) {
            console.error("Failed to stop live trading:", error);
        }
    };

    const checkLiveStatus = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE}/api/live/status`);
            if (response.ok) {
                const data = await response.json();
                setIsLiveRunning(data.is_running);
                if (!data.is_running) {
                    setIsLiveStopping(false);
                }
            }
        } catch (error) {
            console.error("Failed to check live trading status:", error);
        }
    }, []);

    // Check live status on mount
    useEffect(() => {
        checkLiveStatus();
    }, [checkLiveStatus]);

    useEffect(() => {
        if (!isRunning) {
            setActiveBacktestRunId(null);
        }
    }, [isRunning]);

    // Poll live status while running/stopping so UI reflects state promptly.
    useEffect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (isLiveRunning || isLiveStopping) {
            const periodMs = isLiveStopping ? 1000 : 5000;
            interval = setInterval(() => checkLiveStatus(), periodMs);
        }
        return () => { if (interval) clearInterval(interval); };
    }, [isLiveRunning, isLiveStopping, checkLiveStatus]);

    const handleStrategyChange = useCallback((strategyName: string) => {
        setSelectedStrategy(strategyName);
        setConfig(prev => ({ ...prev, strategy: strategyName }));

        if (strategyName && strategyName.trim() !== "") {
            const strategy = strategyMap.get(strategyName);
            setStrategyConfig(getStrategyDefaults(strategy));
            setIsConfigDisabled(false);
        } else {
            setStrategyConfig({});
            setIsConfigDisabled(false);
        }
    }, [strategyMap, getStrategyDefaults]);

    const handleConfigChange = useCallback((key: string, value: any) => {
        setConfig(prev => ({ ...prev, [key]: value }));
        if (errors[key]) {
            setErrors(prev => {
                const newErrors = { ...prev };
                delete newErrors[key];
                return newErrors;
            });
        }
        if (key === 'timeframes') {
            setErrors(prev => {
                const newErrors = { ...prev };
                delete newErrors['timeframe_primary'];
                delete newErrors['timeframe_secondary'];
                return newErrors;
            });
        }
    }, [errors]);

    const handleStrategyConfigChange = useCallback((key: string, value: any) => {
        setStrategyConfig(prev => ({ ...prev, [key]: value }));
    }, []);

    const value = {
        strategies, selectedStrategy, config, strategyConfig, errors,
        isRunning, isLiveRunning, isLiveStopping, isConfigDisabled, loadDialogOpen, savedConfigs, topSymbols, loadedTemplateName,
        setStrategies, setSelectedStrategy, setConfig, setStrategyConfig, setErrors,
        setIsRunning, setIsLiveRunning, setIsLiveStopping, setIsConfigDisabled, setLoadDialogOpen, setSavedConfigs,
        loadStrategies, loadConfig, loadUserConfigs, handleOpenLoadDialog,
        handleLoadConfig, handleDeleteConfig, handleReorderConfigs, resetDashboard, startBacktest,
        stopBacktest, startLiveTrading, stopLiveTrading, checkLiveStatus, handleStrategyChange, handleConfigChange, handleStrategyConfigChange,
        resetStrategySettings
    };

    return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
};
