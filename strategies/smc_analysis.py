"""
Smart Money Concepts (SMC) utility classes for market structure analysis.
Includes market structure analysis, order block detection, fair value gaps, and liquidity zones.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass


@dataclass
class SwingPoint:
    """Represents a swing high or low point."""

    index: int
    price: float
    timestamp: pd.Timestamp
    type: str  # 'high' or 'low'


@dataclass
class OrderBlock:
    """Represents an order block zone."""

    start_index: int
    end_index: int
    high: float
    low: float
    type: str  # 'demand' or 'supply'
    strength: float  # 0-1 strength rating
    timestamp: pd.Timestamp
    zone_id: str = ""  # Unique identifier for the zone
    used: bool = False  # Whether this zone has been used for trading


@dataclass
class FairValueGap:
    """Represents a fair value gap (imbalance)."""

    start_index: int
    end_index: int
    high: float
    low: float
    type: str  # 'bullish' or 'bearish'
    filled: bool
    timestamp: pd.Timestamp
    zone_id: str = ""  # Unique identifier for the zone
    used: bool = False  # Whether this zone has been used for trading


@dataclass
class LiquidityZone:
    """Represents a liquidity zone."""

    price: float
    type: str  # 'buy' or 'sell'
    strength: float
    timestamp: pd.Timestamp
    swept: bool


class MarketStructureAnalyzer:
    """
    Analyzes market structure for Break of Structure (BOS) and Change of Character (CHOCH).
    """

    def __init__(self, lookback_period: int = 20):
        """
        Initialize market structure analyzer.

        Args:
            lookback_period: Number of bars to look back for swing points
        """
        self.lookback_period = lookback_period
        self.swing_points: List[SwingPoint] = []

    def identify_trend(self, df: pd.DataFrame) -> str:
        """
        Identify overall trend direction using swing points.

        Args:
            df: Price data DataFrame

        Returns:
            'Bullish', 'Bearish', or 'Sideways'
        """
        swing_points = self.find_swing_points(df)

        if len(swing_points) < 2:
            return "Sideways"

        # Compare recent swing highs and lows
        recent_highs = [sp for sp in swing_points[-5:] if sp.type == "high"]
        recent_lows = [sp for sp in swing_points[-5:] if sp.type == "low"]

        if not recent_highs or not recent_lows:
            return "Sideways"

        # Check for higher highs and higher lows (bullish)
        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if recent_highs[-1].price > recent_highs[-2].price and recent_lows[-1].price > recent_lows[-2].price:
                return "Bullish"

        # Check for lower highs and lower lows (bearish)
        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if recent_highs[-1].price < recent_highs[-2].price and recent_lows[-1].price < recent_lows[-2].price:
                return "Bearish"

        return "Sideways"

    def find_swing_points(self, df: pd.DataFrame) -> List[SwingPoint]:
        """
        Find swing highs and lows in the price data.

        Args:
            df: Price data DataFrame

        Returns:
            List of SwingPoint objects
        """
        swing_points = []

        for i in range(self.lookback_period, len(df) - self.lookback_period):
            current_high = df["high"].iloc[i]
            current_low = df["low"].iloc[i]

            # Check for swing high
            is_swing_high = True
            for j in range(i - self.lookback_period, i + self.lookback_period + 1):
                if j != i and df["high"].iloc[j] >= current_high:
                    is_swing_high = False
                    break

            if is_swing_high:
                swing_points.append(SwingPoint(index=i, price=current_high, timestamp=df.index[i], type="high"))

            # Check for swing low
            is_swing_low = True
            for j in range(i - self.lookback_period, i + self.lookback_period + 1):
                if j != i and df["low"].iloc[j] <= current_low:
                    is_swing_low = False
                    break

            if is_swing_low:
                swing_points.append(SwingPoint(index=i, price=current_low, timestamp=df.index[i], type="low"))

        self.swing_points = swing_points
        return swing_points

    def detect_structure_breaks(self, df: pd.DataFrame) -> Dict[str, bool]:
        """
        Detect Break of Structure (BOS) events.

        Args:
            df: Price data DataFrame

        Returns:
            Dictionary with BOS detection results
        """
        swing_points = self.find_swing_points(df)

        if len(swing_points) < 2:
            return {"bullish_bos": False, "bearish_bos": False}

        # Get recent swing points
        recent_swings = swing_points[-10:]  # Last 10 swing points

        bullish_bos = False
        bearish_bos = False

        # Check for bullish BOS (break above recent swing high)
        recent_highs = [sp for sp in recent_swings if sp.type == "high"]
        if recent_highs:
            highest_swing = max(recent_highs, key=lambda x: x.price)
            current_price = df["close"].iloc[-1]
            if current_price > highest_swing.price:
                bullish_bos = True

        # Check for bearish BOS (break below recent swing low)
        recent_lows = [sp for sp in recent_swings if sp.type == "low"]
        if recent_lows:
            lowest_swing = min(recent_lows, key=lambda x: x.price)
            current_price = df["close"].iloc[-1]
            if current_price < lowest_swing.price:
                bearish_bos = True

        return {
            "bullish_bos": bullish_bos,
            "bearish_bos": bearish_bos,
            "last_swing_high": recent_highs[-1].price if recent_highs else None,
            "last_swing_low": recent_lows[-1].price if recent_lows else None,
        }

    def detect_choch(self, df: pd.DataFrame) -> Dict[str, bool]:
        """
        Detect Change of Character (CHOCH) events.

        Args:
            df: Price data DataFrame

        Returns:
            Dictionary with CHOCH detection results
        """
        swing_points = self.find_swing_points(df)

        if len(swing_points) < 4:
            return {"bullish_choch": False, "bearish_choch": False}

        # Get recent swing points
        recent_swings = swing_points[-6:]  # Last 6 swing points

        bullish_choch = False
        bearish_choch = False

        # Check for bullish CHOCH (higher low after lower low)
        lows = [sp for sp in recent_swings if sp.type == "low"]
        if len(lows) >= 2:
            if lows[-1].price > lows[-2].price:
                bullish_choch = True

        # Check for bearish CHOCH (lower high after higher high)
        highs = [sp for sp in recent_swings if sp.type == "high"]
        if len(highs) >= 2:
            if highs[-1].price < highs[-2].price:
                bearish_choch = True

        return {"bullish_choch": bullish_choch, "bearish_choch": bearish_choch}

    def get_market_bias(self, df: pd.DataFrame) -> str:
        """
        Determine current market bias based on structure.

        Args:
            df: Price data DataFrame

        Returns:
            'Bullish', 'Bearish', or 'Neutral'
        """
        structure_breaks = self.detect_structure_breaks(df)
        choch = self.detect_choch(df)

        if structure_breaks["bullish_bos"] or choch["bullish_choch"]:
            return "Bullish"
        elif structure_breaks["bearish_bos"] or choch["bearish_choch"]:
            return "Bearish"
        else:
            return "Neutral"


class OrderBlockDetector:
    """
    Detects order blocks (supply and demand zones) in price data.
    """

    def __init__(self, min_strength: float = 0.6):
        """
        Initialize order block detector.

        Args:
            min_strength: Minimum strength threshold for order blocks
        """
        self.min_strength = min_strength
        self.order_blocks: List[OrderBlock] = []

    def find_order_blocks(self, df: pd.DataFrame) -> List[OrderBlock]:
        """
        Find order blocks in the price data.

        Args:
            df: Price data DataFrame

        Returns:
            List of OrderBlock objects
        """
        order_blocks = []

        # Find potential order blocks by looking for strong moves followed by reversals
        for i in range(5, len(df) - 5):
            # Look for strong bullish move (demand block)
            if self._is_strong_bullish_move(df, i):
                ob = self._create_demand_block(df, i)
                if ob and ob.strength >= self.min_strength:
                    order_blocks.append(ob)

            # Look for strong bearish move (supply block)
            if self._is_strong_bearish_move(df, i):
                ob = self._create_supply_block(df, i)
                if ob and ob.strength >= self.min_strength:
                    order_blocks.append(ob)

        self.order_blocks = order_blocks
        return order_blocks

    def _is_strong_bullish_move(self, df: pd.DataFrame, index: int) -> bool:
        """Check if there's a strong bullish move at the given index."""
        if index < 2 or index >= len(df) - 2:
            return False

        # Check for strong bullish candle
        current = df.iloc[index]
        prev = df.iloc[index - 1]

        # Strong bullish candle criteria
        body_size = current["close"] - current["open"]
        total_range = current["high"] - current["low"]

        if body_size <= 0 or total_range == 0:
            return False

        body_ratio = body_size / total_range

        # Strong bullish candle with significant body
        return body_ratio > 0.7 and current["close"] > prev["high"] and body_size > df["close"].rolling(20).std().iloc[index] * 0.5

    def _is_strong_bearish_move(self, df: pd.DataFrame, index: int) -> bool:
        """Check if there's a strong bearish move at the given index."""
        if index < 2 or index >= len(df) - 2:
            return False

        # Check for strong bearish candle
        current = df.iloc[index]
        prev = df.iloc[index - 1]

        # Strong bearish candle criteria
        body_size = current["open"] - current["close"]
        total_range = current["high"] - current["low"]

        if body_size <= 0 or total_range == 0:
            return False

        body_ratio = body_size / total_range

        # Strong bearish candle with significant body
        return body_ratio > 0.7 and current["close"] < prev["low"] and body_size > df["close"].rolling(20).std().iloc[index] * 0.5

    def _create_demand_block(self, df: pd.DataFrame, index: int) -> Optional[OrderBlock]:
        """Create a demand order block."""
        if index < 1 or index >= len(df) - 1:
            return None

        # Demand block is the last bearish candle before the strong bullish move
        demand_candle = df.iloc[index - 1]

        # Calculate strength based on volume and price action
        volume_strength = self._calculate_volume_strength(df, index - 1)
        price_strength = self._calculate_price_strength(df, index - 1, "demand")

        strength = (volume_strength + price_strength) / 2

        # Generate unique zone ID
        zone_id = f"demand_{index}_{demand_candle['timestamp'] if 'timestamp' in demand_candle else df.index[index - 1]}"

        return OrderBlock(
            start_index=index - 1,
            end_index=index - 1,
            high=demand_candle["high"],
            low=demand_candle["low"],
            type="demand",
            strength=strength,
            timestamp=df.index[index - 1],
            zone_id=zone_id,
            used=False,
        )

    def _create_supply_block(self, df: pd.DataFrame, index: int) -> Optional[OrderBlock]:
        """Create a supply order block."""
        if index < 1 or index >= len(df) - 1:
            return None

        # Supply block is the last bullish candle before the strong bearish move
        supply_candle = df.iloc[index - 1]

        # Calculate strength based on volume and price action
        volume_strength = self._calculate_volume_strength(df, index - 1)
        price_strength = self._calculate_price_strength(df, index - 1, "supply")

        strength = (volume_strength + price_strength) / 2

        # Generate unique zone ID
        zone_id = f"supply_{index}_{supply_candle['timestamp'] if 'timestamp' in supply_candle else df.index[index - 1]}"

        return OrderBlock(
            start_index=index - 1,
            end_index=index - 1,
            high=supply_candle["high"],
            low=supply_candle["low"],
            type="supply",
            strength=strength,
            timestamp=df.index[index - 1],
            zone_id=zone_id,
            used=False,
        )

    def _calculate_volume_strength(self, df: pd.DataFrame, index: int) -> float:
        """Calculate volume strength for order block."""
        if "volume" not in df.columns or index < 20:
            return 0.5  # Default if no volume data

        current_volume = df["volume"].iloc[index]
        avg_volume = df["volume"].rolling(20).mean().iloc[index]

        if avg_volume == 0:
            return 0.5

        volume_ratio = current_volume / avg_volume
        return min(1.0, volume_ratio / 2.0)  # Normalize to 0-1

    def _calculate_price_strength(self, df: pd.DataFrame, index: int, block_type: str) -> float:
        """Calculate price action strength for order block."""
        if index < 5 or index >= len(df) - 5:
            return 0.5

        candle = df.iloc[index]

        if block_type == "demand":
            # For demand blocks, check how quickly price left the zone
            next_candles = df.iloc[index + 1 : index + 6]
            if len(next_candles) > 0:
                min_low = next_candles["low"].min()
                if min_low > candle["high"]:
                    return 1.0  # Strong demand
                elif min_low > candle["close"]:
                    return 0.8
                else:
                    return 0.3

        elif block_type == "supply":
            # For supply blocks, check how quickly price left the zone
            next_candles = df.iloc[index + 1 : index + 6]
            if len(next_candles) > 0:
                max_high = next_candles["high"].max()
                if max_high < candle["low"]:
                    return 1.0  # Strong supply
                elif max_high < candle["close"]:
                    return 0.8
                else:
                    return 0.3

        return 0.5

    def find_premium_discount_zones(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """
        Find premium and discount zones based on recent range.

        Args:
            df: Price data DataFrame

        Returns:
            Dictionary with premium and discount zone information
        """
        if len(df) < 50:
            return {"premium": None, "discount": None, "midpoint": None}

        # Use last 50 bars to determine range
        recent_data = df.tail(50)
        range_high = recent_data["high"].max()
        range_low = recent_data["low"].min()
        midpoint = (range_high + range_low) / 2

        return {
            "premium": {"high": range_high, "low": midpoint, "type": "supply"},
            "discount": {"high": midpoint, "low": range_low, "type": "demand"},
            "midpoint": midpoint,
            "range_high": range_high,
            "range_low": range_low,
        }

    def is_price_in_zone(self, price: float, zone: Dict) -> bool:
        """Check if price is within a given zone."""
        if zone is None:
            return False
        return zone["low"] <= price <= zone["high"]


class FairValueGapDetector:
    """
    Detects Fair Value Gaps (FVGs) or imbalances in price data.
    """

    def __init__(self, min_gap_size: float = 0.001):
        """
        Initialize FVG detector.

        Args:
            min_gap_size: Minimum gap size as percentage of price
        """
        self.min_gap_size = min_gap_size
        self.fair_value_gaps: List[FairValueGap] = []

    def scan_for_gaps(self, df: pd.DataFrame) -> List[FairValueGap]:
        """
        Scan for fair value gaps in the price data.

        Args:
            df: Price data DataFrame

        Returns:
            List of FairValueGap objects
        """
        gaps = []

        for i in range(2, len(df) - 1):
            # Check for bullish FVG (gap up)
            bullish_gap = self._detect_bullish_gap(df, i)
            if bullish_gap:
                gaps.append(bullish_gap)

            # Check for bearish FVG (gap down)
            bearish_gap = self._detect_bearish_gap(df, i)
            if bearish_gap:
                gaps.append(bearish_gap)

        self.fair_value_gaps = gaps
        return gaps

    def _detect_bullish_gap(self, df: pd.DataFrame, index: int) -> Optional[FairValueGap]:
        """Detect bullish fair value gap."""
        if index < 2 or index >= len(df) - 1:
            return None

        # Three-candle pattern for bullish FVG
        candle1 = df.iloc[index - 2]  # First candle
        candle2 = df.iloc[index - 1]  # Second candle (gap candle)
        candle3 = df.iloc[index]  # Third candle

        # Check for gap: candle2 low > candle1 high
        if candle2["low"] > candle1["high"]:
            gap_size = (candle2["low"] - candle1["high"]) / candle1["high"]

            if gap_size >= self.min_gap_size:
                # Generate unique zone ID
                zone_id = f"bullish_fvg_{index}_{df.index[index]}"

                return FairValueGap(
                    start_index=index - 2,
                    end_index=index,
                    high=candle2["low"],
                    low=candle1["high"],
                    type="bullish",
                    filled=False,
                    timestamp=df.index[index],
                    zone_id=zone_id,
                    used=False,
                )

        return None

    def _detect_bearish_gap(self, df: pd.DataFrame, index: int) -> Optional[FairValueGap]:
        """Detect bearish fair value gap."""
        if index < 2 or index >= len(df) - 1:
            return None

        # Three-candle pattern for bearish FVG
        candle1 = df.iloc[index - 2]  # First candle
        candle2 = df.iloc[index - 1]  # Second candle (gap candle)
        candle3 = df.iloc[index]  # Third candle

        # Check for gap: candle2 high < candle1 low
        if candle2["high"] < candle1["low"]:
            gap_size = (candle1["low"] - candle2["high"]) / candle1["low"]

            if gap_size >= self.min_gap_size:
                # Generate unique zone ID
                zone_id = f"bearish_fvg_{index}_{df.index[index]}"

                return FairValueGap(
                    start_index=index - 2,
                    end_index=index,
                    high=candle1["low"],
                    low=candle2["high"],
                    type="bearish",
                    filled=False,
                    timestamp=df.index[index],
                    zone_id=zone_id,
                    used=False,
                )

        return None

    def check_gap_fill(self, df: pd.DataFrame, gap: FairValueGap) -> bool:
        """Check if a fair value gap has been filled."""
        if gap.filled:
            return True

        # Check if price has returned to fill the gap
        current_price = df["close"].iloc[-1]

        if gap.type == "bullish":
            # Bullish gap is filled when price comes back down
            return current_price <= gap.high
        else:
            # Bearish gap is filled when price comes back up
            return current_price >= gap.low

    def get_active_gaps(self, df: pd.DataFrame) -> List[FairValueGap]:
        """Get all unfilled fair value gaps."""
        active_gaps = []

        for gap in self.fair_value_gaps:
            if not self.check_gap_fill(df, gap):
                active_gaps.append(gap)

        return active_gaps


class LiquidityZoneMapper:
    """
    Maps liquidity zones and detects liquidity sweeps.
    """

    def __init__(self, sweep_threshold: float = 0.002):
        """
        Initialize liquidity zone mapper.

        Args:
            sweep_threshold: Minimum price movement to consider a sweep
        """
        self.sweep_threshold = sweep_threshold
        self.liquidity_zones: List[LiquidityZone] = []

    def identify_liquidity_sweeps(self, df: pd.DataFrame) -> List[LiquidityZone]:
        """
        Identify liquidity sweeps in the price data.

        Args:
            df: Price data DataFrame

        Returns:
            List of LiquidityZone objects
        """
        zones = []

        # Look for liquidity above recent highs and below recent lows
        for i in range(20, len(df) - 5):
            # Check for liquidity sweep above recent high
            recent_high = df["high"].iloc[i - 20 : i].max()
            current_high = df["high"].iloc[i]

            if current_high > recent_high * (1 + self.sweep_threshold):
                # Check if price reversed after the sweep
                next_low = df["low"].iloc[i + 1 : i + 6].min()
                if next_low < recent_high:
                    zones.append(LiquidityZone(price=recent_high, type="sell", strength=0.8, timestamp=df.index[i], swept=True))

            # Check for liquidity sweep below recent low
            recent_low = df["low"].iloc[i - 20 : i].min()
            current_low = df["low"].iloc[i]

            if current_low < recent_low * (1 - self.sweep_threshold):
                # Check if price reversed after the sweep
                next_high = df["high"].iloc[i + 1 : i + 6].max()
                if next_high > recent_low:
                    zones.append(LiquidityZone(price=recent_low, type="buy", strength=0.8, timestamp=df.index[i], swept=True))

        self.liquidity_zones = zones
        return zones

    def find_liquidity_levels(self, df: pd.DataFrame, lookback: int = 50) -> List[LiquidityZone]:
        """
        Find potential liquidity levels (recent highs and lows).

        Args:
            df: Price data DataFrame
            lookback: Number of bars to look back

        Returns:
            List of LiquidityZone objects
        """
        zones = []

        if len(df) < lookback:
            return zones

        recent_data = df.tail(lookback)

        # Find significant highs and lows
        highs = recent_data["high"].rolling(5).max() == recent_data["high"]
        lows = recent_data["low"].rolling(5).min() == recent_data["low"]

        for i, (idx, row) in enumerate(recent_data.iterrows()):
            if highs.iloc[i]:
                zones.append(LiquidityZone(price=row["high"], type="sell", strength=0.6, timestamp=idx, swept=False))

            if lows.iloc[i]:
                zones.append(LiquidityZone(price=row["low"], type="buy", strength=0.6, timestamp=idx, swept=False))

        return zones


# Example usage
if __name__ == "__main__":
    # Create sample data
    dates = pd.date_range("2023-01-01", periods=100, freq="1H")
    np.random.seed(42)
    prices = 50000 + np.cumsum(np.random.randn(100) * 100)

    df = pd.DataFrame(
        {
            "open": prices,
            "high": prices + np.random.rand(100) * 50,
            "low": prices - np.random.rand(100) * 50,
            "close": prices + np.random.randn(100) * 20,
            "volume": np.random.randint(1000, 10000, 100),
        },
        index=dates,
    )

    # Test MarketStructureAnalyzer
    analyzer = MarketStructureAnalyzer()
    trend = analyzer.identify_trend(df)
    print(f"Market trend: {trend}")

    bos = analyzer.detect_structure_breaks(df)
    print(f"Structure breaks: {bos}")

    # Test OrderBlockDetector
    ob_detector = OrderBlockDetector()
    order_blocks = ob_detector.find_order_blocks(df)
    print(f"Found {len(order_blocks)} order blocks")

    zones = ob_detector.find_premium_discount_zones(df)
    print(f"Premium/Discount zones: {zones}")

    # Test FairValueGapDetector
    fvg_detector = FairValueGapDetector()
    gaps = fvg_detector.scan_for_gaps(df)
    print(f"Found {len(gaps)} fair value gaps")

    # Test LiquidityZoneMapper
    liquidity_mapper = LiquidityZoneMapper()
    liquidity_zones = liquidity_mapper.identify_liquidity_sweeps(df)
    print(f"Found {len(liquidity_zones)} liquidity zones")
