
class PatternDetector:
    """
    Stateless detector of candlestick patterns.
    Extracted from PriceActionStrategy to adhere to SRP/OCP.
    """

    @staticmethod
    def is_bullish_pinbar(open_p, high, low, close, atr, params):
        """
        Check for Bullish Pinbar.
        params: object with min_range_factor, max_body_to_range, min_wick_to_range
        """
        body = abs(close - open_p)
        rng = high - low
        if rng == 0: return False
        
        # Check if bar size is significant enough
        if rng < (atr * params.min_range_factor): return False
        
        lower_wick = min(open_p, close) - low
        
        return (
            body < params.max_body_to_range * rng and 
            lower_wick > params.min_wick_to_range * rng
        )

    @staticmethod
    def is_bearish_pinbar(open_p, high, low, close, atr, params):
        """
        Check for Bearish Pinbar.
        """
        body = abs(close - open_p)
        rng = high - low
        if rng == 0: return False
        
        # Check if bar size is significant enough
        if rng < (atr * params.min_range_factor): return False
        
        upper_wick = high - max(open_p, close)
        
        return (
            body < params.max_body_to_range * rng and 
            upper_wick > params.min_wick_to_range * rng
        )

    @staticmethod
    def is_bullish_engulfing(prev_open, prev_close, curr_open, curr_close, curr_high, curr_low, atr, params):
        """
        Check for Bullish Engulfing.
        """
        rng = curr_high - curr_low
        if rng < (atr * params.min_range_factor): return False
        
        if prev_close < prev_open and curr_close > curr_open:
            return (
                curr_close >= prev_open and 
                curr_open <= prev_close
            )
        return False

    @staticmethod
    def is_bearish_engulfing(prev_open, prev_close, curr_open, curr_close, curr_high, curr_low, atr, params):
        """
        Check for Bearish Engulfing.
        """
        rng = curr_high - curr_low
        if rng < (atr * params.min_range_factor): return False
        
        if prev_close > prev_open and curr_close < curr_open:
             return (
                curr_close <= prev_open and 
                curr_open >= prev_close
            )
        return False
