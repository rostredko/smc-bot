import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BacktestProvider } from './BacktestProvider';
import { useConfigContext } from './config/ConfigProvider';
import { useConsoleContext } from './console/ConsoleProvider';
import { useResultsContext } from './results/ResultsProvider';

const fetchMock = vi.fn();

class FakeWebSocket {
    onopen: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;

    constructor(_url: string) {
        setTimeout(() => this.onopen?.(), 0);
    }

    close() {
        this.onclose?.();
    }
}

const jsonResponse = (data: unknown, ok: boolean = true) =>
    Promise.resolve({
        ok,
        json: async () => data,
    });

const Harness = () => {
    const { isRunning, isConfigDisabled, isLiveRunning, isLiveStopping, selectedStrategy } = useConfigContext();
    const { backtestStatus } = useResultsContext();
    const { consoleOutput } = useConsoleContext();

    return (
        <>
            <div data-testid="is-running">{String(isRunning)}</div>
            <div data-testid="is-config-disabled">{String(isConfigDisabled)}</div>
            <div data-testid="is-live-running">{String(isLiveRunning)}</div>
            <div data-testid="is-live-stopping">{String(isLiveStopping)}</div>
            <div data-testid="selected-strategy">{selectedStrategy}</div>
            <div data-testid="status-message">{backtestStatus?.message || ''}</div>
            <div data-testid="console-lines">{consoleOutput.join('|')}</div>
        </>
    );
};

describe('BacktestProvider', () => {
    let runtimeStateResponse: Record<string, unknown>;

    beforeEach(() => {
        runtimeStateResponse = {
            backtest: {
                run_id: 'backtest_active_1',
                status: 'running',
                progress: 35,
                message: 'Warm-up in progress',
                config: {
                    strategy: 'bt_price_action',
                    symbol: 'BTC/USDT',
                    timeframes: ['4h', '1h'],
                    exchange: 'binance',
                    exchange_type: 'future',
                    execution_mode: 'paper',
                    strategy_config: {
                        risk_reward_ratio: 3.0,
                    },
                },
            },
            live: {
                is_running: false,
                run_id: null,
                start_time: null,
                stop_requested: false,
                config: null,
            },
            console: {
                run_id: 'backtest_active_1',
                run_type: 'backtest',
                lines: ['line 1', 'line 2'],
            },
        };
        fetchMock.mockReset();
        fetchMock.mockImplementation((input: RequestInfo | URL) => {
            const url = String(input);
            if (url.endsWith('/api/symbols/top')) {
                return jsonResponse({ symbols: ['BTC/USDT'] });
            }
            if (url.endsWith('/strategies')) {
                return jsonResponse({
                    strategies: [
                        {
                            name: 'bt_price_action',
                            display_name: 'Price Action',
                            description: 'Price action strategy',
                            config_schema: {
                                risk_reward_ratio: { type: 'number', default: 2.0 },
                            },
                        },
                    ],
                });
            }
            if (url.endsWith('/config')) {
                return jsonResponse({});
            }
            if (url.endsWith('/api/live/status')) {
                return jsonResponse({ is_running: false });
            }
            if (url.endsWith('/api/runtime/state')) {
                return jsonResponse(runtimeStateResponse);
            }
            if (url.includes('/backtest/status/backtest_active_1')) {
                return jsonResponse({
                    run_id: 'backtest_active_1',
                    status: 'running',
                    progress: 35,
                    message: 'Warm-up in progress',
                });
            }
            throw new Error(`Unhandled fetch URL in test: ${url}`);
        });

        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('restores active backtest state and console lines after reload', async () => {
        render(
            <BacktestProvider>
                <Harness />
            </BacktestProvider>
        );

        await waitFor(() => {
            expect(screen.getByTestId('is-running')).toHaveTextContent('true');
            expect(screen.getByTestId('is-config-disabled')).toHaveTextContent('true');
            expect(screen.getByTestId('selected-strategy')).toHaveTextContent('bt_price_action');
            expect(screen.getByTestId('status-message')).toHaveTextContent('Warm-up in progress');
            expect(screen.getByTestId('console-lines')).toHaveTextContent('line 1|line 2');
        });
    });

    it('restores active live state and console lines after reload', async () => {
        runtimeStateResponse = {
            backtest: null,
            live: {
                is_running: true,
                run_id: 'live_active_1',
                start_time: '2026-03-15T18:00:00',
                stop_requested: true,
                config: {
                    strategy: 'bt_price_action',
                    symbol: 'BTC/USDT',
                    timeframes: ['4h', '1h'],
                    exchange: 'binance',
                    exchange_type: 'future',
                    execution_mode: 'paper',
                    strategy_config: {
                        risk_reward_ratio: 2.5,
                    },
                },
            },
            console: {
                run_id: 'live_active_1',
                run_type: 'live',
                lines: ['live line 1', 'live line 2'],
            },
        };

        render(
            <BacktestProvider>
                <Harness />
            </BacktestProvider>
        );

        await waitFor(() => {
            expect(screen.getByTestId('is-running')).toHaveTextContent('false');
            expect(screen.getByTestId('is-live-running')).toHaveTextContent('true');
            expect(screen.getByTestId('is-live-stopping')).toHaveTextContent('true');
            expect(screen.getByTestId('is-config-disabled')).toHaveTextContent('true');
            expect(screen.getByTestId('selected-strategy')).toHaveTextContent('bt_price_action');
            expect(screen.getByTestId('console-lines')).toHaveTextContent('live line 1|live line 2');
        });
    });
});
