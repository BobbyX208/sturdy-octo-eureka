import random
print("✅ economy_rules.py loaded, random module:", random)
from typing import Dict, Any, Tuple


class EconomyRules:
    
    def __init__(self, tax_rate: float = 0.01, wealth_threshold: int = 500000, wealth_tax_rate: float = 0.005):
        self.tax_rate = tax_rate
        self.wealth_threshold = wealth_threshold
        self.wealth_tax_rate = wealth_tax_rate
    
    def calculate_wallet_tax(self, wallet: int) -> Tuple[int, int]:
        if wallet <= 0:
            return 0, 0
        
        tax = int(wallet * self.tax_rate)
        
        max_tax = 500
        if tax > max_tax:
            tax = max_tax
        
        return tax, wallet - tax
    
    def calculate_wealth_tax(self, wallet: int, bank: int) -> Tuple[int, int]:
        total_wealth = wallet + bank
        
        if total_wealth <= self.wealth_threshold:
            return 0, bank
        
        excess = total_wealth - self.wealth_threshold
        tax = int(excess * self.wealth_tax_rate)
        
        new_bank = bank - tax
        if new_bank < 0:
            tax = bank
            new_bank = 0
        
        return tax, new_bank
    
    def calculate_investment_tax(self, profit: int) -> int:
        if profit <= 0:
            return 0
        
        return int(profit * 0.15)
    
    def calculate_bank_fee(self, amount: int, is_deposit: bool, premium_tier: str = "citizen") -> int:
        if is_deposit:
            fee_rate = 0.005
        else:
            fee_rate = 0.01
        
        premium_reductions = {
            "citizen": 1.0,
            "resident": 0.5,
            "elite": 0.0,
            "obsidian": 0.0
        }
        
        reduction = premium_reductions.get(premium_tier, 1.0)
        
        fee = int(amount * fee_rate * (1 - reduction))
        
        return min(fee, 1000)
    
    def calculate_daily_reward(self, streak: int, premium_tier: str = "citizen") -> Tuple[int, int]:

        import random
        
        base_min = 200
        base_max = 800
        
        base_reward = random.randint(base_min, base_max)
        
        streak_multiplier = 1 + (min(streak, 7) * 0.08)
        
        premium_multipliers = {
            "citizen": 1.0,
            "resident": 1.2,
            "elite": 1.4,
            "obsidian": 2.0
        }
        premium_multiplier = premium_multipliers.get(premium_tier, 1.0)
        
        reward = int(base_reward * streak_multiplier * premium_multiplier)
        
        new_streak = streak + 1
        
        return reward, new_streak
    
    def calculate_streak_penalty(self, streak: int, days_missed: int) -> Tuple[int, int]:
        penalty = 100 * days_missed
        
        if days_missed >= 3:
            new_streak = 0
        else:
            new_streak = streak
        
        return penalty, new_streak
    
    def calculate_transfer_fee(self, amount: int, sender_tier: str = "citizen") -> int:
        base_fee = int(amount * 0.01)
        
        premium_reductions = {
            "citizen": 1.0,
            "resident": 0.5,
            "elite": 0.0,
            "obsidian": 0.0
        }
        
        reduction = premium_reductions.get(sender_tier, 1.0)
        
        fee = int(base_fee * (1 - reduction))
        
        return min(fee, 5000)
    
    def can_afford(self, balance: int, cost: int, is_bank: bool = False) -> Tuple[bool, int]:
        if balance >= cost:
            return True, balance - cost
        
        return False, balance