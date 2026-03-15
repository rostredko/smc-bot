import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConsoleProvider, useConsoleContext } from './ConsoleProvider';

class FakeWebSocket {
    static instance: FakeWebSocket | null = null;

    onopen: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;

    constructor(_url: string) {
        FakeWebSocket.instance = this;
    }

    close() {
        this.onclose?.();
    }

    emitOpen() {
        this.onopen?.();
    }

    emitMessage(data: string) {
        this.onmessage?.({ data });
    }
}

const Harness = () => {
    const { consoleOutput } = useConsoleContext();
    return <div data-testid="console">{consoleOutput.join("|")}</div>;
};

describe('ConsoleProvider', () => {
    beforeEach(() => {
        FakeWebSocket.instance = null;
        vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('replaces console output from websocket snapshot payload', async () => {
        render(
            <ConsoleProvider>
                <Harness />
            </ConsoleProvider>
        );

        const socket = FakeWebSocket.instance;
        expect(socket).toBeTruthy();

        act(() => {
            socket?.emitOpen();
            socket?.emitMessage(JSON.stringify({
                type: 'console_snapshot',
                run_id: 'live_test',
                run_type: 'live',
                lines: ['line 1', 'line 2'],
            }));
        });

        await waitFor(() => {
            expect(screen.getByTestId('console')).toHaveTextContent('line 1|line 2');
        });
    });
});
