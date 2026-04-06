import math
from typing import Dict, Any, Optional


class JobDomain:
    
    def __init__(self, job_config: Dict[str, Dict[str, Any]]):
        self.job_config = job_config
    
    def calculate_reward(self, player: Dict[str, Any], job_id: str) -> int:
        job = self.job_config.get(job_id)
        if not job:
            return 0
        
        base_pay = job.get("base_pay", 50)
        
        rep_multiplier = 1 + (player.get("rep_rank", 1) * 0.1)
        
        premium_multipliers = {
            "citizen": 1.0,
            "resident": 1.2,
            "elite": 1.4,
            "obsidian": 2.0
        }
        premium_multiplier = premium_multipliers.get(player.get("premium_tier", "citizen"), 1.0)
        
        district_bonus = self._get_district_bonus(player.get("district", 1), job.get("district", 1))
        
        streak_bonus = 1 + (min(player.get("daily_streak", 0), 7) * 0.08)
        
        reward = int(base_pay * rep_multiplier * premium_multiplier * district_bonus * streak_bonus)
        
        return max(reward, base_pay)
    
    def _get_district_bonus(self, player_district: int, job_district: int) -> float:
        if player_district == job_district:
            return 1.15
        
        return 1.0
    
    def calculate_hire_chance(self, player: Dict[str, Any], job_id: str) -> float:
        job = self.job_config.get(job_id, {})
        base_chance = job.get("hire_chance", 0.5)
        
        required_rep = job.get("min_rep", 0)
        player_rep = player.get("reputation", 0)
        
        if player_rep < required_rep:
            return 0.0
        
        rep_bonus = min(player_rep / 5000, 0.25)
        
        premium_bonus = 0.0
        premium_tier = player.get("premium_tier", "citizen")
        if premium_tier == "elite":
            premium_bonus = 0.1
        elif premium_tier == "obsidian":
            premium_bonus = 0.15
        
        final_chance = min(base_chance + rep_bonus + premium_bonus, 0.95)
        
        return round(final_chance, 2)
    
    def calculate_passive_income(self, player: Dict[str, Any], job_id: str) -> int:
        job = self.job_config.get(job_id, {})
        base_passive = job.get("passive_income", 25)
        
        efficiency = player.get("business_efficiency", 1.0)
        
        premium_multipliers = {
            "citizen": 1.0,
            "resident": 1.1,
            "elite": 1.2,
            "obsidian": 1.3
        }
        premium_multiplier = premium_multipliers.get(player.get("premium_tier", "citizen"), 1.0)
        
        return int(base_passive * efficiency * premium_multiplier)
    
    def can_apply(self, player: Dict[str, Any], job_id: str, current_job_count: int, max_jobs: int) -> tuple[bool, str]:
        job = self.job_config.get(job_id, {})
        
        if not job:
            return False, "Job does not exist"
        
        if player.get("is_jailed", False):
            return False, "You are in jail and cannot apply for jobs"
        
        if player.get("reputation", 0) < job.get("min_rep", 0):
            return False, f"Requires reputation {job.get('min_rep', 0)}"
        
        if current_job_count >= max_jobs:
            return False, f"You already have the maximum of {max_jobs} jobs"
        
        return True, "OK"
    
    def calculate_cooldown(self, player: Dict[str, Any], base_cooldown: int) -> int:
        cooldown_reductions = {
            "citizen": 0,
            "resident": 0.1,
            "elite": 0.2,
            "obsidian": 0.3
        }
        reduction = cooldown_reductions.get(player.get("premium_tier", "citizen"), 0)
        
        return int(base_cooldown * (1 - reduction))