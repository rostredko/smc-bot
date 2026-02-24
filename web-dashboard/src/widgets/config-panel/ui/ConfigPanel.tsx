import React from 'react';
import {
    Card, CardHeader, CardContent, Grid, FormControl, InputLabel, Select, MenuItem,
    Box, Button, Alert, LinearProgress, Accordion, AccordionSummary, Typography,
    AccordionDetails, TextField, Tooltip as MuiTooltip, Autocomplete, FormControlLabel, Switch, Dialog, DialogTitle, DialogContent, DialogActions, TableContainer, Table, TableBody, TableRow, TableCell, IconButton
} from '@mui/material';
import { PlayArrow, Stop, Refresh, FileDownloadOutlined, ExpandMore, DeleteOutline } from '@mui/icons-material';
import { useConfigContext } from '../../../app/providers/config/ConfigProvider';
import { useResultsContext } from '../../../app/providers/results/ResultsProvider';
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';
import { TOOLTIP_HINTS } from '../../../shared/const/tooltips';
import StrategyField from '../../../shared/ui/StrategyField/StrategyField';

const ConfigPanel: React.FC = () => {
    const {
        strategies, selectedStrategy, config, strategyConfig,
        errors, isRunning, isConfigDisabled, loadDialogOpen, savedConfigs,
        topSymbols, handleStrategyChange, handleConfigChange, handleStrategyConfigChange,
        startBacktest, stopBacktest, resetDashboard, handleOpenLoadDialog, setLoadDialogOpen,
        handleLoadConfig, handleDeleteConfig
    } = useConfigContext();

    const { backtestStatus, setBacktestStatus, setResults } = useResultsContext();
    const { setConsoleOutput } = useConsoleContext();

    const strategySections: Array<{ title: string; keys: string[] }> = [
        {
            title: "Filters",
            keys: [
                "use_rsi_filter", "rsi_period", "rsi_overbought", "rsi_oversold",
                "use_rsi_momentum", "rsi_momentum_threshold",
                "use_adx_filter", "adx_period", "adx_threshold",
                "use_trend_filter", "trend_ema_period",
            ]
        },
        {
            title: "Patterns",
            keys: [
                "pattern_hammer", "pattern_inverted_hammer",
                "pattern_shooting_star", "pattern_hanging_man",
                "pattern_bullish_engulfing", "pattern_bearish_engulfing"
            ]
        },
    ];

    const PATTERN_LABELS: Record<string, string> = {
        pattern_hammer: "Hammer (Bullish Pinbar)",
        pattern_inverted_hammer: "Inverted Hammer (Bullish Pinbar)",
        pattern_shooting_star: "Shooting Star (Bearish Pinbar)",
        pattern_hanging_man: "Hanging Man (Bearish Pinbar)",
        pattern_bullish_engulfing: "Bullish Engulfing",
        pattern_bearish_engulfing: "Bearish Engulfing",
    };

    const PATTERN_DESCRIPTIONS: Record<string, string> = {
        pattern_hammer: "Small body with long lower wick at bottom of downtrend; bullish reversal.",
        pattern_inverted_hammer: "Small body with long upper wick at bottom of downtrend; bullish reversal.",
        pattern_shooting_star: "Small body with long upper wick at top of uptrend; bearish reversal.",
        pattern_hanging_man: "Small body with long lower wick at top of uptrend; bearish reversal.",
        pattern_bullish_engulfing: "Second candle fully engulfs the first; bullish reversal.",
        pattern_bearish_engulfing: "Second candle fully engulfs the first; bearish reversal.",
    };

    const generalStrategyKeys = [
        "risk_reward_ratio", "sl_buffer_atr", "atr_period",
        "min_range_factor", "min_wick_to_range", "max_body_to_range",
        "trailing_stop_distance", "breakeven_trigger_r",
    ];

    return (
        <>
            <Dialog
                open={loadDialogOpen}
                onClose={() => setLoadDialogOpen(false)}
                aria-labelledby="load-dialog-title"
                maxWidth="sm"
                fullWidth
                PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#fff' } }}
            >
                <DialogTitle id="load-dialog-title" sx={{ borderBottom: '1px solid #333' }}>
                    Load Configuration Template
                </DialogTitle>
                <DialogContent sx={{ p: 0 }}>
                    {savedConfigs.length === 0 ? (
                        <Typography sx={{ color: '#aaa', p: 3, textAlign: 'center' }}>
                            No saved configurations found. Save a configuration from Recent Backtests first.
                        </Typography>
                    ) : (
                        <TableContainer>
                            <Table size="small">
                                <TableBody>
                                    {savedConfigs.map((name) => (
                                        <TableRow key={name} hover sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' } }} onClick={() => handleLoadConfig(name)}>
                                            <TableCell sx={{ color: '#fff', borderBottom: '1px solid #333' }}>{name}</TableCell>
                                            <TableCell align="right" sx={{ borderBottom: '1px solid #333' }}>
                                                <Button size="small" variant="text" color="primary" onClick={(e) => { e.stopPropagation(); handleLoadConfig(name); }}>Load</Button>
                                                <IconButton size="small" color="error" title={`Delete ${name}`} onClick={(e: React.MouseEvent) => { e.stopPropagation(); handleDeleteConfig(name); }}>
                                                    <DeleteOutline fontSize="small" />
                                                </IconButton>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    )}
                </DialogContent>
                <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                    <Button onClick={() => setLoadDialogOpen(false)} color="inherit">Close</Button>
                </DialogActions>
            </Dialog>

            <Card>
                <CardHeader title="Backtest Control" />
                <CardContent>
                    <Grid container spacing={2} alignItems="center">
                        <Grid item xs={12} md={3}>
                            <FormControl fullWidth disabled={isConfigDisabled}>
                                <InputLabel>Strategy</InputLabel>
                                <Select
                                    value={selectedStrategy}
                                    onChange={e => handleStrategyChange(e.target.value)}
                                    label="Strategy"
                                >
                                    <MenuItem value="">
                                        <em>Select a strategy...</em>
                                    </MenuItem>
                                    {strategies.map(s => (
                                        <MenuItem key={s.name} value={s.name}>
                                            {s.display_name}
                                        </MenuItem>
                                    ))}
                                </Select>
                            </FormControl>
                        </Grid>
                        <Grid item xs={12} md={6}>
                            <Box sx={{ display: 'flex', gap: 1 }}>
                                <Button
                                    variant="outlined"
                                    size="large"
                                    startIcon={<PlayArrow />}
                                    onClick={() => startBacktest(
                                        setConsoleOutput,
                                        setResults,
                                        setBacktestStatus
                                    )}
                                    disabled={!selectedStrategy || isRunning}
                                    sx={{
                                        borderWidth: 2, borderColor: '#2e7d32', color: '#2e7d32', fontWeight: 'bold',
                                        '&:hover': { borderWidth: 2, borderColor: '#1b5e20', color: '#1b5e20', bgcolor: 'transparent' }
                                    }}
                                >
                                    Start Backtest
                                </Button>
                                <Button variant="contained" startIcon={<Stop />} onClick={() => stopBacktest(backtestStatus?.run_id)} disabled={!isRunning} color="error">
                                    Stop
                                </Button>
                                <Button variant="outlined" startIcon={<Refresh />} onClick={resetDashboard} disabled={isRunning}>
                                    Reset
                                </Button>
                                <Button variant="outlined" startIcon={<FileDownloadOutlined />} onClick={handleOpenLoadDialog} disabled={isRunning} color="secondary">
                                    Load Config
                                </Button>
                            </Box>
                        </Grid>
                    </Grid>
                    {isRunning && backtestStatus && (
                        <Box sx={{ mt: 2 }}>
                            <Alert severity="info">
                                {backtestStatus.message}
                                <LinearProgress variant="determinate" value={backtestStatus.progress} sx={{ mt: 1 }} />
                            </Alert>
                        </Box>
                    )}
                </CardContent>
            </Card >

            <Box mt={3} />

            <Card>
                <CardHeader title="Configuration" />
                <CardContent>
                    <Accordion>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="h6">General Settings</Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                            <Grid container spacing={2}>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["initial_capital"]} arrow placement="top">
                                        <TextField label="Initial Capital" required type="number" value={isNaN(config.initial_capital) ? "" : config.initial_capital} onChange={e => handleConfigChange("initial_capital", parseFloat(e.target.value))} disabled={isConfigDisabled} fullWidth error={!!errors.initial_capital} helperText={errors.initial_capital} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["risk_per_trade"]} arrow placement="top">
                                        <TextField label="Risk Per Trade (%)" required type="number" value={isNaN(config.risk_per_trade) ? "" : config.risk_per_trade} onChange={e => handleConfigChange("risk_per_trade", parseFloat(e.target.value))} disabled={isConfigDisabled} fullWidth error={!!errors.risk_per_trade} helperText={errors.risk_per_trade} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["max_drawdown"]} arrow placement="top">
                                        <TextField label="Max Drawdown (%)" type="number" value={isNaN(config.max_drawdown) ? "" : config.max_drawdown} onChange={e => handleConfigChange("max_drawdown", parseFloat(e.target.value))} disabled={isConfigDisabled} fullWidth error={!!errors.max_drawdown} helperText={errors.max_drawdown} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["leverage"]} arrow placement="top">
                                        <TextField label="Leverage" type="number" value={isNaN(config.leverage) ? "" : config.leverage} onChange={e => handleConfigChange("leverage", parseFloat(e.target.value))} disabled={isConfigDisabled} fullWidth error={!!errors.leverage} helperText={errors.leverage} />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={4}>
                                    <MuiTooltip title={TOOLTIP_HINTS["symbol"]} arrow placement="top">
                                        <Autocomplete
                                            freeSolo options={topSymbols} value={config.symbol}
                                            onChange={(_, newValue) => { if (newValue) handleConfigChange("symbol", newValue); }}
                                            onInputChange={(_, newInputValue) => { handleConfigChange("symbol", newInputValue); }}
                                            disabled={isConfigDisabled}
                                            renderInput={(params) => (
                                                <TextField {...params} label="Symbol" required fullWidth error={!!errors.symbol} helperText={errors.symbol} />
                                            )}
                                        />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={2}>
                                    <MuiTooltip title={TOOLTIP_HINTS["timeframe_primary"]} arrow placement="top">
                                        <TextField
                                            label="Trend TF" required value={config.timeframes?.[0] || ""}
                                            onChange={e => { const val = e.target.value; const secondary = config.timeframes?.[1] || "15m"; handleConfigChange("timeframes", [val, secondary]); }}
                                            disabled={isConfigDisabled} fullWidth error={!!errors.timeframe_primary} helperText={errors.timeframe_primary}
                                        />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={2}>
                                    <MuiTooltip title={TOOLTIP_HINTS["timeframe_secondary"]} arrow placement="top">
                                        <TextField
                                            label="Entry TF" required value={config.timeframes?.[1] || ""}
                                            onChange={e => { const val = e.target.value; const primary = config.timeframes?.[0] || "4h"; handleConfigChange("timeframes", [primary, val]); }}
                                            disabled={isConfigDisabled} fullWidth error={!!errors.timeframe_secondary} helperText={errors.timeframe_secondary}
                                        />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={4}>
                                    <MuiTooltip title={TOOLTIP_HINTS["start_date"]} arrow placement="top">
                                        <TextField label="Start Date" required type="date" value={config.start_date} onChange={e => handleConfigChange("start_date", e.target.value)} disabled={isConfigDisabled} fullWidth InputLabelProps={{ shrink: true }} error={!!errors.start_date} helperText={errors.start_date} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={4}>
                                    <MuiTooltip title={TOOLTIP_HINTS["end_date"]} arrow placement="top">
                                        <TextField label="End Date" required type="date" value={config.end_date} onChange={e => handleConfigChange("end_date", e.target.value)} disabled={isConfigDisabled} fullWidth InputLabelProps={{ shrink: true }} error={!!errors.end_date} helperText={errors.end_date} />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["trailing_stop_distance"]} arrow placement="top">
                                        <TextField label="Trailing Stop Distance" type="number" value={isNaN(config.trailing_stop_distance) ? "" : config.trailing_stop_distance} onChange={e => handleConfigChange("trailing_stop_distance", parseFloat(e.target.value))} disabled={isConfigDisabled} fullWidth />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["breakeven_trigger_r"]} arrow placement="top">
                                        <TextField label="Breakeven Trigger (R)" type="number" value={isNaN(config.breakeven_trigger_r) ? "" : config.breakeven_trigger_r} onChange={e => handleConfigChange("breakeven_trigger_r", parseFloat(e.target.value))} disabled={isConfigDisabled} fullWidth />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["dynamic_position_sizing"]} arrow placement="top">
                                        <FormControlLabel control={<Switch checked={config.dynamic_position_sizing} onChange={e => handleConfigChange("dynamic_position_sizing", e.target.checked)} disabled={isConfigDisabled} />} label="Dynamic Position Sizing" />
                                    </MuiTooltip>
                                </Grid>

                                {generalStrategyKeys.map((key) => {
                                    const strategy = strategies.find(s => s.name === selectedStrategy);
                                    const schema = strategy?.config_schema?.[key];
                                    if (!schema) return null;

                                    return (
                                        <StrategyField
                                            key={key} fieldKey={key} schema={schema} value={strategyConfig[key]}
                                            label={key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase())}
                                            tooltip={TOOLTIP_HINTS[key] || "No description available"}
                                            isDisabled={isConfigDisabled} onChange={handleStrategyConfigChange}
                                        />
                                    );
                                })}
                            </Grid>
                        </AccordionDetails>
                    </Accordion>

                    {strategySections.map((section) => {
                        const strategy = strategies.find(s => s.name === selectedStrategy);
                        if (!strategy) return null;

                        const hasKeys = section.keys.some(k => strategy.config_schema && k in strategy.config_schema);
                        if (!hasKeys) return null;

                        return (
                            <Accordion key={section.title}>
                                <AccordionSummary expandIcon={<ExpandMore />}>
                                    <Typography variant="h6">{section.title}</Typography>
                                </AccordionSummary>
                                <AccordionDetails>
                                    <Grid container spacing={2}>
                                        {section.keys.map((key) => {
                                            const schema = strategy.config_schema?.[key];
                                            if (!schema) return null;

                                            let isDisabled = isConfigDisabled;
                                            if (!isDisabled) {
                                                if (["rsi_period", "rsi_overbought", "rsi_oversold"].includes(key)) {
                                                    if (strategyConfig["use_rsi_filter"] === false) isDisabled = true;
                                                }
                                                if (["rsi_momentum_threshold"].includes(key)) {
                                                    if (strategyConfig["use_rsi_momentum"] === false) isDisabled = true;
                                                }
                                                if (key === "trend_ema_period") {
                                                    if (strategyConfig["use_trend_filter"] === false) isDisabled = true;
                                                }
                                                if (["adx_period", "adx_threshold"].includes(key)) {
                                                    if (strategyConfig["use_adx_filter"] === false) isDisabled = true;
                                                }
                                            }

                                            const label = PATTERN_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase());
                                            const description = PATTERN_DESCRIPTIONS[key];
                                            const isPatternsSection = section.title === "Patterns";
                                            return (
                                                <StrategyField
                                                    key={key} fieldKey={key} schema={schema} value={strategyConfig[key]}
                                                    label={label}
                                                    description={description}
                                                    tooltip={TOOLTIP_HINTS[key] || "No description available"}
                                                    isDisabled={isDisabled} onChange={handleStrategyConfigChange}
                                                    compact={isPatternsSection}
                                                />
                                            );
                                        })}
                                    </Grid>
                                </AccordionDetails>
                            </Accordion>
                        );
                    })}
                </CardContent>
            </Card>
        </>
    );
};

export default ConfigPanel;
