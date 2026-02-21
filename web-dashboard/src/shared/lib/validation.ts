import { BacktestConfig } from '../model/types';

export const validateBacktestConfig = (config: BacktestConfig, availableSymbols: string[] = []): Record<string, string> => {
    const newErrors: Record<string, string> = {};
    const timeframeRegex = /^\d+[mhdwM]$/;

    // 1. Timeframe validation
    const tfPrimary = config.timeframes && config.timeframes[0] !== undefined ? config.timeframes[0].trim() : "";

    if (!tfPrimary) {
        newErrors['timeframe_primary'] = "Required";
    } else if (!timeframeRegex.test(tfPrimary)) {
        newErrors['timeframe_primary'] = "Invalid (e.g. 4h)";
    }

    const tfSecondary = config.timeframes && config.timeframes[1] !== undefined ? config.timeframes[1].trim() : "";

    if (!tfSecondary) {
        newErrors['timeframe_secondary'] = "Required";
    } else if (!timeframeRegex.test(tfSecondary)) {
        newErrors['timeframe_secondary'] = "Invalid (e.g. 15m)";
    }

    // 2. Numeric validation
    if (isNaN(config.initial_capital) || config.initial_capital <= 0) newErrors['initial_capital'] = "Must be positive number";
    if (isNaN(config.risk_per_trade) || config.risk_per_trade <= 0) newErrors['risk_per_trade'] = "Must be positive number";
    if (isNaN(config.max_drawdown) || config.max_drawdown <= 0) newErrors['max_drawdown'] = "Must be positive number";
    if (isNaN(config.leverage) || config.leverage <= 0) newErrors['leverage'] = "Must be positive number";

    // 3. Date validation
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!config.start_date || !dateRegex.test(config.start_date)) {
        newErrors['start_date'] = "Invalid (YYYY-MM-DD)";
    }
    if (!config.end_date || !dateRegex.test(config.end_date)) {
        newErrors['end_date'] = "Invalid (YYYY-MM-DD)";
    }

    if (!newErrors['start_date'] && !newErrors['end_date']) {
        if (new Date(config.start_date) >= new Date(config.end_date)) {
            newErrors['start_date'] = "Must be before End Date";
            newErrors['end_date'] = "Must be after Start Date";
        }
    }

    // Symbol validation
    if (!config.symbol || !config.symbol.trim()) {
        newErrors['symbol'] = "Required";
    } else if (availableSymbols.length > 0 && !availableSymbols.includes(config.symbol)) {
        newErrors['symbol'] = "Invalid symbol. Select from dropdown.";
    }

    return newErrors;
};
