import React, { useMemo, useEffect } from 'react';
import {
    DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
    Card, CardHeader, CardContent, Grid, FormControl, InputLabel, Select, MenuItem,
    Box, Button, LinearProgress, Accordion, AccordionSummary, Typography, Chip,
    AccordionDetails, TextField, Tooltip as MuiTooltip, Autocomplete, FormControlLabel, Switch, Dialog, DialogTitle, DialogContent, DialogActions, TableContainer, Table, TableBody, TableRow, TableCell, IconButton, ToggleButtonGroup, ToggleButton
} from '@mui/material';
import {
    PlayArrow,
    Stop,
    Refresh,
    FileDownloadOutlined,
    ExpandMore,
    DeleteOutline,
    Tune,
    PlayCircleOutline,
    FlashOn,
    DragIndicator,
} from '@mui/icons-material';
import { useConfigContext } from '../../../app/providers/config/ConfigProvider';
import { useResultsContext } from '../../../app/providers/results/ResultsProvider';
import { useConsoleContext } from '../../../app/providers/console/ConsoleProvider';
import { TOOLTIP_HINTS } from '../../../shared/const/tooltips';
import StrategyField from '../../../shared/ui/StrategyField/StrategyField';

/** 3 numeric params for Optimize mode. */
const OPTIMIZE_PRESETS: Array<{ key: string; label: string; default: number }> = [
    { key: 'risk_reward_ratio', label: 'Risk:Reward', default: 2.0 },
    { key: 'sl_buffer_atr', label: 'SL Buffer (ATR)', default: 1.5 },
    { key: 'trailing_stop_distance', label: 'Trailing Stop Distance', default: 0.04 },
];
/** Keys that are controlled by Optimize section — disable in General Settings when run_mode is optimize. */
const OPTIMIZE_PARAM_KEYS = new Set(OPTIMIZE_PRESETS.map((p) => p.key));

function getOptValues(config: Record<string, any>, strategyConfig: Record<string, any>, key: string, preset: typeof OPTIMIZE_PRESETS[0]): [number, number, number] {
    const arr = config.opt_params?.[key];
    if (Array.isArray(arr) && arr.length === 3) {
        const a = arr.map((v: any) => parseFloat(String(v)));
        const valid = a.filter((n: number) => !isNaN(n) && Number.isFinite(n));
        if (valid.length === 3) return valid as [number, number, number];
    }
    const val = key === 'trailing_stop_distance' ? config.trailing_stop_distance : strategyConfig[key];
    const base = typeof val === 'number' && !isNaN(val) && Number.isFinite(val) ? val : preset.default;
    return [base, base, base];
}

function validateOptValue(key: string, val: number): string | null {
    if (isNaN(val) || !Number.isFinite(val)) return "Invalid number";
    if (key === 'risk_reward_ratio' && val < 0) return "Must be ≥ 0";
    if (key === 'sl_buffer_atr' && val <= 0) return "Must be > 0";
    if (key === 'trailing_stop_distance' && val < 0) return "Must be ≥ 0";
    return null;
}

function buildOptParamsFromValues(config: Record<string, any>, strategyConfig: Record<string, any>): Record<string, number[]> {
    const out: Record<string, number[]> = {};
    for (const p of OPTIMIZE_PRESETS) {
        out[p.key] = getOptValues(config, strategyConfig, p.key, p);
    }
    return out;
}

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

interface ConfigPanelProps {
    activeTab?: 'backtest' | 'live';
}

