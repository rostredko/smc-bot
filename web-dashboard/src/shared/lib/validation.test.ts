import { describe, it, expect } from 'vitest';
import { validateBacktestConfig } from './validation';
import { BacktestConfig } from '../model/types';

describe('validateBacktestConfig', () => {
    const getValidConfig = (): BacktestConfig => ({
        initial_capital: 10000,
        risk_per_trade: 1,
        max_drawdown: 20,
        max_positions: 1,
        leverage: 10,
        symbol: "BTC/USDT",
        timeframes: ["4h", "15m"],
        start_date: "2025-01-01",
        end_date: "2025-12-31",
        strategy: "test_strategy",
        strategy_config: {},
        trailing_stop_distance: 0.05,
        breakeven_trigger_r: 1.5,
        dynamic_position_sizing: true
    });

    it('passes valid configuration', () => {
        const config = getValidConfig();
        const errors = validateBacktestConfig(config, ["BTC/USDT", "ETH/USDT"]);
        expect(Object.keys(errors).length).toBe(0);
    });

    it('fails if timeframes are missing or invalid', () => {
        const config = getValidConfig();
        config.timeframes = ["", "15m"];
        let errors = validateBacktestConfig(config, []);
        expect(errors.timeframe_primary).toBe("Required");

        config.timeframes = ["invalid", "15m"];
        errors = validateBacktestConfig(config, []);
        expect(errors.timeframe_primary).toBe("Invalid (e.g. 4h)");

        config.timeframes = ["4h", ""];
        errors = validateBacktestConfig(config, []);
        expect(errors.timeframe_secondary).toBe("Required");
    });

    it('fails with invalid numbers', () => {
        const config = getValidConfig();
        config.initial_capital = -100;
        config.risk_per_trade = 0;

        const errors = validateBacktestConfig(config, []);
        expect(errors.initial_capital).toBe("Must be positive number");
        expect(errors.risk_per_trade).toBe("Must be positive number");
    });

    it('validates dates correctly (must be valid and chronologically ordered)', () => {
        const config = getValidConfig();
        config.start_date = "2025-12-31";
        config.end_date = "2025-01-01";

        const errors = validateBacktestConfig(config, []);
        expect(errors.start_date).toBe("Must be before End Date");
        expect(errors.end_date).toBe("Must be after Start Date");
    });

    it('validates symbol presence and bounds', () => {
        const config = getValidConfig();
        config.symbol = "";

        let errors = validateBacktestConfig(config, ["BTC/USDT"]);
        expect(errors.symbol).toBe("Required");

        config.symbol = "INVALID/COIN";
        errors = validateBacktestConfig(config, ["BTC/USDT"]);
        expect(errors.symbol).toBe("Invalid symbol. Select from dropdown.");
    });
});
