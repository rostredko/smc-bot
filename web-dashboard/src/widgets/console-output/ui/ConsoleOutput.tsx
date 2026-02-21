import React from 'react';
import { Card, CardHeader, CardContent, Box, Button, FormControlLabel, Checkbox, Typography } from '@mui/material';
import { Virtuoso } from 'react-virtuoso';
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';

const ConsoleOutput: React.FC = () => {
    const {
        consoleOutput,
        setConsoleOutput,
        autoScroll,
        setAutoScroll,
        websocketConnected
    } = useConsoleContext();

    return (
        <Card>
            <CardHeader
                title="Live Output"
                action={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Button
                            size="small"
                            variant="outlined"
                            color="inherit"
                            onClick={() => setConsoleOutput([])}
                        >
                            Clear
                        </Button>
                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={autoScroll}
                                    onChange={(e) => setAutoScroll(e.target.checked)}
                                    size="small"
                                    sx={{ color: '#666', '&.Mui-checked': { color: '#00ff00' } }}
                                />
                            }
                            label={<Typography variant="body2" sx={{ color: '#888' }}>Stick to bottom</Typography>}
                        />
                        <Typography variant="body2" color={websocketConnected ? "success.main" : "error.main"}>
                            {websocketConnected ? "🟢 Live" : "🔴 Offline"}
                        </Typography>
                    </Box>
                }
            />
            <CardContent>
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
                        boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)"
                    }}
                >
                    {consoleOutput.length === 0 ? (
                        <Typography variant="body2" sx={{ color: "#666" }}>
                            No output yet. Start a backtest to see live results.
                        </Typography>
                    ) : (
                        <Virtuoso
                            style={{ height: '100%', width: '100%' }}
                            data={consoleOutput}
                            initialTopMostItemIndex={consoleOutput.length - 1}
                            followOutput={autoScroll ? "smooth" : false}
                            itemContent={(_, line: string) => (
                                <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                    {line}
                                </div>
                            )}
                        />
                    )}
                </Box>
            </CardContent>
        </Card>
    );
};

export default ConsoleOutput;
