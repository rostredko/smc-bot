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
  Checkbox,
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
  Chip,
  Tooltip as MuiTooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  Stack
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
import BacktestHistoryList from "./components/BacktestHistoryList";

const API_BASE = "http://localhost:8000";

const TOOLTIP_HINTS: Record<string, string> = {
  // Account
  initial_capital: "Starting account balance in USD",
  risk_per_trade: "Percentage of capital risked per single trade (e.g. 1.0 = 1%)",
  max_drawdown: "Maximum allowed decline in account equity before stopping",
  leverage: "Multiplier for position size (technical use only, risk is controlled by % per trade)",
  max_positions: "Maximum number of simultaneous open trades",

  // General
  symbol: "Trading pair to backtest (e.g. BTC/USDT)",
  start_date: "Backtest start date",
  end_date: "Backtest end date",
  timeframe_primary: "The main timeframe for analysis (e.g. 4h, 1d)",
  timeframe_secondary: "The lower timeframe for entries (e.g. 15m, 1h)",
  trailing_stop_distance: "Distance to trail the stop loss behind price (e.g. 0.02 = 2%)",
  breakeven_trigger_r: "Profit multiplier to trigger move to breakeven (e.g. 1.0 = Move stop to entry when profit hits 1R)",
  dynamic_position_sizing: "Adjust position size based on current capital/risk",

  // Strategy Specific
  primary_timeframe: "The main timeframe for candle analysis (e.g. 4h, 1h)",
  min_range_factor: "Minimum size of a candle relative to recent average",
  use_trend_filter: "Enable/Disable trading only in direction of EMA trend",
  trend_ema_period: "Period for Exponential Moving Average to determine trend direction",
  risk_reward_ratio: "Target Profit/Risk ratio for trade exits",
  sl_buffer_atr: "Buffer added to Stop Loss based on ATR (volatility)",
  use_rsi_filter: "Enable/Disable RSI checks for overbought/oversold conditions",
  rsi_period: "Lookback period for RSI indicator",
  rsi_overbought: "RSI level above which Longs are avoided (Too high)",
  rsi_oversold: "RSI level below which Shorts are avoided (Too low)",
  min_wick_to_range: "Minimum wick size relative to candle body (for Pin Bars)",
  max_body_to_range: "Maximum body size relative to total range (for Pin Bars)",
  use_adx_filter: "Enable/Disable ADX (Trend Strength) Filter",
  adx_period: "Lookback period for ADX indicator",
  adx_threshold: "Minimum ADX value required to enter a trade (Trend Strength)",
  use_rsi_momentum: "Enable/Disable RSI Momentum (Long if > 50, Short if < 50)",
  rsi_momentum_threshold: "Threshold for RSI Momentum (usually 50)",
};

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
  trailing_stop_distance: number;
  breakeven_trigger_r: number;
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

const DEFAULT_CONFIG: BacktestConfig = {
  initial_capital: 10000,
  risk_per_trade: 1.0,
  max_drawdown: 10.0,
  max_positions: 3,
  leverage: 1.0,
  symbol: "BTC/USDT",
  timeframes: ["4h"],
  start_date: "2023-01-01",
  end_date: "2023-12-31",
  strategy: "",
  strategy_config: {},
  trailing_stop_distance: 0.02,
  breakeven_trigger_r: 1.0,
  dynamic_position_sizing: true
};

