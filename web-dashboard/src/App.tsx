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
  Autocomplete,
  IconButton
} from "@mui/material";
import {
  PlayArrow,
  Stop,
  Refresh,
  ExpandMore,
  Check,
  Close,
  FileDownloadOutlined,
  DeleteOutline
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
  PieChart,
  Pie,
  Cell
} from "recharts";
import BacktestHistoryList from "./components/BacktestHistoryList";
import StrategyField from "./components/StrategyField";
import TradeAnalysisChart from "./components/TradeAnalysisChart";
import TradeDetailsModal from "./components/TradeDetailsModal";

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
  timeframe_primary: "Higher timeframe for trend direction / EMA filter (e.g. 4h, 1d)",
  timeframe_secondary: "Lower timeframe for pattern detection and trade entries (e.g. 15m, 1h)",
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
  risk_per_trade: 1.5,
  max_drawdown: 30.0,
  max_positions: 1,
  leverage: 10.0,
  symbol: "BTC/USDT",
  timeframes: ["4h", "1h"],
  start_date: "2025-01-01",
  end_date: "2025-12-31",
  strategy: "",
  strategy_config: {},
  trailing_stop_distance: 0.04,
  breakeven_trigger_r: 1.5,
  dynamic_position_sizing: true
};

// Validation helper outside component (pure function)
const validateBacktestConfig = (config: BacktestConfig, availableSymbols: string[] = []): Record<string, string> => {
  const newErrors: Record<string, string> = {};
  const timeframeRegex = /^\d+[mhdwM]$/;

  // 1. Timeframe validation
  const tfPrimary = config.timeframes && config.timeframes[0] !== undefined ? config.timeframes[0].trim() : "";

  if (!tfPrimary) {
    newErrors['timeframe_primary'] = "Required";
  } else if (!timeframeRegex.test(tfPrimary)) {
    newErrors['timeframe_primary'] = "Invalid (e.g. 4h)";
  }

  const tfSecondary = config.timeframes && config.timeframes[1] !== undefined ? config.timeframes[1].trim() : "";

  if (!tfSecondary) {
    newErrors['timeframe_secondary'] = "Required";
  } else if (!timeframeRegex.test(tfSecondary)) {
    newErrors['timeframe_secondary'] = "Invalid (e.g. 15m)";
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
  } else if (availableSymbols.length > 0 && !availableSymbols.includes(config.symbol)) {
    newErrors['symbol'] = "Invalid symbol. Select from dropdown.";
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

  const [loadDialogOpen, setLoadDialogOpen] = useState(false);
  const [savedConfigs, setSavedConfigs] = useState<string[]>([]);

  // Sections mapping for strategy parameters (order matters)
  // Sections mapping for strategy parameters (order matters)
  // Sections mapping for strategy parameters (order matters)
  const strategySections: Array<{ title: string; keys: string[] }> = [
    {
      title: "Filters",
      keys: [
        "volatility_filter_enabled", "atr_period", "atr_percentile_min", "atr_percentile_max", "sl_atr_multiplier", "min_signal_confidence",
        "use_rsi_filter", "rsi_period", "rsi_overbought", "rsi_oversold", "use_rsi_momentum", "rsi_momentum_threshold",
        "use_adx_filter", "adx_period", "adx_threshold",
        "use_trend_filter", "trend_ema_period",
        "require_structure_confirmation", "support_level_lookback_bars"
      ]
    },
    {
      title: "Pattern Settings",
      keys: ["min_range_factor", "min_wick_to_range", "max_body_to_range"]
    },
  ];

  // Keys extracted from "Strategy Settings" to be merged into "General Settings"
  const generalStrategyKeys = [
    "mode", "allow_short",
    "risk_reward_ratio", "sl_buffer_atr",
    "use_partial_tp", "tp1_r", "tp1_pct", "tp2_r", "tp2_pct", "runner_pct",
    "cooldown_after_loss_bars", "reduce_risk_after_loss", "risk_reduction_after_loss",
    "min_notional", "taker_fee", "slippage_bp"
  ];



  // Auto-scroll console to bottom
  const scrollToBottom = () => {
    setTimeout(() => {
      consoleEndRef.current?.scrollIntoView({ behavior: "auto" }); // Changed smooth to auto for performance
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
    const messagesToFlush = [...logBuffer.current];
    if (messagesToFlush.length === 0) return;

    logBuffer.current = []; // Clear immediately to avoid race conditions

    setConsoleOutput(prev => {
      // Limit log history to last 5000 lines to capture full backtest reports
      const combined = [...prev, ...messagesToFlush];
      return combined.slice(-5000);
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

  // Top Symbols Fetch
  const [topSymbols, setTopSymbols] = useState<string[]>([]);
  useEffect(() => {
    const fetchTopSymbols = async () => {
      try {
        // Use API_BASE constant
        const response = await fetch(`${API_BASE}/api/symbols/top`);
        if (response.ok) {
          const data = await response.json();
          if (data.symbols) {
            setTopSymbols(data.symbols);
          }
        }
      } catch (error) {
        console.error("Error fetching top symbols:", error);
      }
    };
    fetchTopSymbols();
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

  const loadUserConfigs = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/user-configs`);
      if (response.ok) {
        const data = await response.json();
        setSavedConfigs(data.configs || []);
      }
    } catch (error) {
      console.error("Failed to load user configs:", error);
    }
  };

  const handleOpenLoadDialog = () => {
    loadUserConfigs();
    setLoadDialogOpen(true);
  };

  const handleLoadConfig = async (configName: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/user-configs/${configName}`);
      if (response.ok) {
        const data = await response.json();

        // Apply config
        setConfig(prev => ({ ...prev, ...data }));

        if (data.strategy) {
          setSelectedStrategy(data.strategy);

          // Get strategy defaults
          const strategyDef = strategies.find(s => s.name === data.strategy);
          if (strategyDef) {
            const defaults: Record<string, any> = {};
            Object.entries(strategyDef.config_schema || {}).forEach(([key, schema]: [string, any]) => {
              defaults[key] = schema.default;
            });
            setStrategyConfig({
              ...defaults,
              ...(data.strategy_config || {})
            });
          } else {
            setStrategyConfig(data.strategy_config || {});
          }
        } else {
          setStrategyConfig({});
        }

        setLoadDialogOpen(false);
      }
    } catch (error) {
      console.error("Failed to load specific config:", error);
    }
  };

  const handleDeleteConfig = async (configName: string) => {
    if (!window.confirm(`Are you sure you want to delete the configuration "${configName}"?`)) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/user-configs/${configName}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        loadUserConfigs(); // Refresh list after deletion
      } else {
        console.error("Failed to delete config:", response.status);
      }
    } catch (error) {
      console.error("Error deleting config:", error);
    }
  };

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
    const newErrors = validateBacktestConfig(config, topSymbols);
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
    setSelectedStrategy(strategyName);
    setConfig(prev => ({ ...prev, strategy: strategyName }));

    if (strategyName && strategyName.trim() !== "") {
      const strategy = strategies.find(s => s.name === strategyName);

      if (strategy) {
        const defaults: Record<string, any> = {};
        Object.entries(strategy.config_schema || {}).forEach(([key, schema]: [string, any]) => {
          defaults[key] = schema.default;
        });
        setStrategyConfig(defaults);
        setIsConfigDisabled(false);
      } else {
        // Fallback if strategy definition not found yet (should not happen if loaded)
        setStrategyConfig({});
        setIsConfigDisabled(false);
      }
    } else {
      setStrategyConfig({});
      setIsConfigDisabled(false);
    }
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
  const handleBarClick = (trade: any) => {
    if (trade) {
      setSelectedTrade(trade);
      setIsTradeModalOpen(true);
    }
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
      <TradeDetailsModal
        open={isTradeModalOpen}
        onClose={() => setIsTradeModalOpen(false)}
        selectedTrade={selectedTrade}
      />

      {/* Load Configuration Dialog */}
      <Dialog
        open={loadDialogOpen}
        onClose={() => setLoadDialogOpen(false)}
        aria-labelledby="load-dialog-title"
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: { bgcolor: '#1e1e1e', color: '#fff' }
        }}
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
                    <Button
                      variant="outlined"
                      startIcon={<FileDownloadOutlined />}
                      onClick={handleOpenLoadDialog}
                      disabled={isRunning}
                      color="secondary"
                    >
                      Load Config
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

                    <Grid item xs={12} md={4}>
                      <MuiTooltip title={TOOLTIP_HINTS["symbol"]} arrow placement="top">
                        <Autocomplete
                          freeSolo
                          options={topSymbols}
                          value={config.symbol}
                          onChange={(_, newValue) => {
                            if (newValue) handleConfigChange("symbol", newValue);
                          }}
                          onInputChange={(_, newInputValue) => {
                            handleConfigChange("symbol", newInputValue);
                          }}
                          disabled={isConfigDisabled}
                          renderInput={(params) => (
                            <TextField
                              {...params}
                              label="Symbol"
                              required
                              fullWidth
                              error={!!errors.symbol}
                              helperText={errors.symbol}
                            />
                          )}
                        />
                      </MuiTooltip>
                    </Grid>

                    <Grid item xs={12} md={2}>
                      <MuiTooltip title={TOOLTIP_HINTS["timeframe_primary"]} arrow placement="top">
                        <TextField
                          label="Trend TF"
                          required
                          value={config.timeframes && config.timeframes[0] ? config.timeframes[0] : ""}
                          onChange={e => {
                            const val = e.target.value;
                            const secondary = config.timeframes && config.timeframes[1] ? config.timeframes[1] : "15m";
                            handleConfigChange("timeframes", [val, secondary]);
                          }}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.timeframe_primary}
                          helperText={errors.timeframe_primary}
                        />
                      </MuiTooltip>
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <MuiTooltip title={TOOLTIP_HINTS["timeframe_secondary"]} arrow placement="top">
                        <TextField
                          label="Entry TF"
                          required
                          value={config.timeframes && config.timeframes[1] ? config.timeframes[1] : ""}
                          onChange={e => {
                            const val = e.target.value;
                            const primary = config.timeframes && config.timeframes[0] ? config.timeframes[0] : "4h";
                            handleConfigChange("timeframes", [primary, val]);
                          }}
                          disabled={isConfigDisabled}
                          fullWidth
                          error={!!errors.timeframe_secondary}
                          helperText={errors.timeframe_secondary}
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

                    {/* Render Strategy Specific General Settings (Merged) */}
                    {generalStrategyKeys.map((key) => {
                      const strategy = strategies.find(s => s.name === selectedStrategy);
                      const schema = strategy?.config_schema?.[key];
                      if (!schema) return null; // Or logic to show even if not in schema? Ideally schema drives it.

                      // Keep isDisabled logic duplicated for now or simplify.
                      // Most of these keys don't have complex dependencies in the current logic block 
                      // (dependencies were mostly for Filters which are in dynamic sections).
                      return (
                        <StrategyField
                          key={key}
                          fieldKey={key}
                          schema={schema}
                          value={(strategyConfig as any)[key]}
                          label={key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase())}
                          tooltip={TOOLTIP_HINTS[key] || "No description available"}
                          isDisabled={isConfigDisabled}
                          onChange={handleStrategyConfigChange}
                        />
                      );
                    })}

                  </Grid>
                </AccordionDetails>
              </Accordion>

              {/* Dynamic Strategy Config */}
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
                              const useRsi = (strategyConfig as any)["use_rsi_filter"];
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
                            <StrategyField
                              key={key}
                              fieldKey={key}
                              schema={schema}
                              value={(strategyConfig as any)[key]}
                              label={key.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase())}
                              tooltip={TOOLTIP_HINTS[key] || "No description available"}
                              isDisabled={isDisabled}
                              onChange={handleStrategyConfigChange}
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
                  <TradeAnalysisChart trades={results?.trades || []} onTradeClick={handleBarClick} />
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