import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Container,
  Grid,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Typography,
  LinearProgress,
  Alert,
  TextField,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip
} from "@mui/material";
import {
  PlayArrow,
  Stop,
  Refresh,
  ExpandMore,
  Check,
  Close
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell
} from "recharts";

const API_BASE = "http://localhost:8000";

// Custom tooltip components for formatting numbers
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        backgroundColor: '#fff',
        border: '1px solid #ccc',
        borderRadius: '4px',
        padding: '8px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <p style={{ margin: 0, fontWeight: 'bold' }}>{label}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} style={{ margin: 0, color: entry.color }}>
            {`${entry.dataKey}: ${entry.value?.toFixed(1)}`}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

const CustomPieTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        backgroundColor: '#fff',
        border: '1px solid #ccc',
        borderRadius: '4px',
        padding: '8px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <p style={{ margin: 0, fontWeight: 'bold' }}>{payload[0].name}</p>
        <p style={{ margin: 0, color: payload[0].color }}>
          {`Value: ${payload[0].value?.toFixed(1)}`}
        </p>
      </div>
    );
  }
  return null;
};

interface Strategy {
  name: string;
  display_name: string;
  description: string;
  config_schema: Record<string, any>;
}

interface BacktestConfig {
  initial_capital: number;
  risk_per_trade: number;
  max_drawdown: number;
  max_positions: number;
  leverage: number;
  symbol: string;
  timeframes: string[];
  start_date: string;
  end_date: string;
  strategy: string;
  strategy_config: Record<string, any>;
  min_risk_reward: number;
  trailing_stop_distance: number;
  max_total_risk_percent: number;
  dynamic_position_sizing: boolean;
}

interface BacktestStatus {
  run_id: string;
  status: string;
  progress: number;
  message: string;
  results?: any;
  error?: string;
}

interface BacktestResults {
  total_pnl: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  sharpe_ratio: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_win: number;
  avg_loss: number;
  signals_generated: number;
  initial_capital: number;
  equity_curve: Array<{ date: string, equity: number }>;
  trades: Array<any>;
}

