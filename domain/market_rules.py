from typing import Dict, Any, Tuple, List


class MarketRules:
    
    def __init__(self, listing_fee_rate: float = 0.05, max_listing_days: int = 7):
        self.listing_fee_rate = listing_fee_rate
        self.max_listing_days = max_listing_days
    
    def calculate_listing_fee(self, price_per_unit: int, quantity: int) -> int:
        total_value = price_per_unit * quantity
        
        fee = int(total_value * self.listing_fee_rate)
        
        return max(fee, 10)
    
    def can_list_item(self, seller_rep: int, item_tier: str = "common") -> Tuple[bool, str]:
        rep_requirements = {
            "common": 0,
            "uncommon": 2,
            "rare": 4,
            "epic": 6,
            "legendary": 8
        }
        
        required_rep = rep_requirements.get(item_tier, 0)
        
        if seller_rep < required_rep:
            return False, f"Requires reputation {required_rep} to list {item_tier} items"
        
        return True, "OK"
    
    def calculate_price_range(self, base_price: int, seller_rep: int, market_demand: float = 1.0) -> Tuple[int, int]:
        rep_bonus = 1 + min(seller_rep / 10000, 0.5)
        
        min_price = int(base_price * 0.5 * rep_bonus)
        max_price = int(base_price * 2.0 * market_demand)
        
        return min_price, max_price
    
    def calculate_expiration(self, listing_days: int = None) -> int:
        if listing_days is None:
            listing_days = self.max_listing_days
        
        return min(listing_days, self.max_listing_days)
    
    def calculate_market_tax(self, sale_amount: int, seller_rep: int) -> int:
        base_tax_rate = 0.10
        
        rep_reduction = min(seller_rep / 10000, 0.05)
        
        tax_rate = base_tax_rate - rep_reduction
        
        tax = int(sale_amount * tax_rate)
        
        return max(tax, 1)
    
    def calculate_demand_multiplier(self, item_id: str, recent_sales: int, total_listed: int) -> float:
        if total_listed == 0:
            return 1.0
        
        sell_through_rate = recent_sales / total_listed
        
        if sell_through_rate > 0.5:
            return 1.2
        elif sell_through_rate > 0.3:
            return 1.1
        elif sell_through_rate > 0.1:
            return 1.0
        else:
            return 0.9