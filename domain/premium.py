from typing import Dict, Any, Tuple


class PremiumDomain:
    
    def __init__(self, tier_config: Dict[str, Dict[str, Any]]):
        self.tier_config = tier_config
    
    def get_tier_info(self, tier: str) -> Dict[str, Any]:
        return self.tier_config.get(tier, self.tier_config.get("citizen", {}))
    
    def is_premium_active(self, player: Dict[str, Any]) -> bool:
        tier = player.get("premium_tier", "citizen")
        
        if tier == "citizen":
            return True
        
        expires = player.get("premium_expires")
        
        if not expires:
            return False
        
        from datetime import datetime, timezone
        return expires > datetime.now(timezone.utc)
    
    def get_effective_tier(self, player: Dict[str, Any]) -> str:
        if not self.is_premium_active(player):
            return "citizen"
        
        return player.get("premium_tier", "citizen")
    
    def get_daily_bonus_multiplier(self, tier: str) -> float:
        config = self.get_tier_info(tier)
        return config.get("daily_bonus", 1.0)
    
    def get_cooldown_reduction(self, tier: str) -> float:
        config = self.get_tier_info(tier)
        return config.get("cooldown_reduction", 0.0)
    
    def get_max_jobs(self, tier: str) -> int:
        config = self.get_tier_info(tier)
        return config.get("max_jobs", 3)
    
    def get_max_businesses(self, tier: str) -> int:
        config = self.get_tier_info(tier)
        return config.get("max_businesses", 3)
    
    def get_npc_memory_depth(self, tier: str) -> int:
        config = self.get_tier_info(tier)
        return config.get("memory_depth", 5)
    
    def can_use_analyst(self, tier: str, daily_usage: int = 0) -> Tuple[bool, str]:
        if tier == "citizen":
            return False, "Analyst is available for Elite and Obsidian tiers"
        
        if tier == "resident":
            return False, "Analyst is available for Elite and Obsidian tiers"
        
        if tier == "elite":
            if daily_usage >= 3:
                return False, "Elite tier limited to 3 analyst calls per day"
            return True, "OK"
        
        if tier == "obsidian":
            return True, "OK"
        
        return False, "Unknown tier"
    
    def can_use_billboard(self, tier: str) -> Tuple[bool, str]:
        if tier == "obsidian":
            return True, "OK"
        
        return False, "Billboard is available for Obsidian tier only"
    
    def get_server_premium_features(self, guild_id: int, features: Dict[str, Any]) -> Dict[str, Any]:
        default_features = {
            "custom_district_channels": False,
            "unlimited_factions": False,
            "scheduled_turf_wars": False,
            "server_leaderboard": False,
            "custom_welcome_message": False
        }
        
        default_features.update(features)
        
        return default_features
    
    def calculate_feature_access(self, tier: str, feature: str) -> bool:
        feature_access = {
            "analyst": ["elite", "obsidian"],
            "billboard": ["obsidian"],
            "early_season": ["elite", "obsidian"],
            "unlimited_transactions": ["obsidian"],
            "priority_support": ["elite", "obsidian"]
        }
        
        allowed_tiers = feature_access.get(feature, [])
        
        return tier in allowed_tiers