export default function App() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [config, setConfig] = useState<BacktestConfig>({
    initial_capital: 10000,
    risk_per_trade: 2.0,
    max_drawdown: 15.0,
    max_positions: 3,
    leverage: 10.0,
    symbol: "BTC/USDT",
    timeframes: ["4h", "15m"],
    start_date: "2023-01-01",
    end_date: "2023-12-31",
    strategy: "",
    strategy_config: {},
    min_risk_reward: 2.0,
    trailing_stop_distance: 0.02,
    max_total_risk_percent: 15.0,
    dynamic_position_sizing: true
  });
  const [strategyConfig, setStrategyConfig] = useState<Record<string, any>>({});
  const [backtestStatus, setBacktestStatus] = useState<BacktestStatus | null>(null);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [consoleOutput, setConsoleOutput] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isConfigDisabled, setIsConfigDisabled] = useState(false);
  const [websocketConnected, setWebsocketConnected] = useState(false);
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const websocketRef = useRef<WebSocket | null>(null);

  // Sections mapping for strategy parameters (order matters)
  const strategySections: Array<{ title: string; keys: string[] }> = [
    { title: "Core Settings", keys: ["mode", "allow_short"] },
    { title: "Timeframes", keys: ["high_timeframe", "low_timeframe"] },
    { title: "Volatility Filters", keys: ["volatility_filter_enabled", "atr_period", "atr_percentile_min", "atr_percentile_max", "sl_atr_multiplier", "min_signal_confidence"] },
    { title: "Technical Entry Filters", keys: ["use_rsi_filter", "rsi_period", "rsi_overbought", "rsi_oversold", "use_trend_filter", "trend_ema_period"] },
    { title: "Pattern Settings", keys: ["min_range_factor", "min_wick_to_range", "max_body_to_range", "risk_reward_ratio", "sl_buffer_atr"] },
    { title: "Partial Take Profits", keys: ["use_partial_tp", "tp1_r", "tp1_pct", "tp2_r", "tp2_pct", "runner_pct"] },
    { title: "Exit Management", keys: ["trailing_stop_enabled", "trail_start", "trail_step", "breakeven_move_enabled"] },
    { title: "Market Structure", keys: ["require_structure_confirmation", "support_level_lookback_bars"] },
    { title: "Cooldown & Psychology", keys: ["cooldown_after_loss_bars", "reduce_risk_after_loss", "risk_reduction_after_loss"] },
    { title: "Exchange Settings", keys: ["min_notional", "taker_fee", "slippage_bp"] },
  ];

  // Helper to render a single strategy field by key
  const renderStrategyField = (key: string) => {
    const strategy = strategies.find(s => s.name === selectedStrategy);
    const schema = strategy?.config_schema?.[key] || {};
    const value = (strategyConfig as any)[key];
    const label = key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase());
    const isBoolean = schema?.type === "boolean" || typeof value === "boolean" || value === "true" || value === "false";

    // Dependency Logic
    let isDisabled = isConfigDisabled;
    if (!isDisabled) {
      if (["rsi_period", "rsi_overbought", "rsi_oversold"].includes(key)) {
        const useRsi = (strategyConfig as any)["use_rsi_filter"];
        // Check if explicitly false (handle undefined as true/default if needed, but safe to assume it follows config)
        if (useRsi === false) isDisabled = true;
      }
      if (key === "trend_ema_period") {
        const useTrend = (strategyConfig as any)["use_trend_filter"];
        if (useTrend === false) isDisabled = true;
      }
    }

    return (
      <Grid item xs={12} md={6} key={key}>
        {isBoolean ? (
          <FormControlLabel
            control={
              <Switch
                checked={value !== undefined ? Boolean(value === true || value === "true") : Boolean(schema?.default)}
                onChange={e => handleStrategyConfigChange(key, e.target.checked)}
                disabled={isDisabled}
              />
            }
            label={label}
          />
        ) : (
          <TextField
            label={label}
            type={schema?.type === "number" ? "number" : "text"}
            value={value !== undefined ? value : (schema?.default || "")}
            onChange={e => {
              const newValue = schema?.type === "number" ? parseFloat(e.target.value) : e.target.value;
              handleStrategyConfigChange(key, newValue);
            }}
            disabled={isDisabled}
            fullWidth
          />
        )}
      </Grid>
    );
  };

  // Auto-scroll console to bottom
  const scrollToBottom = () => {
    setTimeout(() => {
      consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 0);
  };

  useEffect(() => {
    scrollToBottom();
  }, [consoleOutput]);

  // Load strategies and config on mount
  useEffect(() => {
    const loadData = async () => {
      await loadStrategies();
      await loadConfig();
    };
    loadData();

    // Connect to WebSocket for console output
    const connectWebSocket = () => {
      try {
        const ws = new WebSocket(`ws://localhost:8000/ws`);

        ws.onopen = () => {
          console.log('✅ WebSocket connected');
          setWebsocketConnected(true);
        };

        ws.onmessage = (event) => {
          if (event.data && event.data.trim()) {
            setConsoleOutput(prev => [...prev, event.data]);
          }
        };

        ws.onerror = (error) => {
          console.error('❌ WebSocket error:', error);
          setWebsocketConnected(false);
        };

        ws.onclose = () => {
          console.log('🔄 WebSocket disconnected, reconnecting in 3s...');
          setWebsocketConnected(false);
          setTimeout(() => connectWebSocket(), 3000);
        };

        websocketRef.current = ws;
      } catch (error) {
        console.error('❌ Failed to connect WebSocket:', error);
        setWebsocketConnected(false);
      }
    };

    connectWebSocket();

    return () => {
      if (websocketRef.current) {
        websocketRef.current.close();
      }
    };
  }, []);

  // Poll for backtest status when running
  useEffect(() => {
    if (isRunning && backtestStatus?.run_id) {
      const interval = setInterval(() => {
        checkBacktestStatus(backtestStatus.run_id);
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [isRunning, backtestStatus]);

  const loadStrategies = async () => {
    try {
      const response = await fetch(`${API_BASE}/strategies`);
      const data = await response.json();
      console.log("Loaded strategies:", data.strategies);
      setStrategies(data.strategies || []);
    } catch (error) {
      console.error("Failed to load strategies:", error);
    }
  };

  const loadConfig = async () => {
    try {
      const response = await fetch(`${API_BASE}/config`);
      const data = await response.json();
      console.log("Loaded config:", data);

      setConfig(prev => ({ ...prev, ...data }));
      setSelectedStrategy("");
      setStrategyConfig({});
    } catch (error) {
      console.error("Failed to load config:", error);
    }
  };

  const startBacktest = async () => {
    try {
      setIsRunning(true);
      setIsConfigDisabled(true);
      setConsoleOutput([]); // Clear console output
      setResults(null); // Clear old results

      const requestBody = {
        config: {
          ...config,
          strategy_config: strategyConfig
        }
      };

      const response = await fetch(`${API_BASE}/backtest/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });

      if (response.ok) {
        const data = await response.json();
        setBacktestStatus({
          run_id: data.run_id,
          status: "running",
          progress: 0,
          message: "Starting backtest..."
        });
      } else {
        throw new Error("Failed to start backtest");
      }
    } catch (error) {
      console.error("Failed to start backtest:", error);
      setIsRunning(false);
      setIsConfigDisabled(false);
    }
  };

  const stopBacktest = async () => {
    try {
      if (backtestStatus?.run_id) {
        await fetch(`${API_BASE}/backtest/${backtestStatus.run_id}`, {
          method: "DELETE"
        });
        // Don't set isRunning to false immediately - let polling continue
        // until the status updates to "cancelled" or "completed"
        // This ensures results are fetched before we stop polling
      }
    } catch (error) {
      console.error("Failed to stop backtest:", error);
    }
  };

  const checkBacktestStatus = async (runId: string) => {
    try {
      const response = await fetch(`${API_BASE}/backtest/status/${runId}`);
      const status = await response.json();
      setBacktestStatus(status);

      if (status.status === "completed") {
        setIsRunning(false);
        setIsConfigDisabled(false);
        setResults(status.results);
      } else if (status.status === "cancelled") {
        setIsRunning(false);
        setIsConfigDisabled(false);
        // Show intermediate results even if cancelled
        setResults(status.results);
      } else if (status.status === "failed") {
        setIsRunning(false);
        setIsConfigDisabled(false);
      }
    } catch (error) {
      console.error("Failed to check status:", error);
    }
  };

  const handleStrategyChange = useCallback((strategyName: string) => {
    console.log("📍 [1] handleStrategyChange called with:", strategyName);
    setSelectedStrategy(strategyName);
    setConfig(prev => ({ ...prev, strategy: strategyName }));

    console.log("📍 [2] Config updated, now processing strategy config...");

    if (strategyName && strategyName.trim() !== "") {
      console.log("📍 [3] Finding strategy in list...");
      const strategy = strategies.find(s => s.name === strategyName);
      console.log("📍 [4] Strategy found:", strategy?.name);

      if (strategy) {
        console.log("📍 [5] Extracting defaults from schema...");
        const defaults: Record<string, any> = {};
        Object.entries(strategy.config_schema || {}).forEach(([key, schema]: [string, any]) => {
          defaults[key] = schema.default;
        });
        console.log("📍 [6] Defaults extracted:", defaults);
        setStrategyConfig(defaults);
        console.log("📍 [7] Strategy config updated");
      }
    } else {
      console.log("📍 [3] No strategy selected, clearing config");
      setStrategyConfig({});
    }
    console.log("📍 [8] handleStrategyChange completed");
  }, [strategies]);

  const handleConfigChange = useCallback((key: string, value: any) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleStrategyConfigChange = useCallback((key: string, value: any) => {
    setStrategyConfig(prev => ({ ...prev, [key]: value }));
  }, []);

  // Chart data processing
  const equityData = useMemo(() => {
    if (!results?.equity_curve || results.equity_curve.length === 0) {
      return [
        { date: "Start", equity: results?.initial_capital || 10000 },
        { date: "End", equity: (results?.initial_capital || 10000) + (results?.total_pnl || 0) }
      ];
    }
    return results.equity_curve.map(point => ({
      date: new Date(point.date).toLocaleDateString(),
      equity: point.equity
    }));
  }, [results]);

  const tradeData = useMemo(() => {
    if (!results?.trades || results.trades.length === 0) {
      return [
        { trade: 1, pnl: 0, type: "NO_TRADES" }
      ];
    }
    return results.trades.map((trade, index) => ({
      trade: index + 1,
      pnl: trade.pnl || 0,
      type: trade.pnl > 0 ? "WIN" : "LOSS"
    }));
  }, [results]);

  const pieData = useMemo(() => {
    if (!results) return [];
    const winning = results.winning_trades || 0;
    const losing = results.losing_trades || 0;

    if (winning === 0 && losing === 0) {
      return [
        { name: "No Trades", value: 1, color: "#9e9e9e" }
      ];
    }

    return [
      { name: "Winning Trades", value: winning, color: "#4caf50" },
      { name: "Losing Trades", value: losing, color: "#f44336" }
    ];
  }, [results]);

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom align="center">
        SMC Trading Engine Dashboard
      </Typography>

      {/* WebSocket Connection Status */}
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center' }}>
        <Chip
          icon={websocketConnected ? <Check /> : <Close />}
          label={websocketConnected ? "WebSocket Connected" : "WebSocket Disconnected"}
          color={websocketConnected ? "success" : "error"}
          variant="outlined"
        />
      </Box>

      <Grid container spacing={3}>
        {/* Control Panel */}
        <Grid item xs={12}>
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
                      variant="contained"
                      startIcon={<PlayArrow />}
                      onClick={startBacktest}
                      disabled={!selectedStrategy || isRunning}
                      color="success"
                    >
                      Start Backtest
                    </Button>
                    <Button
                      variant="contained"
                      startIcon={<Stop />}
                      onClick={stopBacktest}
                      disabled={!isRunning}
                      color="error"
                    >
                      Stop
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<Refresh />}
                      onClick={() => {
                        setIsRunning(false);
                        setIsConfigDisabled(false);
                        setBacktestStatus(null);
                        setResults(null);
                        setConsoleOutput([]);
                      }}
                      disabled={isRunning}
                    >
                      Reset
                    </Button>
                  </Box>
                </Grid>

              </Grid>

              {isRunning && backtestStatus && (
                <Box sx={{ mt: 2 }}>
                  <Alert severity="info">
                    {backtestStatus.message}
                    <LinearProgress
                      variant="determinate"
                      value={backtestStatus.progress}
                      sx={{ mt: 1 }}
                    />
                  </Alert>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Configuration */}
        <Grid item xs={12}>
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
                      <TextField
                        label="Initial Capital"
                        type="number"
                        value={config.initial_capital}
                        onChange={e => handleConfigChange("initial_capital", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Risk Per Trade (%)"
                        type="number"
                        value={config.risk_per_trade}
                        onChange={e => handleConfigChange("risk_per_trade", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Max Drawdown (%)"
                        type="number"
                        value={config.max_drawdown}
                        onChange={e => handleConfigChange("max_drawdown", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Leverage"
                        type="number"
                        value={config.leverage}
                        onChange={e => handleConfigChange("leverage", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Max Positions"
                        type="number"
                        value={config.max_positions}
                        onChange={e => handleConfigChange("max_positions", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <TextField
                        label="Symbol"
                        value={config.symbol}
                        onChange={e => handleConfigChange("symbol", e.target.value)}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <TextField
                        label="Start Date"
                        type="date"
                        value={config.start_date}
                        onChange={e => handleConfigChange("start_date", e.target.value)}
                        disabled={isConfigDisabled}
                        fullWidth
                        InputLabelProps={{ shrink: true }}
                      />
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <TextField
                        label="End Date"
                        type="date"
                        value={config.end_date}
                        onChange={e => handleConfigChange("end_date", e.target.value)}
                        disabled={isConfigDisabled}
                        fullWidth
                        InputLabelProps={{ shrink: true }}
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Min Risk/Reward"
                        type="number"
                        value={config.min_risk_reward}
                        onChange={e => handleConfigChange("min_risk_reward", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Trailing Stop Distance"
                        type="number"
                        value={config.trailing_stop_distance}
                        onChange={e => handleConfigChange("trailing_stop_distance", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField
                        label="Max Total Risk (%)"
                        type="number"
                        value={config.max_total_risk_percent}
                        onChange={e => handleConfigChange("max_total_risk_percent", parseFloat(e.target.value))}
                        disabled={isConfigDisabled}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={config.dynamic_position_sizing}
                            onChange={e => handleConfigChange("dynamic_position_sizing", e.target.checked)}
                            disabled={isConfigDisabled}
                          />
                        }
                        label="Dynamic Position Sizing"
                      />
                    </Grid>
                  </Grid>
                </AccordionDetails>
              </Accordion>

              {Object.keys(strategyConfig).length > 0 && (
                <>
                  {strategySections.map(section => {
                    const keysInSection = section.keys.filter(k => strategyConfig.hasOwnProperty(k));
                    if (keysInSection.length === 0) return null;
                    return (
                      <Accordion key={section.title}>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <Typography variant="h6">{section.title}</Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                          <Grid container spacing={2}>
                            {keysInSection.map(key => renderStrategyField(key))}
                          </Grid>
                        </AccordionDetails>
                      </Accordion>
                    );
                  })}
                </>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Live Output - moved before Results */}
        <Grid item xs={12}>
          <Card>
            <CardHeader
              title="Live Output"
              action={
                <Typography variant="body2" color={websocketConnected ? "success.main" : "error.main"}>
                  {websocketConnected ? "🟢 Live" : "🔴 Offline"}
                </Typography>
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
                  <>
                    {consoleOutput.map((line, index) => (
                      <div key={index} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {line}
                      </div>
                    ))}
                    <div ref={consoleEndRef} />
                  </>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Results Dashboard */}
        {results && (
          <>
            {/* Performance Metrics */}
            <Grid item xs={12}>
              <Card>
                <CardHeader title="Performance Metrics" />
                <CardContent>
                  <Grid container spacing={2}>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color={results.total_pnl >= 0 ? "success.main" : "error.main"}>
                          ${results.total_pnl?.toFixed(1)}
                        </Typography>
                        <Typography variant="body2">Total PnL</Typography>
                      </Paper>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color="primary.main">
                          {(results.win_rate * 100)?.toFixed(1)}%
                        </Typography>
                        <Typography variant="body2">Win Rate</Typography>
                      </Paper>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color="warning.main">
                          {results.profit_factor?.toFixed(1)}
                        </Typography>
                        <Typography variant="body2">Profit Factor</Typography>
                      </Paper>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color="error.main">
                          {results.max_drawdown?.toFixed(1)}%
                        </Typography>
                        <Typography variant="body2">Max Drawdown</Typography>
                      </Paper>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color="info.main">
                          {results.sharpe_ratio?.toFixed(1)}
                        </Typography>
                        <Typography variant="body2">Sharpe Ratio</Typography>
                      </Paper>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color="primary.main">
                          {results.total_trades}
                        </Typography>
                        <Typography variant="body2">Total Trades</Typography>
                      </Paper>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <Paper sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="h6" color="secondary.main">
                          {results.signals_generated || 0}
                        </Typography>
                        <Typography variant="body2">Signals Generated</Typography>
                      </Paper>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {/* Charts */}
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Equity Curve" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={equityData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend />
                      <Line type="monotone" dataKey="equity" stroke="#8884d8" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Trade Distribution" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        outerRadius={80}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomPieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>

            {/* Trade Analysis */}
            <Grid item xs={12}>
              <Card>
                <CardHeader title="Trade Analysis" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={tradeData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="trade" />
                      <YAxis />
                      <Tooltip content={<CustomTooltip />} />
                      <Bar dataKey="pnl" fill="#8884d8" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>

            {/* Detailed Results Table */}
            <Grid item xs={12}>
              <Card>
                <CardHeader title="Detailed Results" />
                <CardContent>
                  <TableContainer>
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>Metric</TableCell>
                          <TableCell>Value</TableCell>
                          <TableCell>Description</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        <TableRow>
                          <TableCell>Total PnL</TableCell>
                          <TableCell>${results.total_pnl?.toFixed(1)}</TableCell>
                          <TableCell>Overall profit/loss</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Win Rate</TableCell>
                          <TableCell>{(results.win_rate * 100)?.toFixed(1)}%</TableCell>
                          <TableCell>Percentage of winning trades</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Profit Factor</TableCell>
                          <TableCell>{results.profit_factor?.toFixed(1)}</TableCell>
                          <TableCell>Gross profit / Gross loss</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Max Drawdown</TableCell>
                          <TableCell>{results.max_drawdown?.toFixed(1)}%</TableCell>
                          <TableCell>Maximum peak-to-trough decline</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Sharpe Ratio</TableCell>
                          <TableCell>{results.sharpe_ratio?.toFixed(1)}</TableCell>
                          <TableCell>Risk-adjusted return</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Total Trades</TableCell>
                          <TableCell>{results.total_trades}</TableCell>
                          <TableCell>Number of executed trades</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Winning Trades</TableCell>
                          <TableCell>{results.winning_trades || 0}</TableCell>
                          <TableCell>Number of profitable trades</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Losing Trades</TableCell>
                          <TableCell>{results.losing_trades || 0}</TableCell>
                          <TableCell>Number of losing trades</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Average Win</TableCell>
                          <TableCell>{results.avg_win?.toFixed(1)}</TableCell>
                          <TableCell>Average profit per winning trade</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Average Loss</TableCell>
                          <TableCell>{results.avg_loss?.toFixed(1)}</TableCell>
                          <TableCell>Average loss per losing trade</TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>
          </>
        )}
      </Grid>
    </Container>
  );
}