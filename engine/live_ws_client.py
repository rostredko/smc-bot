import json
import asyncio
import threading
import queue
import websockets

from engine.logger import get_logger

logger = get_logger(__name__)


class BinanceWebsocketClient(threading.Thread):
    """
    A separate background thread running an asyncio event loop.
    Connects to Binance WebSocket (Futures or Spot) and pushes closed klines to a queue.
    """

    def __init__(self, symbol: str, timeframe: str, exchange_type: str, data_queue: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True, name=f"WSClient_{symbol}_{timeframe}")
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange_type = exchange_type
        self.data_queue = data_queue
        self.stop_event = stop_event
        self.loop = None
        self._active_ws = None
        self._ws_lock = threading.Lock()

    def _get_ws_url(self) -> str:
        # Format symbol for Binance WS (e.g., BTCUSDT -> btcusdt)
        clean_symbol = self.symbol.replace("/", "").lower()
        if self.exchange_type.lower() == "future":
            base_url = "wss://fstream.binance.com/ws"
        else:
            base_url = "wss://stream.binance.com:9443/ws"
        
        # Stream name: <symbol>@kline_<interval>
        stream_name = f"{clean_symbol}@kline_{self.timeframe}"
        return f"{base_url}/{stream_name}"

    async def _sleep_with_stop(self, seconds: float, step: float = 0.25):
        """
        Sleep in small chunks so stop_event can interrupt reconnect backoff quickly.
        """
        remaining = max(0.0, float(seconds))
        while remaining > 0 and not self.stop_event.is_set():
            chunk = min(step, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk

    async def _ws_loop(self):
        ws_url = self._get_ws_url()
        logger.info(f"Connecting to Binance WS: {ws_url}")
        
        retry_delay = 5
        while not self.stop_event.is_set():
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    with self._ws_lock:
                        self._active_ws = ws
                    logger.info(f"Connected to WS stream for {self.symbol} ({self.timeframe})")
                    retry_delay = 5  # Reset on successful connect

                    try:
                        while not self.stop_event.is_set():
                            # Wait for message with a timeout to check stop_event periodically
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            except asyncio.TimeoutError:
                                continue

                            data = json.loads(msg)
                            kline = data.get("k")

                            if kline and kline.get("x"):  # "x": True means the kline is closed
                                # It's a closed candle, push it to the queue
                                # O = Open, H = High, L = Low, C = Close, V = Volume, t = start time
                                bar = {
                                    "timestamp": kline.get("t"),
                                    "open": float(kline.get("o")),
                                    "high": float(kline.get("h")),
                                    "low": float(kline.get("l")),
                                    "close": float(kline.get("c")),
                                    "volume": float(kline.get("v")),
                                }
                                logger.debug(f"Received closed candle {self.timeframe}: {bar['close']}")
                                try:
                                    self.data_queue.put_nowait(bar)
                                except queue.Full:
                                    # Keep feed responsive under transient load: drop oldest bar.
                                    try:
                                        self.data_queue.get_nowait()
                                    except queue.Empty:
                                        pass
                                    try:
                                        self.data_queue.put_nowait(bar)
                                    except queue.Full:
                                        logger.warning("Live queue overflow: dropping candle")
                    finally:
                        with self._ws_lock:
                            self._active_ws = None

            except (websockets.ConnectionClosed, websockets.InvalidURI, websockets.InvalidHandshake, ConnectionError) as e:
                logger.error(f"WebSocket Error: {e}")
                if self.stop_event.is_set():
                    break
                logger.info(f"Reconnecting WS in {retry_delay}s...")
                await self._sleep_with_stop(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
            except Exception as e:
                logger.exception(f"Unexpected WS Error: {e}")
                if self.stop_event.is_set():
                    break
                await self._sleep_with_stop(retry_delay)

    async def _close_active_ws(self):
        ws = None
        with self._ws_lock:
            ws = self._active_ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    def request_stop(self):
        """
        Request fast shutdown from another thread:
        - set stop_event
        - close active websocket from this thread's event loop
        """
        self.stop_event.set()
        loop = self.loop
        if loop and loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._close_active_ws(), loop)
                fut.result(timeout=0.5)
            except Exception:
                # Best effort only; stop_event will still terminate loop on next cycle.
                pass

    def run(self):
        """Thread entry point."""
        logger.info(f"Starting WS Thread for {self.symbol}...")
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self._ws_loop())
        finally:
            with self._ws_lock:
                self._active_ws = None
            self.loop.close()
            logger.info(f"WS Thread for {self.symbol} stopped.")
