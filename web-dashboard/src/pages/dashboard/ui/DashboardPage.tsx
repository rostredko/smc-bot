import React from 'react';
import { Container, Grid, Typography, Box, Paper, Tooltip, Tabs, Tab } from '@mui/material';
import { Dashboard, Timeline, PlayArrow, FlashOn } from '@mui/icons-material';
import ConfigPanel from '../../../widgets/config-panel/ui/ConfigPanel';
import ConsoleOutput from '../../../widgets/console-output/ui/ConsoleOutput';
import { lazy, Suspense } from 'react';
import ResultsPanel from '../../../widgets/results-panel/ui/ResultsPanel';
const BacktestHistoryList = lazy(() => import('../../../widgets/backtest-history/ui/BacktestHistoryList'));
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';
import { useConfigContext } from '../../../app/providers/config/ConfigProvider';

const DashboardPage: React.FC = () => {
    const { websocketConnected } = useConsoleContext();
    const { activeTab, setActiveTab } = useConfigContext();
    const tabValue = activeTab ?? 'backtest';

    const handleTabChange = (_: React.SyntheticEvent, v: 'backtest' | 'live') => {
        setActiveTab?.(v);
    };

    return (
        <Container maxWidth="xl" sx={{ py: { xs: 2, sm: 4 }, px: { xs: 1.5, sm: 3 } }}>
            <Paper
                elevation={0}
                sx={{
                    mb: { xs: 2, sm: 3 },
                    px: { xs: 2, sm: 3 },
                    py: { xs: 1.5, sm: 2.5 },
                    borderRadius: 3,
                    background: 'linear-gradient(to right, #2d2d2d, #5a5a5a, #7a7a7a)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    display: 'flex',
                    flexDirection: { xs: 'column', sm: 'row' },
                    alignItems: { xs: 'flex-start', sm: 'center' },
                    justifyContent: 'space-between',
                    gap: 2,
                }}
            >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Box
                        sx={{
                            width: 40,
                            height: 40,
                            borderRadius: 2,
                            bgcolor: 'primary.main',
                            color: 'primary.contrastText',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            boxShadow: '0 0 20px rgba(33,150,243,0.4)',
                        }}
                    >
                        <Dashboard fontSize="medium" />
                    </Box>
                    <Box>
                        <Typography variant="h5" component="h1" sx={{ color: '#fff', fontWeight: 600, display: 'flex', alignItems: 'baseline', gap: 1 }}>
                            Backtest Machine Dashboard
                            <Typography component="span" sx={{ fontSize: '0.65em', fontWeight: 400, color: 'rgba(255,255,255,0.6)' }}>
                                v{__APP_VERSION__}{__BUILD_NUMBER__ !== 'dev' ? ` (#${__BUILD_NUMBER__})` : ' (dev)'}
                            </Typography>
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                            <Timeline sx={{ fontSize: 16, color: 'rgba(255,255,255,0.7)' }} />
                            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.85)' }}>
                                Configure strategies, run backtests & monitor live engine in one place.
                            </Typography>
                        </Box>
                    </Box>
                </Box>

                <Tooltip title={websocketConnected ? "WebSocket Connected" : "WebSocket Disconnected"} arrow>
                    <Box
                        sx={{
                            width: 12,
                            height: 12,
                            borderRadius: '50%',
                            bgcolor: websocketConnected ? '#2e7d32' : '#d32f2f',
                            boxShadow: websocketConnected ? '0 0 8px rgba(46,125,50,0.6)' : '0 0 8px rgba(211,47,47,0.5)',
                        }}
                    />
                </Tooltip>
            </Paper>

            <Paper sx={{ mb: 2 }}>
                <Tabs
                    value={tabValue}
                    onChange={handleTabChange}
                    TabIndicatorProps={{
                        sx: {
                            height: 3,
                            borderRadius: '3px 3px 0 0',
                            backgroundColor: tabValue === 'backtest' ? '#2e7d32' : '#ed6c02',
                        },
                    }}
                    sx={{
                        borderBottom: 1,
                        borderColor: 'divider',
                        '& .MuiTab-root': { textTransform: 'none', fontWeight: 600 },
                    }}
                >
                    <Tab
                        value="backtest"
                        label="Backtest"
                        icon={<PlayArrow sx={{ fontSize: 18 }} />}
                        iconPosition="start"
                        sx={{
                            color: tabValue === 'backtest' ? '#2e7d32' : 'text.secondary',
                            '&.Mui-selected': { color: '#2e7d32' },
                        }}
                    />
                    <Tab
                        value="live"
                        label="Live"
                        icon={<FlashOn sx={{ fontSize: 18 }} />}
                        iconPosition="start"
                        sx={{
                            color: tabValue === 'live' ? '#ed6c02' : 'text.secondary',
                            '&.Mui-selected': { color: '#ed6c02' },
                        }}
                    />
                </Tabs>
            </Paper>

            <Grid container spacing={{ xs: 2, sm: 3 }}>
                <Grid item xs={12}>
                    <ConfigPanel activeTab={tabValue} />
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
