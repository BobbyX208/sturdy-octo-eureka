import random
from typing import Dict, Any, Tuple, Optional


class CrimeDomain:
    
    def __init__(self, crime_config: Dict[str, Dict[str, Any]]):
        self.crime_config = crime_config
    
    def calculate_success(self, player: Dict[str, Any], crime_type: str, district: int = 1) -> Tuple[bool, int, int, int]:
        crime = self.crime_config.get(crime_type)
        if not crime:
            return False, 0, 0, 0
        
        base_success_rate = crime.get("success_rate", 0.5)
        
        rep_penalty = min(player.get("reputation", 0) / 1000, 0.2)
        
        district_bonus = 0.0
        if district == 1:
            district_bonus = 0.08
        elif district == 6:
            district_bonus = 0.12
        
        heat_penalty = player.get("heat_level", 0) * 0.02
        
        final_success_rate = base_success_rate - rep_penalty + district_bonus - heat_penalty
        
        final_success_rate = max(0.1, min(0.8, final_success_rate))
        
        roll = random.random()
        success = roll < final_success_rate
        
        if success:
            loot = random.randint(crime.get("min_loot", 50), crime.get("max_loot", 200))
            loot = int(loot * self._get_loot_multiplier(player))
            fine = 0
            jail_hours = 0
        else:
            loot = 0
            fine = random.randint(crime.get("min_fine", 100), crime.get("max_fine", 300))
            jail_chance = crime.get("jail_chance", 0.2)
            
            if random.random() < jail_chance:
                jail_hours = self._calculate_jail_hours(player, crime_type)
            else:
                jail_hours = 0
        
        return success, loot, fine, jail_hours
    
    def _get_loot_multiplier(self, player: Dict[str, Any]) -> float:
        premium_multipliers = {
            "citizen": 1.0,
            "resident": 1.05,
            "elite": 1.1,
            "obsidian": 1.15
        }
        return premium_multipliers.get(player.get("premium_tier", "citizen"), 1.0)
    
    def _calculate_jail_hours(self, player: Dict[str, Any], crime_type: str) -> int:
        crime = self.crime_config.get(crime_type, {})
        base_hours = crime.get("jail_hours", 2)
        
        rep_multiplier = 1 + (player.get("rep_rank", 1) * 0.2)
        
        heat_multiplier = 1 + (player.get("heat_level", 0) * 0.1)
        
        hours = int(base_hours * rep_multiplier * heat_multiplier)
        
        return min(hours, 48)
    
    def calculate_rep_loss(self, player: Dict[str, Any], crime_type: str, success: bool) -> int:
        crime = self.crime_config.get(crime_type, {})
        base_loss = crime.get("rep_loss", 10)
        
        if success:
            return base_loss
        
        return base_loss * 2
    
    def calculate_heat_gain(self, crime_type: str, success: bool) -> int:
        crime = self.crime_config.get(crime_type, {})
        base_gain = crime.get("heat_gain", 1)
        
        if success:
            return base_gain
        
        return base_gain * 2
    
    def calculate_heist_success(self, participants: int, district: int, total_rep: int) -> float:
        base_rate = 0.42
        
        player_bonus = min(participants * 0.04, 0.2)
        
        district_bonus = 0.08 if district == 6 else 0.0
        
        rep_bonus = min(total_rep / 10000, 0.15)
        
        success_rate = base_rate + player_bonus + district_bonus + rep_bonus
        
        return min(0.7, max(0.3, success_rate))
    
    def calculate_heist_loot(self, participants: int, district: int, total_rep: int) -> int:
        base_loot = random.randint(8000, 35000)
        
        participant_multiplier = 1 + (participants * 0.15)
        
        district_multiplier = 1.2 if district == 4 else 1.0
        
        rep_multiplier = 1 + min(total_rep / 20000, 0.5)
        
        loot = int(base_loot * participant_multiplier * district_multiplier * rep_multiplier)
        
        return min(loot, 100000)
    
    def can_commit_crime(self, player: Dict[str, Any], crime_type: str) -> Tuple[bool, str]:
        crime = self.crime_config.get(crime_type)
        
        if not crime:
            return False, "Crime type does not exist"
        
        if player.get("is_jailed", False):
            return False, "You are in jail and cannot commit crimes"
        
        required_rep = crime.get("min_rep", 0)
        if player.get("reputation", 0) < required_rep:
            return False, f"Requires reputation {required_rep}"
        
        return True, "OK"
    
    def calculate_bounty_amount(self, crime_type: str) -> int:
        crime = self.crime_config.get(crime_type, {})
        base_bounty = crime.get("bounty", 500)
        
        return base_bounty * random.randint(1, 3)