const ConfigPanel: React.FC<ConfigPanelProps> = ({ activeTab = 'backtest' }) => {
    const {
        strategies, selectedStrategy, config, strategyConfig,
        errors, isRunning, isLiveRunning, isLiveStopping, isConfigDisabled, loadDialogOpen, savedConfigs,
        topSymbols, loadedTemplateName, handleStrategyChange, handleConfigChange, handleStrategyConfigChange,
        startBacktest, stopBacktest, startLiveTrading, stopLiveTrading, resetDashboard, resetStrategySettings, handleOpenLoadDialog, setLoadDialogOpen,
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
    const liveExchangeValue = config.exchange || "binance";

    // When switching to Optimize, init opt_params if empty; clear opt_timeframes (use General Settings)
    useEffect(() => {
        if (config.run_mode === 'optimize') {
            if (!config.opt_params || Object.keys(config.opt_params).length === 0) {
                handleConfigChange('opt_params', buildOptParamsFromValues(config, strategyConfig));
            }
            if (config.opt_timeframes) {
                handleConfigChange('opt_timeframes', undefined);
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- only run when mode switches to optimize
    }, [config.run_mode]);

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

    const structurePoiKeys = [
        "poi_zone_upper_atr_mult",
        "poi_zone_lower_atr_mult",
        "use_premium_discount_filter",
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
    ];

    const formatStrategyLabel = (key: string) => {
        if (key === "poi_zone_upper_atr_mult") return "POI Upper ATR Multiplier";
        if (key === "poi_zone_lower_atr_mult") return "POI Lower ATR Multiplier";
        return key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase());
    };

    const selectedStrategyDef = useMemo(
        () => strategies.find(s => s.name === selectedStrategy),
        [strategies, selectedStrategy]
    );

    const renderedSchemaKeys = (() => {
        const keys = new Set<string>(generalStrategyKeys);
        structurePoiKeys.forEach((key) => keys.add(key));
        strategySections.forEach(section => section.keys.forEach(k => keys.add(k)));
        return keys;
    })();

    const advancedStrategyKeys = (() => {
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
                            <Tune sx={{ fontSize: 20, color: 'primary.main' }} />
                            <Typography variant="h6">Control Panel</Typography>
                        </Box>
                    }
                    subheader="Strategy, run mode & launch"
                    sx={{ py: 1.5, '& .MuiCardHeader-subheader': { mt: 0.25 } }}
                />
                <CardContent sx={{ pt: 0, pb: 2, px: { xs: 1.5, sm: 3 } }}>
                    <Grid container spacing={{ xs: 1.5, sm: 2 }} alignItems="flex-start">
                        <Grid item xs={12}>
                            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                                {/* Strategy + Load/Reset row */}
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                    <FormControl disabled={configDisabled} size="small" sx={{ minWidth: 160, flex: '1 1 auto', maxWidth: { sm: 320 } }}>
                                        <InputLabel>Strategy</InputLabel>
                                        <Select
                                            value={selectedStrategy}
                                            onChange={e => handleStrategyChange(e.target.value)}
                                            label="Strategy"
                                        >
                                            <MenuItem value=""><em>Select...</em></MenuItem>
                                            {strategies.map(s => (
                                                <MenuItem key={s.name} value={s.name}>{s.display_name}</MenuItem>
                                            ))}
                                        </Select>
                                    </FormControl>
                                    <Button variant="text" size="small" startIcon={<FileDownloadOutlined sx={{ fontSize: 16 }} />} onClick={handleOpenLoadDialog} disabled={isRunning || isLiveRunning} sx={{ minWidth: 0, px: 1 }}>
                                        Load
                                    </Button>
                                    <Button variant="text" size="small" startIcon={<Refresh sx={{ fontSize: 16 }} />} onClick={resetDashboard} disabled={isRunning || isLiveRunning} sx={{ minWidth: 0, px: 1 }}>
                                        Reset
                                    </Button>
                                    {loadedTemplateName && (
                                        <Chip label={loadedTemplateName} size="small" variant="outlined" onDelete={isRunning || isLiveRunning ? undefined : resetStrategySettings} sx={{ fontSize: '0.7rem' }} />
                                    )}
                                </Box>

                                {/* Backtest Controls */}
                                {activeTab === 'backtest' && (
                            <Card variant="outlined" sx={{ bgcolor: 'rgba(46, 125, 50, 0.04)', borderColor: 'rgba(46, 125, 50, 0.25)' }}>
                                <CardContent sx={{ p: { xs: 1.5, sm: 2 }, '&:last-child': { pb: { xs: 1.5, sm: 2 } } }}>
                                    <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, flexWrap: 'wrap', alignItems: { sm: 'center' }, gap: 1.5 }}>
                                        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, flex: { xs: 'none', sm: 1 }, minWidth: 0 }}>
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <PlayCircleOutline sx={{ fontSize: 18, color: 'success.main' }} />
                                                <Typography variant="subtitle2" color="primary">Run Mode</Typography>
                                            </Box>
                                            <ToggleButtonGroup value={config.run_mode || 'single'} exclusive onChange={(_, v) => v && handleConfigChange('run_mode', v)} size="small" sx={{ flexWrap: 'wrap' }}>
                                                <MuiTooltip title={TOOLTIP_HINTS.run_mode_single} arrow placement="top">
                                                    <ToggleButton value="single">Single</ToggleButton>
                                                </MuiTooltip>
                                                <MuiTooltip title={TOOLTIP_HINTS.run_mode_optimize} arrow placement="top">
                                                    <ToggleButton value="optimize">Optimize</ToggleButton>
                                                </MuiTooltip>
                                                <MuiTooltip title={TOOLTIP_HINTS.run_mode_walk_forward} arrow placement="top">
                                                    <ToggleButton value="walk_forward">Walk-Forward</ToggleButton>
                                                </MuiTooltip>
                                            </ToggleButtonGroup>
                                        </Box>
                                        <Box sx={{ display: 'flex', gap: 1, width: { xs: '100%', sm: 'auto' }, justifyContent: { xs: 'stretch', sm: 'flex-end' } }}>
                                            <Button variant="contained" disableElevation startIcon={<PlayArrow />} onClick={() => { setResults(null); startBacktest(setConsoleOutput, setResults, setBacktestStatus); }} disabled={!selectedStrategy || isRunning || isLiveRunning} color="success" sx={{ py: 1.25, px: 2, fontSize: '0.95rem', minHeight: 44, flex: { xs: 1, sm: 'none' } }}>
                                                Start Backtest
                                            </Button>
                                            <Button variant="contained" disableElevation color="error" startIcon={<Stop />} onClick={() => stopBacktest(backtestStatus?.run_id)} disabled={!isRunning} sx={{ py: 1.25, px: 2, minHeight: 44 }}>
                                                Stop
                                            </Button>
                                        </Box>
                                    </Box>
                                    {(config.run_mode === 'optimize') && (
                                        <Box sx={{ mt: 1.5 }}>
                                            <Typography variant="caption" component="div" sx={{ mb: 1.5, color: 'text.secondary', lineHeight: 1.6 }}>
                                                {TOOLTIP_HINTS.run_mode_optimize}
                                            </Typography>
                                            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                                                Params: enter 3 values to test (grid search).
                                            </Typography>
                                            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 1.5, sm: 2 }, alignItems: 'flex-start' }}>
                                                    {OPTIMIZE_PRESETS.map((p) => {
                                                        const [v1, v2, v3] = getOptValues(config, strategyConfig, p.key, p);
                                                        const updateVal = (idx: 0 | 1 | 2, raw: string) => {
                                                            const n = parseFloat(raw);
                                                            const vals = [v1, v2, v3];
                                                            vals[idx] = isNaN(n) ? vals[idx] : n;
                                                            handleConfigChange('opt_params', { ...config.opt_params, [p.key]: vals });
                                                        };
                                                        const err1 = validateOptValue(p.key, v1);
                                                        const err2 = validateOptValue(p.key, v2);
                                                        const err3 = validateOptValue(p.key, v3);
                                                        const rowError = err1 || err2 || err3 || errors[`opt_${p.key}`] || null;
                                                        return (
                                                            <Box key={p.key} sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, alignItems: { xs: 'flex-start', sm: 'center' }, gap: 0.5 }}>
                                                                <MuiTooltip title={TOOLTIP_HINTS[p.key] || p.label} arrow placement="top">
                                                                    <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', alignSelf: 'center' }}>{p.label}:</Typography>
                                                                </MuiTooltip>
                                                                <TextField
                                                                    size="small"
                                                                    type="number"
                                                                    value={v1}
                                                                    onChange={(e) => updateVal(0, e.target.value)}
                                                                    error={!!rowError}
                                                                    helperText={rowError}
                                                                    inputProps={{ step: p.key === 'trailing_stop_distance' ? 0.01 : 0.1 }}
                                                                    InputLabelProps={{ shrink: true }}
                                                                    sx={{ width: p.key === 'trailing_stop_distance' ? 100 : 72 }}
                                                                />
                                                                <TextField
                                                                    size="small"
                                                                    type="number"
                                                                    value={v2}
                                                                    onChange={(e) => updateVal(1, e.target.value)}
                                                                    error={!!rowError}
                                                                    inputProps={{ step: p.key === 'trailing_stop_distance' ? 0.01 : 0.1 }}
                                                                    InputLabelProps={{ shrink: true }}
                                                                    sx={{ width: p.key === 'trailing_stop_distance' ? 100 : 72 }}
                                                                />
                                                                <TextField
                                                                    size="small"
                                                                    type="number"
                                                                    value={v3}
                                                                    onChange={(e) => updateVal(2, e.target.value)}
                                                                    error={!!rowError}
                                                                    inputProps={{ step: p.key === 'trailing_stop_distance' ? 0.01 : 0.1 }}
                                                                    InputLabelProps={{ shrink: true }}
                                                                    sx={{ width: p.key === 'trailing_stop_distance' ? 100 : 72 }}
                                                                />
                                                            </Box>
                                                        );
                                                    })}
                                                </Box>
                                            </Box>
                                        </Box>
                                    )}
                                    {(config.run_mode === 'walk_forward') && (
                                        <Box sx={{ mt: 1.5 }}>
                                            <Typography variant="caption" component="div" sx={{ mb: 1.5, color: 'text.secondary', lineHeight: 1.6 }}>
                                                {TOOLTIP_HINTS.run_mode_walk_forward}
                                            </Typography>
                                            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                                <MuiTooltip title={TOOLTIP_HINTS.wf_train_months} arrow placement="top">
                                                    <span><TextField size="small" label="Train" type="number" value={config.wf_train_months ?? 6} onChange={e => handleConfigChange('wf_train_months', parseInt(e.target.value, 10) || 6)} sx={{ width: 70 }} inputProps={{ min: 1, max: 24 }} /></span>
                                                </MuiTooltip>
                                                <MuiTooltip title={TOOLTIP_HINTS.wf_test_months} arrow placement="top">
                                                    <span><TextField size="small" label="Test" type="number" value={config.wf_test_months ?? 1} onChange={e => handleConfigChange('wf_test_months', parseInt(e.target.value, 10) || 1)} sx={{ width: 70 }} inputProps={{ min: 1, max: 12 }} /></span>
                                                </MuiTooltip>
                                                <MuiTooltip title={TOOLTIP_HINTS.wf_step_months} arrow placement="top">
                                                    <span><TextField size="small" label="Step" type="number" value={config.wf_step_months ?? 1} onChange={e => handleConfigChange('wf_step_months', parseInt(e.target.value, 10) || 1)} sx={{ width: 70 }} inputProps={{ min: 1, max: 12 }} /></span>
                                                </MuiTooltip>
                                            </Box>
                                        </Box>
                                    )}
                                    {isRunning && backtestStatus && (
                                        <Box sx={{ mt: 2 }}>
                                            <LinearProgress color="success" variant="determinate" value={backtestStatus.progress} sx={{ height: 4, borderRadius: 2 }} />
                                            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.25 }}>{backtestStatus.message}</Typography>
                                        </Box>
                                    )}
                                </CardContent>
                            </Card>
                                )}

                                {/* Live Trading Controls */}
                                {activeTab === 'live' && (
                            <Card variant="outlined" sx={{ bgcolor: 'rgba(237, 108, 2, 0.04)', borderColor: 'rgba(237, 108, 2, 0.25)' }}>
                                <CardContent sx={{ p: { xs: 1.5, sm: 2 }, '&:last-child': { pb: { xs: 1.5, sm: 2 } } }}>
                                    <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, flexWrap: 'wrap', alignItems: { sm: 'center' }, gap: 1.5 }}>
                                        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, flex: { xs: 'none', sm: 1 }, minWidth: 0 }}>
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <FlashOn sx={{ fontSize: 18, color: 'warning.main' }} />
                                                <Typography variant="subtitle2" color="warning.main">Live (Paper)</Typography>
                                            </Box>
                                            <FormControl size="small" error={!!errors.exchange} disabled={configDisabled} sx={{ minWidth: { xs: 120, sm: 140 } }}>
                                                <InputLabel id="live-exchange-label">Exchange</InputLabel>
                                                <Select labelId="live-exchange-label" value={liveExchangeValue} label="Exchange" onChange={e => handleConfigChange("exchange", e.target.value)}>
                                                    <MenuItem value="binance">Binance</MenuItem>
                                                </Select>
                                            </FormControl>
                                            {errors.exchange && <Typography variant="caption" color="error">{errors.exchange}</Typography>}
                                        </Box>
                                        <Box sx={{ display: 'flex', gap: 1, width: { xs: '100%', sm: 'auto' }, justifyContent: { xs: 'stretch', sm: 'flex-end' } }}>
                                            <Button variant="contained" disableElevation color="warning" startIcon={<PlayArrow />} onClick={() => { setResults(null); setConsoleOutput([]); startLiveTrading(); }} disabled={isRunning || isLiveRunning || !selectedStrategy} sx={{ py: 1.25, px: 2, fontSize: '0.95rem', minHeight: 44, flex: { xs: 1, sm: 'none' } }}>
                                                Start Live Run
                                            </Button>
                                            <Button variant="contained" disableElevation color="error" startIcon={<Stop />} onClick={stopLiveTrading} disabled={!isLiveRunning || isLiveStopping} sx={{ py: 1.25, px: 2, minHeight: 44 }}>
                                                Stop
                                            </Button>
                                        </Box>
                                    </Box>
                                    {(isLiveRunning || isLiveStopping) && (
                                        <Box sx={{ mt: 1 }}>
                                            <LinearProgress color={isLiveStopping ? "error" : "warning"} sx={{ height: 4, borderRadius: 2 }} />
                                            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.25 }}>{isLiveStopping ? "Stopping..." : "Running via WebSocket"}</Typography>
                                        </Box>
                                    )}
                                </CardContent>
                            </Card>
                                )}
                            </Box>
                        </Grid>
                    </Grid>
                </CardContent>
            </Card>

            <Box mt={2} />

            <Card>
                <CardHeader title="Configuration" sx={{ py: 1.5 }} />
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
                                        <TextField label="Trailing Stop Distance" type="number" value={isNaN(config.trailing_stop_distance) ? "" : config.trailing_stop_distance} onChange={e => handleConfigChange("trailing_stop_distance", parseFloat(e.target.value))} disabled={configDisabled || config.run_mode === 'optimize'} error={!!errors.trailing_stop_distance} helperText={errors.trailing_stop_distance} fullWidth />
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
                                    const disabledByOptimize = config.run_mode === 'optimize' && OPTIMIZE_PARAM_KEYS.has(key);
                                    return (
                                        <StrategyField
                                            key={key} fieldKey={key} schema={schema} value={strategyConfig[key]}
                                            label={formatStrategyLabel(key)}
                                            tooltip={TOOLTIP_HINTS[key] || "No description available"}
                                            isDisabled={configDisabled || disabledByOptimize} onChange={handleStrategyConfigChange}
                                            error={errors[key]}
                                        />
                                    );
                                })}
                            </Grid>
                        </AccordionDetails>
                    </Accordion>

                    {structurePoiKeys.some((key) => selectedStrategyDef?.config_schema?.[key]) && (
                        <Accordion>
                            <AccordionSummary expandIcon={<ExpandMore />}>
                                <Typography variant="h6">Structure & POI</Typography>
                            </AccordionSummary>
                            <AccordionDetails>
                                <Grid container spacing={2}>
                                    {structurePoiKeys.map((key) => {
                                        const schema = selectedStrategyDef?.config_schema?.[key];
                                        if (!schema) return null;
                                        return (
                                            <StrategyField
                                                key={key}
                                                fieldKey={key}
                                                schema={schema}
                                                value={strategyConfig[key]}
                                                label={formatStrategyLabel(key)}
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

                                            let isDisabled = configDisabled || (config.run_mode === 'optimize' && OPTIMIZE_PARAM_KEYS.has(key));
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

                    {advancedStrategyKeys.length > 0 && (
                        <Accordion>
                            <AccordionSummary expandIcon={<ExpandMore />}>
                                <Typography variant="h6">Advanced Strategy Parameters</Typography>
                            </AccordionSummary>
                            <AccordionDetails>
                                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                    Optional confirmation and candle-quality controls. Leave these at defaults unless you are intentionally tuning advanced behavior.
                                </Typography>
                                <Grid container spacing={2}>
                                    {advancedStrategyKeys.map((key) => {
                                        const schema = selectedStrategyDef?.config_schema?.[key];
                                        if (!schema) return null;
                                        return (
                                            <StrategyField
                                                key={key}
                                                fieldKey={key}
                                                schema={schema}
                                                value={strategyConfig[key]}
                                                label={formatStrategyLabel(key)}
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
