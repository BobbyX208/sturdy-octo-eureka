from typing import Dict, Any, Tuple, List


class ProgressionDomain:
    
    def __init__(self, rep_ranks: List[Dict[str, Any]]):
        self.rep_ranks = rep_ranks
    
    def calculate_rep_rank(self, reputation: int) -> Tuple[int, str]:
        for rank in reversed(self.rep_ranks):
            if reputation >= rank["min_rep"]:
                return rank["rank"], rank["title"]
        
        return 1, "Newcomer"
    
    def rep_to_next_rank(self, reputation: int) -> int:
        for rank in self.rep_ranks:
            if reputation < rank["min_rep"]:
                return rank["min_rep"] - reputation
        
        return 0
    
    def can_prestige(self, player: Dict[str, Any]) -> Tuple[bool, str]:
        reputation = player.get("reputation", 0)
        total_earned = player.get("total_earned", 0)
        current_prestige = player.get("prestige", 0)
        
        if reputation < 25000:
            return False, f"Need reputation 25,000 (Legend rank). Current: {reputation}"
        
        if total_earned < 1000000:
            return False, f"Need lifetime earnings of 1,000,000 SC. Current: {total_earned}"
        
        if current_prestige >= 10:
            return False, "Maximum prestige level reached"
        
        return True, "OK"
    
    def calculate_prestige_reset(self, player: Dict[str, Any]) -> Dict[str, Any]:
        current_prestige = player.get("prestige", 0)
        new_prestige = current_prestige + 1
        
        bonus_multiplier = 1 + (new_prestige * 0.05)
        
        return {
            "new_prestige": new_prestige,
            "bonus_multiplier": bonus_multiplier,
            "reset_wallet": 0,
            "reset_bank": 0,
            "reset_reputation": 0,
            "reset_rep_rank": 1,
            "keep_items": True,
            "keep_premium": True
        }
    
    def calculate_district_unlock(self, reputation: int) -> List[int]:
        unlocked = [1]
        
        district_requirements = {
            2: 100,
            3: 500,
            4: 1000,
            5: 2500,
            6: 5000
        }
        
        for district, req in district_requirements.items():
            if reputation >= req:
                unlocked.append(district)
        
        return unlocked
    
    def get_district_requirement(self, district: int) -> int:
        requirements = {
            1: 0,
            2: 100,
            3: 500,
            4: 1000,
            5: 2500,
            6: 5000
        }
        
        return requirements.get(district, 0)
    
    def calculate_next_district(self, current_district: int, reputation: int) -> Tuple[bool, int, int]:
        next_district = current_district + 1
        
        if next_district > 6:
            return False, 0, 0
        
        requirement = self.get_district_requirement(next_district)
        
        if reputation >= requirement:
            return True, next_district, requirement
        
        return False, next_district, requirement
    
    def calculate_prestige_bonus(self, prestige_level: int, base_value: int) -> int:
        multiplier = 1 + (prestige_level * 0.05)
        
        return int(base_value * multiplier)
    
    def calculate_business_capacity(self, prestige_level: int, premium_tier: str = "citizen") -> int:
        base_capacity = 3
        
        prestige_bonus = prestige_level
        
        premium_bonus = {
            "citizen": 0,
            "resident": 0,
            "elite": 1,
            "obsidian": 2
        }.get(premium_tier, 0)
        
        return base_capacity + prestige_bonus + premium_bonus