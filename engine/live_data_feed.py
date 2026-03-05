import datetime
import backtrader as bt
import queue
import threading

from engine.logger import get_logger

logger = get_logger(__name__)

class LiveWebSocketDataFeed(bt.feed.DataBase):
    """
    A custom Data Feed that polls a thread-safe queue populated by the WS listener.
    It yields bars to Cerebro's synchronized engine in real-time.
    """

    # We must provide these fields. Backtrader defaults to them anyway.
    lines = ('open', 'high', 'low', 'close', 'volume', 'openinterest')

    # Data feed parameters
    params = (
        ('q', None),          # The queue to read from
        ('stop_event', None), # Event to signal shutdown
        ('timeout', 0.5),     # Queue polling timeout
    )

    def start(self):
        super().start()
        logger.debug("LiveWebSocketDataFeed started.")

    def stop(self):
        super().stop()
        logger.debug("LiveWebSocketDataFeed stopped.")

    def islive(self):
        return True

    def haslivedata(self):
        """
        Tells Cerebro whether to keep expecting data from this feed.
        If we return True, Cerebro will sleep and retry _load() later instead of quitting.
        """
        if self.p.stop_event and self.p.stop_event.is_set():
            # If stopped, we only have data if the queue isn't empty yet
            return not self.p.q.empty()
        return True

    def _load(self):
        """
        Called by Cerebro to request the next bar.
        Returns True if a bar is loaded, False if the data stream is exhausted.
        We poll the queue. If empty, we block for self.p.timeout, then return None to tell Cerebro to wait.
        Wait... if _load returns False, Backtrader thinks the data is FINISHED and stops Cerebro!
        In Backtrader, live data feeds must return None if there is no new data yet.
        """
        # If shutdown was requested, stop the feed
        if self.p.stop_event and self.p.stop_event.is_set():
            return False

        try:
            bar = self.p.q.get(block=True, timeout=self.p.timeout)
            
            # Write data to the lines
            # Timestamp comes in milliseconds from Binance WS
            dt = datetime.datetime.utcfromtimestamp(bar["timestamp"] / 1000.0)
            
            # Backtrader timestamp representation is a float (matplotlib format)
            # which is what date2num produces
            self.lines.datetime[0] = bt.date2num(dt)
            self.lines.open[0] = bar["open"]
            self.lines.high[0] = bar["high"]
            self.lines.low[0] = bar["low"]
            self.lines.close[0] = bar["close"]
            self.lines.volume[0] = bar["volume"]
            self.lines.openinterest[0] = 0.0

            return True

        except queue.Empty:
            # Queue is empty, but we are not done. 
            # Returning None tells Cerebro "no data right now, try again in next loop iteration"
            return None
        except Exception as e:
            logger.error(f"Live Feed encountered error: {e}")
            return False
