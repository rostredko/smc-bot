import React, { useMemo } from 'react';
import {
    DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
    Card, CardHeader, CardContent, Grid, FormControl, InputLabel, Select, MenuItem,
    Box, Button, LinearProgress, Accordion, AccordionSummary, Typography, Chip,
    AccordionDetails, TextField, Tooltip as MuiTooltip, Autocomplete, FormControlLabel, Switch, Dialog, DialogTitle, DialogContent, DialogActions, TableContainer, Table, TableBody, TableRow, TableCell, IconButton
} from '@mui/material';
import {
    PlayArrow,
    Stop,
    Refresh,
    FileDownloadOutlined,
    ExpandMore,
    DeleteOutline,
    Tune,
    Settings,
    PlayCircleOutline,
    FlashOn,
    DragIndicator,
} from '@mui/icons-material';
import { useConfigContext } from '../../../app/providers/config/ConfigProvider';
import { useResultsContext } from '../../../app/providers/results/ResultsProvider';
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';
import { TOOLTIP_HINTS } from '../../../shared/const/tooltips';
import StrategyField from '../../../shared/ui/StrategyField/StrategyField';

interface SortableTemplateRowProps {
    name: string;
    onLoad: (name: string) => void;
    onDelete: (name: string) => void;
}

const SortableTemplateRow: React.FC<SortableTemplateRowProps> = ({ name, onLoad, onDelete }) => {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: name });
    const style = {
        transform: transform ? CSS.Transform.toString({ ...transform, x: 0 }) : undefined,
        transition,
        opacity: isDragging ? 0.5 : 1,
    };
    return (
        <TableRow
            ref={setNodeRef}
            style={style}
            hover
            sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' } }}
            onClick={() => onLoad(name)}
        >
            <TableCell sx={{ color: '#fff', borderBottom: '1px solid #333', py: 0.5 }}>
                <Box component="span" {...attributes} {...listeners} sx={{ cursor: 'grab', display: 'inline-flex', mr: 1, touchAction: 'none' }} onClick={(e) => e.stopPropagation()}>
                    <DragIndicator fontSize="small" sx={{ color: '#666' }} />
                </Box>
                {name}
            </TableCell>
            <TableCell align="right" sx={{ borderBottom: '1px solid #333', py: 0.5 }}>
                <Button size="small" variant="text" color="primary" onClick={(e) => { e.stopPropagation(); onLoad(name); }}>Load</Button>
                <IconButton size="small" color="error" title={`Delete ${name}`} onClick={(e: React.MouseEvent) => { e.stopPropagation(); onDelete(name); }}>
                    <DeleteOutline fontSize="small" />
                </IconButton>
            </TableCell>
        </TableRow>
    );
};

