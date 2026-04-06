import math
import random
from typing import Dict, Any, List, Tuple


class StockMath:
    
    def __init__(self, mu: float = 0.05, sigma: float = 0.2, max_sentiment: float = 0.1):
        self.mu = mu
        self.sigma = sigma
        self.max_sentiment = max_sentiment
    
    def geometric_brownian_motion(self, current_price: int, dt: float = 1.0) -> int:
        if current_price <= 0:
            return 10
        
        drift = (self.mu - 0.5 * self.sigma ** 2) * dt
        
        diffusion = self.sigma * math.sqrt(dt) * random.gauss(0, 1)
        
        price_multiplier = math.exp(drift + diffusion)
        
        new_price = int(current_price * price_multiplier)
        
        return max(10, min(10000, new_price))
    
    def apply_sentiment(self, price: int, net_pressure: int, volume_threshold: int = 1000) -> int:
        if abs(net_pressure) < volume_threshold:
            return price
        
        sentiment_impact = min(abs(net_pressure) / 10000, self.max_sentiment)
        
        if net_pressure > 0:
            multiplier = 1 + sentiment_impact
        else:
            multiplier = 1 - sentiment_impact
        
        new_price = int(price * multiplier)
        
        return max(10, min(10000, new_price))
    
    def apply_news_modifier(self, price: int, modifier: float) -> int:
        if modifier <= 0:
            return price
        
        new_price = int(price * modifier)
        
        return max(10, min(10000, new_price))
    
    def apply_event_multiplier(self, price: int, multiplier: float) -> int:
        if multiplier <= 0:
            return price
        
        new_price = int(price * multiplier)
        
        return max(10, min(10000, new_price))
    
    def calculate_sentiment_from_trades(self, buy_volume: int, sell_volume: int) -> Tuple[int, float]:
        net_pressure = buy_volume - sell_volume
        
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return net_pressure, 0.0
        
        sentiment_ratio = net_pressure / total_volume
        
        return net_pressure, sentiment_ratio
    
    def calculate_price_volatility(self, prices: List[int]) -> float:
        if len(prices) < 2:
            return 0.0
        
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(ret)
        
        if not returns:
            return 0.0
        
        mean_return = sum(returns) / len(returns)
        
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        
        return math.sqrt(variance)
    
    def calculate_moving_average(self, prices: List[int], window: int = 7) -> float:
        if len(prices) < window:
            return sum(prices) / len(prices) if prices else 0.0
        
        recent_prices = prices[-window:]
        
        return sum(recent_prices) / len(recent_prices)
    
    def calculate_rsi(self, prices: List[int], window: int = 14) -> float:
        if len(prices) < window + 1:
            return 50.0
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        recent_gains = gains[-window:]
        recent_losses = losses[-window:]
        
        avg_gain = sum(recent_gains) / window
        avg_loss = sum(recent_losses) / window
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def predict_movement(self, current_price: int, momentum: float, volatility: float) -> Tuple[str, float]:
        base_probability = 0.5
        
        momentum_impact = momentum * 0.1
        volatility_impact = volatility * 0.05
        
        up_probability = base_probability + momentum_impact - volatility_impact
        
        up_probability = max(0.3, min(0.7, up_probability))
        
        if random.random() < up_probability:
            expected_change = current_price * (self.mu + momentum * 0.1)
            return "UP", expected_change
        else:
            expected_change = current_price * (self.mu - volatility * 0.2)
            return "DOWN", expected_change
    
    def calculate_support_resistance(self, prices: List[int]) -> Tuple[int, int]:
        if len(prices) < 5:
            return 10, 10000
        
        recent_prices = prices[-20:]
        
        support = min(recent_prices)
        resistance = max(recent_prices)
        
        support = max(10, int(support * 0.95))
        resistance = min(10000, int(resistance * 1.05))
        
        return support, resistance