from typing import Dict, Any
from .base_engine import BaseEngine
from .logger import get_logger

logger = get_logger(__name__)


class BTLiveEngine(BaseEngine):
    """
    Concrete implementation of LiveEngine using Backtrader.
    (Placeholder for Stage 2)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    def add_data(self):
        """Add live data feeds."""
        logger.warning("Live trading data feed not yet implemented.")

    def run_live(self):
        """Run live trading."""
        logger.info("Starting Backtrader Live Trading...")
        logger.warning("Live trading mode is currently under development (Stage 2).")