const ConfigPanel: React.FC = () => {
    const {
        strategies, selectedStrategy, config, strategyConfig,
        errors, isRunning, isLiveRunning, isLiveStopping, isConfigDisabled, loadDialogOpen, savedConfigs,
        topSymbols, loadedTemplateName, handleStrategyChange, handleConfigChange, handleStrategyConfigChange,
        startBacktest, stopBacktest, startLiveTrading, stopLiveTrading, resetDashboard, handleOpenLoadDialog, setLoadDialogOpen,
        handleLoadConfig, handleDeleteConfig, handleReorderConfigs
    } = useConfigContext();

    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
    );

    const handleDragEnd = (event: { active: { id: unknown }; over: { id: unknown } | null }) => {
        const { active, over } = event;
        if (over && active.id !== over.id) {
            const oldIndex = savedConfigs.indexOf(String(active.id));
            const newIndex = savedConfigs.indexOf(String(over.id));
            if (oldIndex !== -1 && newIndex !== -1) {
                handleReorderConfigs(arrayMove([...savedConfigs], oldIndex, newIndex));
            }
        }
    };

    const { backtestStatus, setBacktestStatus, setResults } = useResultsContext();
    const { setConsoleOutput } = useConsoleContext();

    const configDisabled = isConfigDisabled || isRunning || isLiveRunning;

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

    const selectedStrategyDef = useMemo(
        () => strategies.find(s => s.name === selectedStrategy),
        [strategies, selectedStrategy]
    );

    const renderedSchemaKeys = (() => {
        const keys = new Set<string>(generalStrategyKeys);
        strategySections.forEach(section => section.keys.forEach(k => keys.add(k)));
        return keys;
    })();

    const extraStrategyKeys = (() => {
        const schema = selectedStrategyDef?.config_schema ?? {};
        return Object.keys(schema).filter((k) => !renderedSchemaKeys.has(k));
    })();

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
                        <TableContainer sx={{ overflowX: 'hidden' }}>
                            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                                <Table size="small">
                                    <TableBody>
                                        <SortableContext items={savedConfigs} strategy={verticalListSortingStrategy}>
                                            {savedConfigs.map((name) => (
                                                <SortableTemplateRow
                                                    key={name}
                                                    name={name}
                                                    onLoad={handleLoadConfig}
                                                    onDelete={handleDeleteConfig}
                                                />
                                            ))}
                                        </SortableContext>
                                    </TableBody>
                                </Table>
                            </DndContext>
                        </TableContainer>
                    )}
                </DialogContent>
                <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                    <Button onClick={() => setLoadDialogOpen(false)} color="inherit">Close</Button>
                </DialogActions>
            </Dialog>

            <Card>
                <CardHeader
                    title={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Tune sx={{ fontSize: 22, color: 'primary.main' }} />
                            <Typography variant="h6">Control Panel</Typography>
                        </Box>
                    }
                    subheader={
                        <Typography variant="body2" color="text.secondary">
                            Select a strategy, tune risk and launch backtests or live runs.
                        </Typography>
                    }
                />
                <CardContent>
                    <Grid container spacing={3}>
                        {/* Strategy Selection & Utilities */}
                        <Grid item xs={12} md={4}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                                <Settings sx={{ fontSize: 18, color: 'text.secondary' }} />
                                <Typography variant="subtitle2" color="textSecondary">
                                    Strategy Setup
                                </Typography>
                            </Box>
                            <FormControl fullWidth disabled={configDisabled} size="small">
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

                            <Box mt={2} display="flex" flexDirection="column" gap={1}>
                                <Box display="flex" gap={1}>
                                    <Button variant="text" size="small" startIcon={<FileDownloadOutlined />} onClick={handleOpenLoadDialog} disabled={isRunning || isLiveRunning}>
                                        Load Template
                                    </Button>
                                    <Button variant="text" size="small" startIcon={<Refresh />} onClick={resetDashboard} disabled={isRunning || isLiveRunning}>
                                        Reset Settings
                                    </Button>
                                </Box>
                                {loadedTemplateName && (
                                    <Chip
                                        label={`📋 ${loadedTemplateName}`}
                                        size="small"
                                        color="primary"
                                        variant="outlined"
                                        sx={{ alignSelf: 'flex-start', fontSize: '0.72rem', maxWidth: 220, fontWeight: 600 }}
                                    />
                                )}
                            </Box>
                        </Grid>

                        {/* Backtest Controls */}
                        <Grid item xs={12} md={4}>
                            <Card variant="outlined" sx={{ bgcolor: 'rgba(46, 125, 50, 0.03)', borderColor: 'rgba(46, 125, 50, 0.2)', height: '100%' }}>
                                <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                        <PlayCircleOutline sx={{ fontSize: 20, color: 'success.main' }} />
                                        <Typography variant="subtitle2" color="primary">
                                            Backtesting Engine
                                        </Typography>
                                    </Box>
                                    <Box display="flex" gap={1} mt={1}>
                                        <Button
                                            fullWidth
                                            variant="contained"
                                            disableElevation
                                            startIcon={<PlayArrow />}
                                            onClick={() => {
                                                setResults(null);
                                                startBacktest(
                                                    setConsoleOutput,
                                                    setResults,
                                                    setBacktestStatus
                                                );
                                            }}
                                            disabled={!selectedStrategy || isRunning || isLiveRunning}
                                            color="success"
                                            sx={{ whiteSpace: 'nowrap' }}
                                        >
                                            Start Backtest
                                        </Button>
                                        <Button
                                            variant="contained"
                                            disableElevation
                                            color="error"
                                            startIcon={<Stop />}
                                            onClick={() => stopBacktest(backtestStatus?.run_id)}
                                            disabled={!isRunning}
                                            sx={{ minWidth: 'auto', px: 2 }}
                                        >
                                            Stop
                                        </Button>
                                    </Box>
                                    {isRunning && backtestStatus && (
                                        <Box sx={{ mt: 2 }}>
                                            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 0.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                {backtestStatus.message}
                                            </Typography>
                                            <LinearProgress color="success" variant="determinate" value={backtestStatus.progress} sx={{ height: 6, borderRadius: 3 }} />
                                        </Box>
                                    )}
                                </CardContent>
                            </Card>
                        </Grid>

                        {/* Live Trading Controls */}
                        <Grid item xs={12} md={4}>
                            <Card variant="outlined" sx={{ bgcolor: 'rgba(237, 108, 2, 0.03)', borderColor: 'rgba(237, 108, 2, 0.2)', height: '100%' }}>
                                <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                        <FlashOn sx={{ fontSize: 20, color: 'warning.main' }} />
                                        <Typography variant="subtitle2" color="warning.main">
                                            Live Data Feed (Paper Trading)
                                        </Typography>
                                    </Box>
                                    <Box display="flex" gap={1} mt={1}>
                                        <Button
                                            fullWidth
                                            variant="contained"
                                            disableElevation
                                            color="warning"
                                            startIcon={<PlayArrow />}
                                            onClick={() => {
                                                setResults(null);
                                                startLiveTrading();
                                            }}
                                            disabled={isRunning || isLiveRunning || !selectedStrategy}
                                            sx={{ whiteSpace: 'nowrap' }}
                                        >
                                            Start Live Run
                                        </Button>
                                        <Button
                                            variant="contained"
                                            disableElevation
                                            color="error"
                                            startIcon={<Stop />}
                                            onClick={stopLiveTrading}
                                            disabled={!isLiveRunning || isLiveStopping}
                                            sx={{ minWidth: 'auto', px: 2 }}
                                        >
                                            Stop
                                        </Button>
                                    </Box>
                                    {(isLiveRunning || isLiveStopping) && (
                                        <Box sx={{ mt: 2 }}>
                                            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 0.5 }}>
                                                {isLiveStopping ? "Stopping Engine..." : "Engine is running via WebSocket."}
                                            </Typography>
                                            <LinearProgress color={isLiveStopping ? "error" : "warning"} sx={{ height: 6, borderRadius: 3 }} />
                                        </Box>
                                    )}
                                </CardContent>
                            </Card>
                        </Grid>

                    </Grid>
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
                                        <TextField label="Initial Capital" required type="number" value={isNaN(config.initial_capital) ? "" : config.initial_capital} onChange={e => handleConfigChange("initial_capital", parseFloat(e.target.value))} disabled={configDisabled} fullWidth error={!!errors.initial_capital} helperText={errors.initial_capital} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["risk_per_trade"]} arrow placement="top">
                                        <TextField label="Risk Per Trade (%)" required type="number" value={isNaN(config.risk_per_trade) ? "" : config.risk_per_trade} onChange={e => handleConfigChange("risk_per_trade", parseFloat(e.target.value))} disabled={configDisabled} fullWidth error={!!errors.risk_per_trade} helperText={errors.risk_per_trade} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["max_drawdown"]} arrow placement="top">
                                        <TextField label="Max Drawdown (%)" type="number" value={isNaN(config.max_drawdown) ? "" : config.max_drawdown} onChange={e => handleConfigChange("max_drawdown", parseFloat(e.target.value))} disabled={configDisabled} fullWidth error={!!errors.max_drawdown} helperText={errors.max_drawdown} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["leverage"]} arrow placement="top">
                                        <TextField label="Leverage" type="number" value={isNaN(config.leverage) ? "" : config.leverage} onChange={e => handleConfigChange("leverage", parseFloat(e.target.value))} disabled={configDisabled} fullWidth error={!!errors.leverage} helperText={errors.leverage} />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={4}>
                                    <MuiTooltip title={TOOLTIP_HINTS["symbol"]} arrow placement="top">
                                        <Autocomplete
                                            freeSolo options={topSymbols} value={config.symbol}
                                            onChange={(_, newValue) => { if (newValue) handleConfigChange("symbol", newValue); }}
                                            onInputChange={(_, newInputValue) => { handleConfigChange("symbol", newInputValue); }}
                                            disabled={configDisabled}
                                            renderInput={(params) => (
                                                <TextField {...params} label="Symbol" required fullWidth error={!!errors.symbol} helperText={errors.symbol} />
                                            )}
                                        />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={2}>
                                    <MuiTooltip title={TOOLTIP_HINTS["timeframe_primary"]} arrow placement="top">
                                        <TextField
                                            select
                                            label="Trend TF" required value={config.timeframes?.[0] || ""}
                                            onChange={e => { const val = e.target.value; const secondary = config.timeframes?.[1] || "15m"; handleConfigChange("timeframes", [val, secondary]); }}
                                            disabled={configDisabled} fullWidth error={!!errors.timeframe_primary} helperText={errors.timeframe_primary}
                                        >
                                            {["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"].map((tf) => (
                                                <MenuItem key={tf} value={tf}>{tf}</MenuItem>
                                            ))}
                                        </TextField>
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={2}>
                                    <MuiTooltip title={TOOLTIP_HINTS["timeframe_secondary"]} arrow placement="top">
                                        <TextField
                                            select
                                            label="Entry TF" required value={config.timeframes?.[1] || ""}
                                            onChange={e => { const val = e.target.value; const primary = config.timeframes?.[0] || "4h"; handleConfigChange("timeframes", [primary, val]); }}
                                            disabled={configDisabled} fullWidth error={!!errors.timeframe_secondary} helperText={errors.timeframe_secondary}
                                        >
                                            {["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"].map((tf) => (
                                                <MenuItem key={tf} value={tf}>{tf}</MenuItem>
                                            ))}
                                        </TextField>
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={4}>
                                    <MuiTooltip title={TOOLTIP_HINTS["start_date"]} arrow placement="top">
                                        <TextField label="Start Date" required type="date" value={config.start_date} onChange={e => handleConfigChange("start_date", e.target.value)} disabled={configDisabled} fullWidth InputLabelProps={{ shrink: true }} error={!!errors.start_date} helperText={errors.start_date} />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={4}>
                                    <MuiTooltip title={TOOLTIP_HINTS["end_date"]} arrow placement="top">
                                        <TextField label="End Date" required type="date" value={config.end_date} onChange={e => handleConfigChange("end_date", e.target.value)} disabled={configDisabled} fullWidth InputLabelProps={{ shrink: true }} error={!!errors.end_date} helperText={errors.end_date} />
                                    </MuiTooltip>
                                </Grid>

                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["trailing_stop_distance"]} arrow placement="top">
                                        <TextField label="Trailing Stop Distance" type="number" value={isNaN(config.trailing_stop_distance) ? "" : config.trailing_stop_distance} onChange={e => handleConfigChange("trailing_stop_distance", parseFloat(e.target.value))} disabled={configDisabled} fullWidth />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["breakeven_trigger_r"]} arrow placement="top">
                                        <TextField label="Breakeven Trigger (R)" type="number" value={isNaN(config.breakeven_trigger_r) ? "" : config.breakeven_trigger_r} onChange={e => handleConfigChange("breakeven_trigger_r", parseFloat(e.target.value))} disabled={configDisabled} fullWidth />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["dynamic_position_sizing"]} arrow placement="top">
                                        <FormControlLabel control={<Switch checked={config.dynamic_position_sizing} onChange={e => handleConfigChange("dynamic_position_sizing", e.target.checked)} disabled={configDisabled} />} label="Dynamic Position Sizing" />
                                    </MuiTooltip>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <MuiTooltip title={TOOLTIP_HINTS["position_cap_adverse"]} arrow placement="top">
                                        <TextField label="Position Cap Adverse" type="number" value={isNaN(config.position_cap_adverse ?? 0.5) ? "" : (config.position_cap_adverse ?? 0.5)} onChange={e => handleConfigChange("position_cap_adverse", parseFloat(e.target.value))} disabled={configDisabled} fullWidth inputProps={{ min: 0.5, max: 1, step: 0.05 }} />
                                    </MuiTooltip>
                                </Grid>

                                {generalStrategyKeys.map((key) => {
                                    const schema = selectedStrategyDef?.config_schema?.[key];
                                    if (!schema) return null;

                                    return (
                                        <StrategyField
                                            key={key} fieldKey={key} schema={schema} value={strategyConfig[key]}
                                            label={key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase())}
                                            tooltip={TOOLTIP_HINTS[key] || "No description available"}
                                            isDisabled={configDisabled} onChange={handleStrategyConfigChange}
                                        />
                                    );
                                })}
                            </Grid>
                        </AccordionDetails>
                    </Accordion>

                    {strategySections.map((section) => {
                        if (!selectedStrategyDef) return null;

                        const hasKeys = section.keys.some(k => selectedStrategyDef.config_schema && k in selectedStrategyDef.config_schema);
                        if (!hasKeys) return null;

                        return (
                            <Accordion key={section.title}>
                                <AccordionSummary expandIcon={<ExpandMore />}>
                                    <Typography variant="h6">{section.title}</Typography>
                                </AccordionSummary>
                                <AccordionDetails>
                                    <Grid container spacing={2}>
                                        {section.keys.map((key) => {
                                            const schema = selectedStrategyDef.config_schema?.[key];
                                            if (!schema) return null;

                                            let isDisabled = configDisabled;
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

                    {extraStrategyKeys.length > 0 && (
                        <Accordion>
                            <AccordionSummary expandIcon={<ExpandMore />}>
                                <Typography variant="h6">Strategy Parameters</Typography>
                            </AccordionSummary>
                            <AccordionDetails>
                                <Grid container spacing={2}>
                                    {extraStrategyKeys.map((key) => {
                                        const schema = selectedStrategyDef?.config_schema?.[key];
                                        if (!schema) return null;
                                        return (
                                            <StrategyField
                                                key={key}
                                                fieldKey={key}
                                                schema={schema}
                                                value={strategyConfig[key]}
                                                label={key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase())}
                                                tooltip={TOOLTIP_HINTS[key] || "No description available"}
                                                isDisabled={configDisabled}
                                                onChange={handleStrategyConfigChange}
                                            />
                                        );
                                    })}
                                </Grid>
                            </AccordionDetails>
                        </Accordion>
                    )}
                </CardContent>
            </Card>
        </>
    );
};

export default ConfigPanel;
