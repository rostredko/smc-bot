export interface ConsoleLinePresentation {
    backgroundColor: string;
    borderBottom: string;
    borderLeft: string;
    color: string;
    fontWeight: string | number;
    margin: string;
    padding: string;
    paddingLeft: string;
}

const basePresentation: ConsoleLinePresentation = {
    backgroundColor: 'transparent',
    borderBottom: 'none',
    borderLeft: 'none',
    color: '#aaaaaa',
    fontWeight: 'normal',
    margin: '0',
    padding: '2px 0',
    paddingLeft: '0',
};

export const getConsoleLinePresentation = (line: string): ConsoleLinePresentation => {
    const isError = line.includes('ERROR') || line.includes('CRITICAL');
    const isWarning = line.includes('WARNING') || line.includes('STOP UPDATE');
    const isWarmupComplete = line.includes('WARM-UP COMPLETE');
    const isSignalThought = line.includes('SIGNAL THESIS:');
    const isSignal = line.includes('SIGNAL GENERATED:');
    const isExecuted = line.includes('EXECUTED');
    const isExitTriggered = line.includes('EXIT TRIGGERED');
    const isTradeClosed = line.includes('TRADE CLOSED');

    if (isWarmupComplete) {
        return {
            ...basePresentation,
            borderBottom: '1px solid #333',
            color: '#00ffff',
            fontWeight: 'bold',
            padding: '12px 0',
        };
    }

    if (isError) {
        return {
            ...basePresentation,
            color: '#ff4444',
            fontWeight: 'bold',
        };
    }

    if (isWarning) {
        return {
            ...basePresentation,
            color: '#ffaa00',
        };
    }

    if (isSignal) {
        return {
            ...basePresentation,
            color: '#00bfff',
            margin: '8px 0 0 0',
        };
    }

    if (isSignalThought) {
        return {
            ...basePresentation,
            backgroundColor: 'rgba(27, 107, 90, 0.18)',
            borderLeft: '2px solid #1b6b5a',
            color: '#7fe7c4',
            margin: '0 0 0 12px',
            padding: '1px 0 1px 12px',
            paddingLeft: '12px',
        };
    }

    if (isExecuted) {
        return {
            ...basePresentation,
            color: '#ffcc00',
        };
    }

    if (isExitTriggered) {
        return {
            ...basePresentation,
            color: '#ffaa00',
        };
    }

    if (isTradeClosed) {
        const pnlMatch = line.match(/PnL:\s*([-\d.]+)/);
        const isLosingTrade = pnlMatch ? parseFloat(pnlMatch[1]) < 0 : false;
        return {
            ...basePresentation,
            borderBottom: '1px dashed #333',
            color: isLosingTrade ? '#ff4444' : '#00ff00',
            fontWeight: 'bold',
            padding: '0 0 8px 0',
        };
    }

    return basePresentation;
};
