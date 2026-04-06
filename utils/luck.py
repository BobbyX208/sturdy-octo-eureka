import random
import secrets
from typing import Tuple, Optional, List, Any


class Luck:
    
    @staticmethod
    def roll_dice(sides: int = 6) -> int:
        return random.randint(1, sides)
    
    @staticmethod
    def roll_multiple(count: int, sides: int = 6) -> List[int]:
        return [random.randint(1, sides) for _ in range(count)]
    
    @staticmethod
    def chance(probability: float) -> bool:
        if probability <= 0:
            return False
        if probability >= 1:
            return True
        
        return random.random() < probability
    
    @staticmethod
    def weighted_choice(options: List[Any], weights: List[float]) -> Any:
        if not options:
            return None
        
        if len(options) != len(weights):
            raise ValueError("Options and weights must have same length")
        
        total = sum(weights)
        if total <= 0:
            return random.choice(options)
        
        r = random.random() * total
        
        cumulative = 0
        for option, weight in zip(options, weights):
            cumulative += weight
            if r < cumulative:
                return option
        
        return options[-1]
    
    @staticmethod
    def weighted_choice_dict(weighted_dict: dict) -> Any:
        items = list(weighted_dict.items())
        weights = [w for _, w in items]
        
        if not items:
            return None
        
        return Luck.weighted_choice([k for k, _ in items], weights)
    
    @staticmethod
    def random_range(min_val: int, max_val: int) -> int:
        return random.randint(min_val, max_val)
    
    @staticmethod
    def random_float(min_val: float, max_val: float) -> float:
        return random.uniform(min_val, max_val)
    
    @staticmethod
    def shuffle(items: List[Any]) -> List[Any]:
        shuffled = items.copy()
        random.shuffle(shuffled)
        return shuffled
    
    @staticmethod
    def sample(items: List[Any], k: int) -> List[Any]:
        if k >= len(items):
            return items.copy()
        
        return random.sample(items, k)
    
    @staticmethod
    def secure_random_bytes(n: int) -> bytes:
        return secrets.token_bytes(n)
    
    @staticmethod
    def secure_random_hex(n: int) -> str:
        return secrets.token_hex(n)
    
    @staticmethod
    def success_rate(base_rate: float, modifiers: List[float] = None) -> Tuple[bool, float]:
        rate = base_rate
        
        if modifiers:
            for mod in modifiers:
                rate += mod
        
        rate = max(0.05, min(0.95, rate))
        
        success = random.random() < rate
        
        return success, rate
    
    @staticmethod
    def critical_chance(base_chance: float = 0.05) -> bool:
        return random.random() < base_chance
    
    @staticmethod
    def loot_amount(base_min: int, base_max: int, multiplier: float = 1.0, luck_stat: int = 0) -> int:
        luck_bonus = 1 + (luck_stat / 100)
        
        amount = random.randint(base_min, base_max)
        amount = int(amount * multiplier * luck_bonus)
        
        return max(1, amount)
    
    @staticmethod
    def gambler_roll(house_edge: float, min_multiplier: float, max_multiplier: float) -> Tuple[float, bool]:
        true_odds = 1 / ((min_multiplier + max_multiplier) / 2)
        
        player_win_chance = 1 - house_edge - true_odds
        
        win = random.random() < player_win_chance
        
        if win:
            multiplier = random.uniform(min_multiplier, max_multiplier)
        else:
            multiplier = 0
        
        return multiplier, win