// Validation helper outside component (pure function)
const validateBacktestConfig = (config: BacktestConfig): Record<string, string> => {
  const newErrors: Record<string, string> = {};
  const timeframeRegex = /^\d+[mhdwM]$/;

  // 1. Timeframe validation
  const tfPrimary = config.timeframes && config.timeframes[0] !== undefined ? config.timeframes[0].trim() : "";

  if (!tfPrimary) {
    newErrors['timeframe_primary'] = "Required";
  } else if (!timeframeRegex.test(tfPrimary)) {
    newErrors['timeframe_primary'] = "Invalid (e.g. 4h)";
  }

  // 2. Numeric validation
  if (isNaN(config.initial_capital) || config.initial_capital <= 0) newErrors['initial_capital'] = "Must be positive number";
  if (isNaN(config.risk_per_trade) || config.risk_per_trade <= 0) newErrors['risk_per_trade'] = "Must be positive number";
  if (isNaN(config.max_drawdown) || config.max_drawdown <= 0) newErrors['max_drawdown'] = "Must be positive number";
  if (isNaN(config.leverage) || config.leverage <= 0) newErrors['leverage'] = "Must be positive number";

  // 3. Date validation
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
  if (!config.start_date || !dateRegex.test(config.start_date)) {
    newErrors['start_date'] = "Invalid (YYYY-MM-DD)";
  }
  if (!config.end_date || !dateRegex.test(config.end_date)) {
    newErrors['end_date'] = "Invalid (YYYY-MM-DD)";
  }

  if (!newErrors['start_date'] && !newErrors['end_date']) {
    if (new Date(config.start_date) >= new Date(config.end_date)) {
      newErrors['start_date'] = "Must be before End Date";
      newErrors['end_date'] = "Must be after Start Date";
    }
  }

  // Symbol validation
  if (!config.symbol || !config.symbol.trim()) {
    newErrors['symbol'] = "Required";
  }

  return newErrors;
};

