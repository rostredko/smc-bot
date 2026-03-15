import { BacktestConfig } from '../model/types';

type ValidationOptions = {
    requireSecondaryTimeframe?: boolean;
    requireDates?: boolean;
};

const timeframeToMinutes = (tf: string): number | null => {
    const match = tf.match(/^(\d+)([mhdwM])$/);
    if (!match) return null;
    const value = Number(match[1]);
    const unit = match[2];
    const multipliers: Record<string, number> = {
        m: 1,
        h: 60,
        d: 60 * 24,
        w: 60 * 24 * 7,
        M: 60 * 24 * 30,
    };
    return value * multipliers[unit];
};

const validateCoreConfig = (
    config: BacktestConfig,
    availableSymbols: string[] = [],
    options: ValidationOptions = {}
): Record<string, string> => {
    const newErrors: Record<string, string> = {};
    const timeframeRegex = /^\d+[mhdwM]$/;
    const requireSecondaryTimeframe = options.requireSecondaryTimeframe ?? true;
    const requireDates = options.requireDates ?? true;

    // 1. Timeframe validation
    const tfPrimary = config.timeframes && config.timeframes[0] !== undefined ? config.timeframes[0].trim() : "";

    if (!tfPrimary) {
        newErrors['timeframe_primary'] = "Required";
    } else if (!timeframeRegex.test(tfPrimary)) {
        newErrors['timeframe_primary'] = "Invalid (e.g. 4h)";
    }

    const tfSecondary = config.timeframes && config.timeframes[1] !== undefined ? config.timeframes[1].trim() : "";

    if (!tfSecondary && requireSecondaryTimeframe) {
        newErrors['timeframe_secondary'] = "Required";
    } else if (tfSecondary && !timeframeRegex.test(tfSecondary)) {
        newErrors['timeframe_secondary'] = "Invalid (e.g. 15m)";
    }

    if (!newErrors['timeframe_primary'] && !newErrors['timeframe_secondary']) {
        const tfPrimaryMinutes = timeframeToMinutes(tfPrimary);
        const tfSecondaryMinutes = tfSecondary ? timeframeToMinutes(tfSecondary) : null;
        if (
            tfPrimaryMinutes !== null &&
            tfSecondaryMinutes !== null &&
            tfPrimaryMinutes < tfSecondaryMinutes
        ) {
            const msg = "Primary TF must be >= Entry TF";
            newErrors['timeframe_primary'] = msg;
            newErrors['timeframe_secondary'] = msg;
        }
    }

    // 2. Numeric validation
    if (isNaN(config.initial_capital) || config.initial_capital <= 0) newErrors['initial_capital'] = "Must be positive number";
    if (isNaN(config.risk_per_trade) || config.risk_per_trade <= 0) newErrors['risk_per_trade'] = "Must be positive number";
    if (isNaN(config.max_drawdown) || config.max_drawdown <= 0) newErrors['max_drawdown'] = "Must be positive number";
    if (isNaN(config.leverage) || config.leverage <= 0) newErrors['leverage'] = "Must be positive number";
    if (
        isNaN(config.position_cap_adverse) ||
        config.position_cap_adverse < 0.5 ||
        config.position_cap_adverse > 1
    ) {
        newErrors['position_cap_adverse'] = "Must be between 0.5 and 1.0";
    }

    // 3. Date validation
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (requireDates && (!config.start_date || !dateRegex.test(config.start_date))) {
        newErrors['start_date'] = "Invalid (YYYY-MM-DD)";
    } else if (!requireDates && config.start_date && !dateRegex.test(config.start_date)) {
        newErrors['start_date'] = "Invalid (YYYY-MM-DD)";
    }
    if (requireDates && (!config.end_date || !dateRegex.test(config.end_date))) {
        newErrors['end_date'] = "Invalid (YYYY-MM-DD)";
    } else if (!requireDates && config.end_date && !dateRegex.test(config.end_date)) {
        newErrors['end_date'] = "Invalid (YYYY-MM-DD)";
    }

    if (!newErrors['start_date'] && !newErrors['end_date']) {
        if (
            config.start_date &&
            config.end_date &&
            new Date(config.start_date) >= new Date(config.end_date)
        ) {
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

export const validateBacktestConfig = (config: BacktestConfig, availableSymbols: string[] = []): Record<string, string> => {
    return validateCoreConfig(config, availableSymbols, {
        requireSecondaryTimeframe: true,
        requireDates: true,
    });
};

export const validateLiveConfig = (config: BacktestConfig, availableSymbols: string[] = []): Record<string, string> => {
    const newErrors = validateCoreConfig(config, availableSymbols, {
        requireSecondaryTimeframe: false,
        requireDates: false,
    });
    const exchange = String(config.exchange || "").trim().toLowerCase();
    const executionMode = String(config.execution_mode || "paper").trim().toLowerCase();

    if (!exchange) {
        newErrors['exchange'] = "Required";
    } else if (exchange !== "binance") {
        newErrors['exchange'] = "Only Binance is supported for live paper testing";
    }

    if (!executionMode) {
        newErrors['execution_mode'] = "Required";
    } else if (executionMode !== "paper") {
        newErrors['execution_mode'] = "Only paper execution mode is enabled right now";
    }

    return newErrors;
};
