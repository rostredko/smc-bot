import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ConfigPanel from './ConfigPanel';

const useConfigContextMock = vi.fn();
const useResultsContextMock = vi.fn();
const useConsoleContextMock = vi.fn();

vi.mock('../../../app/providers/config/ConfigProvider', () => ({
    useConfigContext: () => useConfigContextMock(),
}));

vi.mock('../../../app/providers/results/ResultsProvider', () => ({
    useResultsContext: () => useResultsContextMock(),
}));

vi.mock('../../../app/providers/console/ConsoleProvider', () => ({
    useConsoleContext: () => useConsoleContextMock(),
}));

vi.mock('../../../shared/ui/StrategyField/StrategyField', () => ({
    default: ({ fieldKey, label }: { fieldKey: string; label: string }) => (
        <div data-testid={`strategy-field-${fieldKey}`}>{label}</div>
    ),
}));

describe('ConfigPanel', () => {
    beforeEach(() => {
        useConfigContextMock.mockReturnValue({
            strategies: [{ name: 'bt_price_action', display_name: 'Price Action', description: '', config_schema: {} }],
            selectedStrategy: 'bt_price_action',
            config: {
                initial_capital: 10000,
                risk_per_trade: 1.5,
                max_drawdown: 20,
                leverage: 10,
                symbol: 'BTC/USDT',
                timeframes: ['4h', '1h'],
                exchange: 'binance',
                exchange_type: 'future',
                execution_mode: 'paper',
                start_date: '2025-01-01',
                end_date: '2025-12-31',
                strategy: 'bt_price_action',
                strategy_config: {},
                trailing_stop_distance: 0.04,
                breakeven_trigger_r: 1.5,
                dynamic_position_sizing: true,
                position_cap_adverse: 0.5,
            },
            strategyConfig: {},
            errors: {},
            isRunning: false,
            isLiveRunning: false,
            isLiveStopping: false,
            isConfigDisabled: false,
            loadDialogOpen: false,
            savedConfigs: [],
            topSymbols: ['BTC/USDT'],
            loadedTemplateName: null,
            handleStrategyChange: vi.fn(),
            handleConfigChange: vi.fn(),
            handleStrategyConfigChange: vi.fn(),
            startBacktest: vi.fn(),
            stopBacktest: vi.fn(),
            startLiveTrading: vi.fn(),
            stopLiveTrading: vi.fn(),
            resetDashboard: vi.fn(),
            resetStrategySettings: vi.fn(),
            handleOpenLoadDialog: vi.fn(),
            setLoadDialogOpen: vi.fn(),
            handleLoadConfig: vi.fn(),
            handleDeleteConfig: vi.fn(),
            handleReorderConfigs: vi.fn(),
        });
        useResultsContextMock.mockReturnValue({
            backtestStatus: null,
            setBacktestStatus: vi.fn(),
            setResults: vi.fn(),
        });
        useConsoleContextMock.mockReturnValue({
            setConsoleOutput: vi.fn(),
        });
    });

    it('renders live exchange selector defaulted to Binance', () => {
        render(<ConfigPanel activeTab="live" />);

        const combobox = screen.getByRole('combobox', { name: /exchange/i });
        expect(combobox).toBeInTheDocument();
        expect(combobox).toHaveTextContent('Binance');
    });

    it('renders POI fields separately and keeps extra controls under advanced parameters', () => {
        useConfigContextMock.mockReturnValue({
            strategies: [{
                name: 'bt_price_action',
                display_name: 'Price Action',
                description: '',
                config_schema: {
                    risk_reward_ratio: { type: 'number', default: 2 },
                    poi_zone_upper_atr_mult: { type: 'number', default: 0.3 },
                    poi_zone_lower_atr_mult: { type: 'number', default: 0.2 },
                    use_premium_discount_filter: { type: 'boolean', default: false },
                    use_pinbar_quality_filter: { type: 'boolean', default: false },
                },
            }],
            selectedStrategy: 'bt_price_action',
            config: {
                initial_capital: 10000,
                risk_per_trade: 1.5,
                max_drawdown: 20,
                leverage: 10,
                symbol: 'BTC/USDT',
                timeframes: ['4h', '1h'],
                exchange: 'binance',
                exchange_type: 'future',
                execution_mode: 'paper',
                start_date: '2025-01-01',
                end_date: '2025-12-31',
                strategy: 'bt_price_action',
                strategy_config: {},
                trailing_stop_distance: 0.04,
                breakeven_trigger_r: 1.5,
                dynamic_position_sizing: true,
                position_cap_adverse: 0.5,
            },
            strategyConfig: {
                poi_zone_upper_atr_mult: 0.3,
                poi_zone_lower_atr_mult: 0.2,
                use_premium_discount_filter: true,
                use_pinbar_quality_filter: false,
            },
            errors: {},
            isRunning: false,
            isLiveRunning: false,
            isLiveStopping: false,
            isConfigDisabled: false,
            loadDialogOpen: false,
            savedConfigs: [],
            topSymbols: ['BTC/USDT'],
            loadedTemplateName: null,
            handleStrategyChange: vi.fn(),
            handleConfigChange: vi.fn(),
            handleStrategyConfigChange: vi.fn(),
            startBacktest: vi.fn(),
            stopBacktest: vi.fn(),
            startLiveTrading: vi.fn(),
            stopLiveTrading: vi.fn(),
            resetDashboard: vi.fn(),
            resetStrategySettings: vi.fn(),
            handleOpenLoadDialog: vi.fn(),
            setLoadDialogOpen: vi.fn(),
            handleLoadConfig: vi.fn(),
            handleDeleteConfig: vi.fn(),
            handleReorderConfigs: vi.fn(),
        });

        render(<ConfigPanel />);

        expect(screen.getByText('Structure & POI')).toBeInTheDocument();
        expect(screen.getByTestId('strategy-field-poi_zone_upper_atr_mult')).toHaveTextContent('POI Upper ATR Multiplier');
        expect(screen.getByTestId('strategy-field-poi_zone_lower_atr_mult')).toHaveTextContent('POI Lower ATR Multiplier');
        expect(screen.getByTestId('strategy-field-use_premium_discount_filter')).toHaveTextContent('Use Premium Discount Filter');
        expect(screen.getAllByText('Use Premium Discount Filter')).toHaveLength(1);
        expect(screen.getByText('Advanced Strategy Parameters')).toBeInTheDocument();
        expect(screen.getByTestId('strategy-field-use_pinbar_quality_filter')).toHaveTextContent('Use Pinbar Quality Filter');
    });

    it('renders Market Context before FVG for fvg_sweep_choch_strategy layouts', () => {
        useConfigContextMock.mockReturnValue({
            strategies: [{
                name: 'fvg_sweep_choch_strategy',
                display_name: 'FVG Sweep CHoCH',
                description: '',
                config_schema: {
                    pivot_span: { type: 'number', default: 2, section: 'Market Context' },
                    enable_structure_filter: { type: 'boolean', default: true, section: 'Market Context' },
                    enable_fvg: { type: 'boolean', default: true, section: 'FVG' },
                    fvg_min_atr_mult: { type: 'number', default: 0.2, section: 'FVG' },
                },
            }],
            selectedStrategy: 'fvg_sweep_choch_strategy',
            config: {
                initial_capital: 10000,
                risk_per_trade: 1.5,
                max_drawdown: 20,
                leverage: 10,
                symbol: 'BTC/USDT',
                timeframes: ['1h', '15m'],
                exchange: 'binance',
                exchange_type: 'future',
                execution_mode: 'paper',
                start_date: '2025-01-01',
                end_date: '2025-12-31',
                strategy: 'fvg_sweep_choch_strategy',
                strategy_config: {},
                trailing_stop_distance: 0,
                breakeven_trigger_r: 0.7,
                dynamic_position_sizing: true,
                position_cap_adverse: 0.5,
            },
            strategyConfig: {
                pivot_span: 2,
                enable_structure_filter: true,
                enable_fvg: true,
                fvg_min_atr_mult: 0.2,
            },
            errors: {},
            isRunning: false,
            isLiveRunning: false,
            isLiveStopping: false,
            isConfigDisabled: false,
            loadDialogOpen: false,
            savedConfigs: [],
            topSymbols: ['BTC/USDT'],
            loadedTemplateName: null,
            handleStrategyChange: vi.fn(),
            handleConfigChange: vi.fn(),
            handleStrategyConfigChange: vi.fn(),
            startBacktest: vi.fn(),
            stopBacktest: vi.fn(),
            startLiveTrading: vi.fn(),
            stopLiveTrading: vi.fn(),
            resetDashboard: vi.fn(),
            resetStrategySettings: vi.fn(),
            handleOpenLoadDialog: vi.fn(),
            setLoadDialogOpen: vi.fn(),
            handleLoadConfig: vi.fn(),
            handleDeleteConfig: vi.fn(),
            handleReorderConfigs: vi.fn(),
        });

        render(<ConfigPanel />);

        const marketContext = screen.getByText('Market Context');
        const fvg = screen.getByText('FVG');

        expect(screen.getByTestId('strategy-field-pivot_span')).toBeInTheDocument();
        expect(screen.getAllByText('Market Context')).toHaveLength(1);
        expect(marketContext.compareDocumentPosition(fvg) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
});
