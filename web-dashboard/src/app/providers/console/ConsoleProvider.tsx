import React, { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react';

export interface UseConsoleReturn {
    consoleOutput: string[];
    setConsoleOutput: React.Dispatch<React.SetStateAction<string[]>>;
    websocketConnected: boolean;
    autoScroll: boolean;
    setAutoScroll: React.Dispatch<React.SetStateAction<boolean>>;
}

export const ConsoleContext = createContext<UseConsoleReturn | null>(null);

export const useConsoleContext = () => {
    const context = useContext(ConsoleContext);
    if (!context) throw new Error("useConsoleContext must be used within ConsoleProvider");
    return context;
};

export const ConsoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [consoleOutput, setConsoleOutput] = useState<string[]>([]);
    const [websocketConnected, setWebsocketConnected] = useState(false);
    const [autoScroll, setAutoScroll] = useState(true);
    const consoleEndRef = useRef<HTMLDivElement>(null);
    const websocketRef = useRef<WebSocket | null>(null);

    // Auto-scroll console to bottom
    const scrollToBottom = () => {
        setTimeout(() => {
            consoleEndRef.current?.scrollIntoView({ behavior: "auto" });
        }, 0);
    };

    useEffect(() => {
        if (autoScroll) {
            scrollToBottom();
        }
    }, [consoleOutput, autoScroll]);

    // WebSocket buffering to prevent render flooding
    const logBuffer = useRef<string[]>([]);
    const lastFlushTime = useRef<number>(0);
    const flushTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

    const flushLogs = useCallback(() => {
        const messagesToFlush = [...logBuffer.current];
        if (messagesToFlush.length === 0) return;

        logBuffer.current = [];

        setConsoleOutput(prev => {
            const combined = [...prev, ...messagesToFlush];
            return combined.slice(-5000); // keep only last 5000 lines
        });

        lastFlushTime.current = Date.now();
        flushTimeout.current = null;
    }, []);

    const destroyed = useRef(false);

    const connectWebSocket = useCallback(() => {
        if (destroyed.current) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname;
        const port = '8000';
        const wsUrl = `${protocol}//${host}:${port}/ws`;

        try {
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                setWebsocketConnected(true);
            };

            ws.onmessage = (event) => {
                if (event.data && event.data.trim()) {
                    logBuffer.current.push(event.data);
                    const now = Date.now();
                    if (!flushTimeout.current) {
                        if (now - lastFlushTime.current >= 100) {
                            flushLogs();
                        } else {
                            flushTimeout.current = setTimeout(flushLogs, 100);
                        }
                    }
                }
            };

            // Suppress browser's default "WebSocket connection failed" console error
            ws.onerror = () => { /* intentionally silenced — onclose handles reconnect */ };

            ws.onclose = () => {
                setWebsocketConnected(false);
                if (flushTimeout.current) {
                    clearTimeout(flushTimeout.current);
                    flushLogs();
                }
                // Only reconnect if the provider is still mounted
                if (!destroyed.current) {
                    setTimeout(() => connectWebSocket(), 3000);
                }
            };

            websocketRef.current = ws;
        } catch {
            // Silently ignore — backend may not be running yet
        }
    }, [flushLogs]);

    useEffect(() => {
        destroyed.current = false;
        connectWebSocket();
        return () => {
            destroyed.current = true;
            if (websocketRef.current) {
                websocketRef.current.onclose = null;  // prevent reconnect on intentional close
                websocketRef.current.onerror = null;
                websocketRef.current.close();
            }
            if (flushTimeout.current) {
                clearTimeout(flushTimeout.current);
            }
        };
    }, [connectWebSocket]);


    const value = {
        consoleOutput, setConsoleOutput,
        websocketConnected, autoScroll, setAutoScroll
    };

    return (
        <ConsoleContext.Provider value={value}>
            {children}
        </ConsoleContext.Provider>
    );
};
