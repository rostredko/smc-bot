import React, { useRef, useEffect } from 'react';
import { Card, CardContent, Box, Button, FormControlLabel, Checkbox, Typography } from '@mui/material';
import { Terminal, DeleteOutline, ContentCopy, ArrowDownward } from '@mui/icons-material';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';

const ConsoleOutput: React.FC = () => {
    const {
        consoleOutput,
        setConsoleOutput,
        autoScroll,
        setAutoScroll
    } = useConsoleContext();

    const virtuosoRef = useRef<VirtuosoHandle>(null);

    // Reliable auto-scroll via imperative scrollToIndex
    useEffect(() => {
        if (autoScroll && consoleOutput.length > 0 && virtuosoRef.current) {
            virtuosoRef.current.scrollToIndex({
                index: consoleOutput.length - 1,
                behavior: 'smooth',
                align: 'end',
            });
        }
    }, [consoleOutput, autoScroll]);

    const renderLogLine = (line: string, index: number) => {
        const isError = line.includes('ERROR') || line.includes('CRITICAL');
        const isWarning = line.includes('WARNING') || line.includes('STOP UPDATE');
        const isWarmupComplete = line.includes('WARM-UP COMPLETE');
        const isSignal = line.includes('SIGNAL GENERATED:');
        const isExecuted = line.includes('EXECUTED');
        const isExitTriggered = line.includes('EXIT TRIGGERED');
        const isTradeClosed = line.includes('TRADE CLOSED');

        let color = '#aaaaaa';
        let fontWeight = 'normal';
        let padding = '2px 0';
        let margin = '0';
        let borderBottom = 'none';

        if (isWarmupComplete) {
            color = '#00ffff';
            fontWeight = 'bold';
            padding = '12px 0';
            borderBottom = '1px solid #333';
        } else if (isError) {
            color = '#ff4444';
            fontWeight = 'bold';
        } else if (isWarning) {
            color = '#ffaa00';
        } else if (isSignal) {
            color = '#00bfff';
            margin = '8px 0 0 0';
        } else if (isExecuted) {
            color = '#ffcc00';
        } else if (isExitTriggered) {
            color = '#ffaa00';
        } else if (isTradeClosed) {
            const pnlMatch = line.match(/PnL:\s*([-\d.]+)/);
            if (pnlMatch && parseFloat(pnlMatch[1]) < 0) {
                color = '#ff4444';
            } else {
                color = '#00ff00';
            }
            fontWeight = 'bold';
            padding = '0 0 8px 0';
            borderBottom = '1px dashed #333';
        }

        return (
            <div key={index} style={{
                color,
                fontWeight,
                padding,
                margin,
                borderBottom,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                lineHeight: 1.5,
                fontFamily: "monospace"
            }}>
                {line}
            </div>
        );
    };

    return (
        <Card>
            <CardContent>
                <Box sx={{ width: '100%' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5, width: '100%' }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Terminal sx={{ fontSize: 22, color: 'primary.main' }} />
                            <Typography variant="h6">Live Output</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                            <Button
                                size="small"
                                variant="outlined"
                                color="inherit"
                                startIcon={<DeleteOutline sx={{ fontSize: 16 }} />}
                                onClick={() => setConsoleOutput([])}
                            >
                                Clear
                            </Button>
                            <Button
                                size="small"
                                variant="outlined"
                                color="inherit"
                                startIcon={<ContentCopy sx={{ fontSize: 16 }} />}
                                onClick={() => {
                                    const text = consoleOutput.join('\n');
                                    navigator.clipboard.writeText(text).catch(() => {
                                        const el = document.createElement('textarea');
                                        el.value = text;
                                        document.body.appendChild(el);
                                        el.select();
                                        document.execCommand('copy');
                                        document.body.removeChild(el);
                                    });
                                }}
                            >
                                Copy
                            </Button>
                        </Box>
                    </Box>
                    <Box
                        sx={{
                            height: 400,
                            overflow: "auto",
                            backgroundColor: "#0b0b0b",
                            color: "#00ff00",
                            p: 2,
                            borderRadius: 1,
                            fontFamily: "monospace",
                            fontSize: "0.875rem",
                            border: "1px solid #333",
                            boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)",
                            width: '100%',
                            boxSizing: 'border-box'
                        }}
                    >
                    {consoleOutput.length === 0 ? (
                        <Typography variant="body2" sx={{ color: "#666" }}>
                            No output yet. Start a backtest to see live results.
                        </Typography>
                    ) : (
                        <Virtuoso
                            ref={virtuosoRef}
                            style={{ height: '100%', width: '100%' }}
                            data={consoleOutput}
                            initialTopMostItemIndex={consoleOutput.length - 1}
                            itemContent={(index: number, line: string) => renderLogLine(line, index)}
                        />
                    )}
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1.5, width: '100%' }}>
                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={autoScroll}
                                    onChange={(e) => setAutoScroll(e.target.checked)}
                                    size="small"
                                    sx={{ color: '#666', '&.Mui-checked': { color: '#00ff00' } }}
                                />
                            }
                            label={
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <ArrowDownward sx={{ fontSize: 14, color: '#888' }} />
                                    <Typography variant="body2" sx={{ color: '#888' }}>Stick to bottom</Typography>
                                </Box>
                            }
                        />
                    </Box>
                </Box>
            </CardContent>
        </Card>
    );
};

export default ConsoleOutput;
