import React from 'react';
import { Container, Grid, Typography, Box, Chip } from '@mui/material';
import { Check, Close } from '@mui/icons-material';
import ConfigPanel from '../../../widgets/config-panel/ui/ConfigPanel';
import ConsoleOutput from '../../../widgets/console-output/ui/ConsoleOutput';
import { lazy, Suspense } from 'react';
import ResultsPanel from '../../../widgets/results-panel/ui/ResultsPanel';
const BacktestHistoryList = lazy(() => import('../../../widgets/backtest-history/ui/BacktestHistoryList'));
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';

const DashboardPage: React.FC = () => {
    const { websocketConnected } = useConsoleContext();

    return (
        <Container maxWidth="xl" sx={{ py: 4 }}>
            <Typography variant="h3" component="h1" gutterBottom align="center">
                Backtest Machine Dashboard
            </Typography>

            <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center' }}>
                <Chip
                    icon={websocketConnected ? <Check /> : <Close />}
                    label={websocketConnected ? "WebSocket Connected" : "WebSocket Disconnected"}
                    color={websocketConnected ? "success" : "error"}
                    variant="outlined"
                />
            </Box>

            <Grid container spacing={3}>
                <Grid item xs={12}>
                    <ConfigPanel />
                </Grid>
                <Grid item xs={12}>
                    <ConsoleOutput />
                </Grid>
                <ResultsPanel />
                <Grid item xs={12} mt={3}>
                    <Suspense fallback={null}>
                        <BacktestHistoryList />
                    </Suspense>
                </Grid>
            </Grid>
        </Container>
    );
};

export default DashboardPage;
