import asyncio
import queue
import threading
from typing import Any, Dict, Optional

from engine.execution_settings import (
    is_futures_exchange_type,
    normalize_exchange_name,
    normalize_exchange_type,
)
from engine.logger import get_logger

try:
    from binance import AsyncClient, BinanceSocketManager
except ImportError:  # pragma: no cover - exercised by runtime env, not unit tests
    AsyncClient = None
    BinanceSocketManager = None

logger = get_logger(__name__)

SUPPORTED_LIVE_EXCHANGES = {"binance"}


def normalize_live_exchange_name(exchange_name: Optional[str], *, default: str = "binance") -> str:
    return normalize_exchange_name(exchange_name, default=default)


def normalize_live_exchange_type(exchange_type: Optional[str], *, default: str = "future") -> str:
    return normalize_exchange_type(exchange_type, default=default)


class BaseLiveStreamClient:
    """Minimal transport interface used by BTLiveEngine."""

    def start(self) -> None:
        raise NotImplementedError

    def join(self, timeout: Optional[float] = None) -> None:
        raise NotImplementedError

    def is_alive(self) -> bool:
        raise NotImplementedError

    def request_stop(self) -> None:
        raise NotImplementedError


class BinancePythonBinanceWsClient(BaseLiveStreamClient):
    """
    Wrapper over python-binance AsyncClient/BinanceSocketManager for public kline streams.
    Keeps the same queue contract used by the current Backtrader live feed.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        exchange_type: str,
        data_queue: queue.Queue,
        stop_event: threading.Event,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange_type = normalize_live_exchange_type(exchange_type)
        self.data_queue = data_queue
        self.stop_event = stop_event
        self.name = f"WSClient_{symbol}_{timeframe}"
        self._thread = None
        self._loop = None
        self._lock = threading.Lock()

    @staticmethod
    def _ensure_python_binance_available() -> None:
        if AsyncClient is None or BinanceSocketManager is None:
            raise RuntimeError(
                "python-binance is not installed. Install python-binance to use Binance live paper testing."
            )

    def _format_stream_symbol(self) -> str:
        return self.symbol.replace("/", "").upper()

    def _format_futures_stream_name(self) -> str:
        return f"{self.symbol.replace('/', '').lower()}@kline_{self.timeframe}"

    def _build_socket(self, socket_manager: "BinanceSocketManager"):
        if is_futures_exchange_type(self.exchange_type):
            return socket_manager.futures_multiplex_socket([self._format_futures_stream_name()])
        return socket_manager.kline_socket(self._format_stream_symbol(), interval=self.timeframe)

    def _emit_bar(self, bar: Dict[str, Any]) -> None:
        try:
            self.data_queue.put_nowait(bar)
            return
        except queue.Full:
            pass

        try:
            self.data_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self.data_queue.put_nowait(bar)
        except queue.Full:
            logger.warning("Live queue overflow: dropping candle")

    def _handle_socket_message(self, message: Dict[str, Any]) -> None:
        payload = message.get("data", message) if isinstance(message, dict) else {}
        if not isinstance(payload, dict):
            logger.debug("Ignoring non-dict Binance WS payload: %r", payload)
            return

        if payload.get("e") == "error":
            logger.error("Binance WS error payload: %s", payload)
            return

        kline = payload.get("k")
        if not isinstance(kline, dict) or not kline.get("x"):
            return

        try:
            bar = {
                "timestamp": int(kline["t"]),
                "open": float(kline["o"]),
                "high": float(kline["h"]),
                "low": float(kline["l"]),
                "close": float(kline["c"]),
                "volume": float(kline["v"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse Binance kline payload: %s (%s)", payload, exc)
            return

        logger.debug("Received closed candle %s %s: %s", self.symbol, self.timeframe, bar["close"])
        self._emit_bar(bar)

    async def _sleep_with_stop(self, seconds: float, step: float = 0.1) -> None:
        remaining = max(0.0, float(seconds))
        while remaining > 0 and not self.stop_event.is_set():
            chunk = min(step, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk

    async def _socket_loop(self) -> None:
        retry_delay = 1.0
        while not self.stop_event.is_set():
            client = None
            try:
                client = await AsyncClient.create()
                socket_manager = BinanceSocketManager(client)
                logger.info(
                    "Starting Binance python-binance socket for %s (%s, %s)",
                    self.symbol,
                    self.timeframe,
                    self.exchange_type,
                )
                retry_delay = 1.0
                async with self._build_socket(socket_manager) as stream:
                    while not self.stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(stream.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        self._handle_socket_message(message)
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                logger.error("Binance socket error for %s %s: %s", self.symbol, self.timeframe, exc, exc_info=True)
                await self._sleep_with_stop(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)
            finally:
                if client is not None:
                    try:
                        await client.close_connection()
                    except Exception:
                        pass

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._socket_loop())
        finally:
            self._loop.close()
            self._loop = None

    def start(self) -> None:
        self._ensure_python_binance_available()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name=self.name)
            self._thread.start()

    def request_stop(self) -> None:
        self.stop_event.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(lambda: None)
            except RuntimeError:
                pass

    def join(self, timeout: Optional[float] = None) -> None:
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())


def create_live_stream_client(exchange_name: Optional[str], **kwargs: Any) -> BaseLiveStreamClient:
    exchange = normalize_live_exchange_name(exchange_name)
    if exchange == "binance":
        return BinancePythonBinanceWsClient(**kwargs)
    raise ValueError(f"Unsupported live exchange: {exchange}")