export default function App() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [config, setConfig] = useState<BacktestConfig>(DEFAULT_CONFIG);
  const [strategyConfig, setStrategyConfig] = useState<Record<string, any>>({});
  const [backtestStatus, setBacktestStatus] = useState<BacktestStatus | null>(null);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [consoleOutput, setConsoleOutput] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isRunning, setIsRunning] = useState(false);
  const [isConfigDisabled, setIsConfigDisabled] = useState(false);
  const [websocketConnected, setWebsocketConnected] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const websocketRef = useRef<WebSocket | null>(null);

  // Sections mapping for strategy parameters (order matters)
  const strategySections: Array<{ title: string; keys: string[] }> = [
    { title: "Core Settings", keys: ["mode", "allow_short"] },
    { title: "Timeframes", keys: ["high_timeframe", "low_timeframe"] },
    { title: "Volatility Filters", keys: ["volatility_filter_enabled", "atr_period", "atr_percentile_min", "atr_percentile_max", "sl_atr_multiplier", "min_signal_confidence"] },
    { title: "Technical Entry Filters", keys: ["use_rsi_filter", "rsi_period", "rsi_overbought", "rsi_oversold", "use_rsi_momentum", "rsi_momentum_threshold", "use_adx_filter", "adx_period", "adx_threshold", "use_trend_filter", "trend_ema_period"] },
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
      if (["rsi_momentum_threshold"].includes(key)) {
        const useMom = (strategyConfig as any)["use_rsi_momentum"];
        if (useMom === false) isDisabled = true;
      }
      if (key === "trend_ema_period") {
        const useTrend = (strategyConfig as any)["use_trend_filter"];
        if (useTrend === false) isDisabled = true;
      }
      if (["adx_period", "adx_threshold"].includes(key)) {
        const useAdx = (strategyConfig as any)["use_adx_filter"];
        if (useAdx === false) isDisabled = true;
      }
    }

    return (
      <Grid item xs={12} md={isBoolean ? 12 : 6} key={key}>
        <MuiTooltip title={TOOLTIP_HINTS[key] || "No description available"} arrow placement="top">
          <Box>
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
          </Box>
        </MuiTooltip>
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
    if (autoScroll) {
      scrollToBottom();
    }
  }, [consoleOutput, autoScroll]);

  // WebSocket buffering to prevent render flooding
  const logBuffer = useRef<string[]>([]);
  const lastFlushTime = useRef<number>(0);
  const flushTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushLogs = useCallback(() => {
    if (logBuffer.current.length === 0) return;

    setConsoleOutput(prev => {
      // Take all messages from buffer
      const newMessages = [...logBuffer.current];
      logBuffer.current = []; // Clear buffer immediately

      const newOutput = [...prev, ...newMessages];
      // Keep strictly 500 lines
      if (newOutput.length > 500) {
        return newOutput.slice(-500);
      }
      return newOutput;
    });

    lastFlushTime.current = Date.now();
    flushTimeout.current = null;
  }, []);

  const connectWebSocket = useCallback(() => {
    // Determine the base URL for the WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    // Assume backend is on port 8000 for local dev, or same port for prod
    const port = '8000';
    const wsUrl = `${protocol}//${host}:${port}/ws`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('✅ WebSocket connected');
        setWebsocketConnected(true);
      };

      ws.onmessage = (event) => {
        if (event.data && event.data.trim()) {
          // Push to buffer
          logBuffer.current.push(event.data);

          // Throttle updates: Only flush at most every 100ms
          const now = Date.now();
          if (!flushTimeout.current) {
            if (now - lastFlushTime.current >= 100) {
              // Can flush immediately
              flushLogs();
            } else {
              // Schedule flush
              flushTimeout.current = setTimeout(flushLogs, 100);
            }
          }
        }
      };

      ws.onclose = () => {
        setWebsocketConnected(false);
        // Clear any pending logs
        if (flushTimeout.current) {
          clearTimeout(flushTimeout.current);
          flushLogs(); // Flush remaining
        }
        // Simple reconnect
        setTimeout(() => connectWebSocket(), 3000);
      };

      websocketRef.current = ws;
    } catch (error) {
      console.error('❌ Failed to connect WebSocket:', error);
    }
  }, [flushLogs]);

  // Initial data load moved to after function definitions

  // WebSocket connection effect
  useEffect(() => {
    connectWebSocket();
    return () => {
      if (websocketRef.current) {
        websocketRef.current.onclose = null;
        websocketRef.current.close();
      }
      if (flushTimeout.current) {
        clearTimeout(flushTimeout.current);
      }
    };
  }, [connectWebSocket]);

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
      return data.strategies || [];
    } catch (error) {
      console.error("Failed to load strategies:", error);
      return [];
    }
  };

  const loadConfig = async (currentStrategies: Strategy[] = strategies) => {
    try {
      const response = await fetch(`${API_BASE}/config`);
      const data = await response.json();
      console.log("Loaded config:", data);

      setConfig(prev => ({ ...prev, ...data }));

      if (data.strategy) {
        setSelectedStrategy(data.strategy);

        // Find the strategy definition to get defaults
        const strategyDef = currentStrategies.find(s => s.name === data.strategy);
        if (strategyDef) {
          const defaults: Record<string, any> = {};
          Object.entries(strategyDef.config_schema || {}).forEach(([key, schema]: [string, any]) => {
            defaults[key] = schema.default;
          });

          // Merge defaults with loaded config
          setStrategyConfig({
            ...defaults,
            ...(data.strategy_config || {})
          });
        } else {
          // Fallback if strategy definition not found yet (should not happen if loaded)
          setStrategyConfig(data.strategy_config || {});
        }
      } else {
        setStrategyConfig({});
      }
    } catch (error) {
      console.error("Failed to load config:", error);
    }
  };

  // Load strategies and config on mount
  useEffect(() => {
    const loadData = async () => {
      const loadedStrategies = await loadStrategies();
      await loadConfig(loadedStrategies);
    };
    loadData();
  }, []);

  const resetDashboard = async () => {
    // 1. Reset Run State
    setIsRunning(false);
    setIsConfigDisabled(false);
    setBacktestStatus(null);
    setResults(null);
    setConsoleOutput([]);

    // 2. Reload Config from Server
    await loadConfig();
  };

  const startBacktest = async () => {
    // Run validation immediately
    const newErrors = validateBacktestConfig(config);
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    setErrors({});

    try {
      setIsRunning(true);
      setIsConfigDisabled(true);
      setConsoleOutput([]); // Clear console output
      setResults(null); // Clear old results

      const requestBody = {
        config: {
          ...config,
          timeframes: config.timeframes.filter(t => t.trim() !== ""),
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
    // Clear error for this field
    if (errors[key]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[key];
        return newErrors;
      });
    }
    // Also handle nested timeframe errors implicitly by key if needed
    if (key === 'timeframes') {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors['timeframe_primary'];
        delete newErrors['timeframe_secondary'];
        return newErrors;
      });
    }
  }, [errors]);

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

  const [selectedTrade, setSelectedTrade] = useState<any | null>(null);
  const [isTradeModalOpen, setIsTradeModalOpen] = useState(false);

  // ... [Keep existing useEffects and handlers]

  // Update tradeData to include full trade object and formatted date
  const tradeData = useMemo(() => {
    if (!results?.trades || results.trades.length === 0) {
      return [
        { trade: 1, pnl: 0, type: "NO_TRADES", date: "", fullTrade: null }
      ];
    }
    return results.trades.map((trade, index) => ({
      trade: index + 1,
      pnl: trade.pnl || 0,
      type: trade.pnl > 0 ? "WIN" : "LOSS",
      date: trade.entry_time ? new Date(trade.entry_time).toLocaleDateString() : 'N/A',
      fullTrade: trade
    }));
  }, [results]);

  const handleBarClick = (data: any) => {
    if (data && data.fullTrade) {
      setSelectedTrade(data.fullTrade);
      setIsTradeModalOpen(true);
    }
  };

  const CustomTradeTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div style={{
          backgroundColor: '#1e1e1e',
          border: '1px solid #333',
          borderRadius: '4px',
          padding: '12px',
          boxShadow: '0 4px 6px rgba(0,0,0,0.3)',
          color: '#fff'
        }}>
          <p style={{ margin: 0, fontWeight: 'bold', borderBottom: '1px solid #444', paddingBottom: '4px', marginBottom: '8px' }}>
            Trade #{label}
          </p>
          <p style={{ margin: 0, fontSize: '0.9rem' }}>
            <span style={{ color: '#aaa' }}>Date:</span> {data.date}
          </p>
          <p style={{ margin: 0, fontSize: '0.9rem', color: data.pnl >= 0 ? '#4caf50' : '#f44336' }}>
            <span style={{ color: '#aaa' }}>PnL:</span> ${data.pnl?.toFixed(2)}
          </p>
          <p style={{ margin: '8px 0 0 0', fontSize: '0.8rem', color: '#888', fontStyle: 'italic' }}>
            Click for details
          </p>
        </div>
      );
    }
    return null;
  };
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
      {/* Trade Modal */}
      <Dialog
        open={isTradeModalOpen}
        onClose={() => setIsTradeModalOpen(false)}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: { bgcolor: '#1e1e1e', color: '#fff' }
        }}
      >
        {selectedTrade && (
          <>
            <DialogTitle sx={{ borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box display="flex" alignItems="center" gap={2}>
                <Typography variant="h6">Trade #{selectedTrade.id}</Typography>
                <Chip
                  label={selectedTrade.direction?.toUpperCase()}
                  color={selectedTrade.direction === 'LONG' ? 'success' : 'error'}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={selectedTrade.pnl >= 0 ? "WIN" : "LOSS"}
                  color={selectedTrade.pnl >= 0 ? "success" : "error"}
                  size="small"
                />
              </Box>
              <Typography variant="h5" color={selectedTrade.pnl >= 0 ? "success.main" : "error.main"}>
                {selectedTrade.pnl >= 0 ? "+" : ""}${selectedTrade.pnl?.toFixed(2)} ({selectedTrade.pnl_percent?.toFixed(2)}%)
              </Typography>
            </DialogTitle>
            <DialogContent sx={{ mt: 2 }}>
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderColor: '#333' }}>
                    <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">ENTRY REASON / CONTEXT</Typography>
                    <Typography variant="body1" sx={{ fontStyle: 'italic', fontWeight: 'medium', color: '#fff' }}>
                      "{selectedTrade.reason || 'No specific reason recorded'}"
                    </Typography>

                    {selectedTrade.metadata && Object.keys(selectedTrade.metadata).length > 0 && (
                      <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                        <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">ADDITIONAL CONTEXT</Typography>
                        <Grid container spacing={1}>
                          {Object.entries(selectedTrade.metadata).map(([key, value]) => (
                            <Grid item xs={6} md={4} key={key}>
                              <Typography variant="caption" sx={{ color: '#aaa', textTransform: 'uppercase', fontSize: '0.7rem' }} display="block">
                                {key.replace(/_/g, ' ')}
                              </Typography>
                              <Typography variant="body2" sx={{ color: '#fff' }}>
                                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                              </Typography>
                            </Grid>
                          ))}
                        </Grid>
                      </Box>
                    )}
                  </Paper>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Stack spacing={2}>
                    <Box>
                      <Typography variant="subtitle2" color="gray">ENTRY TIME</Typography>
                      <Typography variant="body1">{selectedTrade.entry_time ? new Date(selectedTrade.entry_time).toLocaleString() : 'N/A'}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="subtitle2" color="gray">ENTRY PRICE</Typography>
                      <Typography variant="body1">${selectedTrade.entry_price?.toFixed(2)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="subtitle2" color="gray">SIZE</Typography>
                      <Typography variant="body1">{selectedTrade.size?.toFixed(4)}</Typography>
                    </Box>
                  </Stack>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Stack spacing={2}>
                    <Box>
                      <Typography variant="subtitle2" color="gray">EXIT TIME</Typography>
                      <Typography variant="body1">{selectedTrade.exit_time ? new Date(selectedTrade.exit_time).toLocaleString() : 'N/A'}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="subtitle2" color="gray">EXIT PRICE</Typography>
                      <Typography variant="body1">${selectedTrade.exit_price?.toFixed(2)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="subtitle2" color="gray">DURATION</Typography>
                      <Typography variant="body1">
                        {(() => {
                          if (!selectedTrade.duration) return 'N/A';
                          // Parse duration string "HH:MM:SS" or similar
                          const parts = selectedTrade.duration.split(':');
                          if (parts.length >= 2) {
                            const h = parseInt(parts[0]);
                            const m = parseInt(parts[1]);
                            return `${h}h ${m}m`;
                          }
                          return selectedTrade.duration;
                        })()}
                      </Typography>
                    </Box>
                  </Stack>
                </Grid>

                <Grid item xs={12}>
                  <Divider sx={{ borderColor: '#333', my: 1 }} />
                </Grid>

                <Grid item xs={6} md={3}>
                  <Typography variant="caption" color="gray">STOP LOSS</Typography>
                  <Typography variant="body2">${selectedTrade.stop_loss?.toFixed(2)}</Typography>
                </Grid>
                <Grid item xs={6} md={3}>
                  <Typography variant="caption" color="gray">TAKE PROFIT</Typography>
                  <Typography variant="body2">${selectedTrade.take_profit?.toFixed(2)}</Typography>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="caption" color="gray">EXIT REASON</Typography>
                  <Typography variant="body2">{selectedTrade.exit_reason}</Typography>
                </Grid>
              </Grid>
            </DialogContent>
            <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
              <Button onClick={() => setIsTradeModalOpen(false)} color="inherit">Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
      <Typography variant="h3" component="h1" gutterBottom align="center">
        Backtest Machine Dashboard
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
                      variant="outlined"
                      size="large"
                      startIcon={<PlayArrow />}
                      onClick={startBacktest}
                      disabled={!selectedStrategy || isRunning}
                      sx={{
                        borderWidth: 2,
                        borderColor: '#2e7d32',
                        color: '#2e7d32',
                        fontWeight: 'bold',
                        '&:hover': {
                          borderWidth: 2,
                          borderColor: '#1b5e20',
                          color: '#1b5e20',
                          bgcolor: 'transparent' // Explicitly avoid fill
                        }
                      }}
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
                      onClick={resetDashboard}
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
                      <MuiTooltip title={TOOLTIP_HINTS["initial_capital"]} arrow placement="top">
                        <TextField
                          label="Initial Capital"
                          required
                          type="number"
                          value={isNaN(config.initial_capital) ? "" : config.initial_capital}
                          onChange={e => handleConfigChange("initial_capital", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.initial_capital}
                          helperText={errors.initial_capital}

                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["risk_per_trade"]} arrow placement="top">
                        <TextField
                          label="Risk Per Trade (%)"
                          required
                          type="number"
                          value={isNaN(config.risk_per_trade) ? "" : config.risk_per_trade}
                          onChange={e => handleConfigChange("risk_per_trade", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.risk_per_trade}
                          helperText={errors.risk_per_trade}

                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["max_drawdown"]} arrow placement="top">
                        <TextField
                          label="Max Drawdown (%)"
                          type="number"
                          value={isNaN(config.max_drawdown) ? "" : config.max_drawdown}
                          onChange={e => handleConfigChange("max_drawdown", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.max_drawdown}
                          helperText={errors.max_drawdown}

                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["leverage"]} arrow placement="top">
                        <TextField
                          label="Leverage"
                          type="number"
                          value={isNaN(config.leverage) ? "" : config.leverage}
                          onChange={e => handleConfigChange("leverage", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.leverage}
                          helperText={errors.leverage}

                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["max_positions"]} arrow placement="top">
                        <TextField
                          label="Max Positions"
                          type="number"
                          value={isNaN(config.max_positions) ? "" : config.max_positions}
                          onChange={e => handleConfigChange("max_positions", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <MuiTooltip title={TOOLTIP_HINTS["symbol"]} arrow placement="top">
                        <TextField
                          label="Symbol"
                          required
                          value={config.symbol}
                          onChange={e => handleConfigChange("symbol", e.target.value)}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.symbol}
                          helperText={errors.symbol}

                        />
                      </MuiTooltip>
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <MuiTooltip title={TOOLTIP_HINTS["timeframe_primary"]} arrow placement="top">
                        <TextField
                          label="Timeframe"
                          required
                          value={config.timeframes && config.timeframes[0] ? config.timeframes[0] : ""}
                          onChange={e => {
                            const val = e.target.value;
                            handleConfigChange("timeframes", [val]);
                          }}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.timeframe_primary}
                          helperText={errors.timeframe_primary}

                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <MuiTooltip title={TOOLTIP_HINTS["start_date"]} arrow placement="top">
                        <TextField
                          label="Start Date"
                          required
                          type="date"
                          value={config.start_date}
                          onChange={e => handleConfigChange("start_date", e.target.value)}
                          disabled={isConfigDisabled}
                          fullWidth
                          InputLabelProps={{ shrink: true }}
                          error={!!errors.start_date}
                          helperText={errors.start_date}

                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <MuiTooltip title={TOOLTIP_HINTS["end_date"]} arrow placement="top">
                        <TextField
                          label="End Date"
                          required
                          type="date"
                          value={config.end_date}
                          onChange={e => handleConfigChange("end_date", e.target.value)}
                          disabled={isConfigDisabled}
                          fullWidth
                          InputLabelProps={{ shrink: true }}
                          error={!!errors.end_date}
                          helperText={errors.end_date}

                        />
                      </MuiTooltip>
                    </Grid>

                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["trailing_stop_distance"]} arrow placement="top">
                        <TextField
                          label="Trailing Stop Distance"
                          type="number"
                          value={isNaN(config.trailing_stop_distance) ? "" : config.trailing_stop_distance}
                          onChange={e => handleConfigChange("trailing_stop_distance", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["breakeven_trigger_r"]} arrow placement="top">
                        <TextField
                          label="Breakeven Trigger (R)"
                          type="number"
                          value={isNaN(config.breakeven_trigger_r) ? "" : config.breakeven_trigger_r}
                          onChange={e => handleConfigChange("breakeven_trigger_r", parseFloat(e.target.value))}
                          disabled={isConfigDisabled}
                          fullWidth
                        />
                      </MuiTooltip>
                    </Grid>

                    <Grid item xs={12} md={3}>
                      <MuiTooltip title={TOOLTIP_HINTS["dynamic_position_sizing"]} arrow placement="top">
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
                      </MuiTooltip>
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
                        sx={{ color: '#666', '&.Mui-checked': { color: '#00ff00' } }} // Styled to match dark theme/terminal
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
                    <BarChart
                      data={tradeData}
                      onClick={(data) => {
                        if (data && data.activePayload && data.activePayload.length > 0) {
                          handleBarClick(data.activePayload[0].payload);
                        }
                      }}
                      style={{ cursor: 'pointer' }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="trade" />
                      <YAxis />
                      <Tooltip content={<CustomTradeTooltip />} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
                      <Bar dataKey="pnl" fill="#8884d8">
                        {
                          tradeData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#4caf50' : '#f44336'} />
                          ))
                        }
                      </Bar>
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

        {/* Backtest History */}
        <Grid item xs={12}>
          <BacktestHistoryList />
        </Grid>

      </Grid>
    </Container >
  );
}