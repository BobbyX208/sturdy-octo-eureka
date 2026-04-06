import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

from database.connection import DatabasePool
from database.queries import BusinessQueries, PlayerQueries
from core.cache import CacheManager
from events.bus import EventBus
from domain.premium import PremiumDomain
from config.settings import Config
from config.constants import GameConstants


class BusinessService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.logger = logging.getLogger("simcoin.services.business")
        
        self.business_queries = BusinessQueries(db)
        self.player_queries = PlayerQueries(db)
        
        self.premium_domain = PremiumDomain(Config.PREMIUM_TIERS)
        self.business_config = self._load_business_config()
    
    def _load_business_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            "food_stall": {"base_income": 500, "upkeep": 50, "min_rep": 0},
            "laundromat": {"base_income": 800, "upkeep": 100, "min_rep": 1},
            "bar": {"base_income": 1200, "upkeep": 200, "min_rep": 2},
            "warehouse": {"base_income": 1000, "upkeep": 150, "min_rep": 2},
            "retail_shop": {"base_income": 1500, "upkeep": 250, "min_rep": 3},
            "restaurant": {"base_income": 2000, "upkeep": 350, "min_rep": 4},
            "trading_post": {"base_income": 2500, "upkeep": 500, "min_rep": 5},
            "club": {"base_income": 3000, "upkeep": 750, "min_rep": 6},
            "black_market": {"base_income": 3500, "upkeep": 1000, "min_rep": 7},
            "investment_firm": {"base_income": 5000, "upkeep": 1500, "min_rep": 8}
        }
    
    async def open_business(self, user_id: int, business_type: str, name: str, district: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            config = self.business_config.get(business_type)
            
            if not config:
                return {"success": False, "message": "Invalid business type."}
            
            if player.get("reputation", 0) < config["min_rep"]:
                return {"success": False, "message": f"Requires reputation {config['min_rep']}."}
            
            effective_tier = self.premium_domain.get_effective_tier(player)
            max_businesses = self.premium_domain.get_max_businesses(effective_tier)
            
            current_businesses = await self.business_queries.get_user_businesses(user_id)
            
            if len(current_businesses) >= max_businesses:
                return {"success": False, "message": f"You already have {len(current_businesses)} businesses. Max is {max_businesses}."}
            
            has_license = await self._has_item(user_id, "business_license")
            
            if not has_license:
                return {"success": False, "message": "You need a Business License. Purchase from the market."}
            
            await self._remove_item(user_id, "business_license")
            
            business = await self.business_queries.create(
                user_id, name, business_type, district,
                config["base_income"], config["upkeep"]
            )
            
            await self.event_bus.fire("business.opened", {
                "user_id": user_id,
                "business_id": business["id"],
                "business_name": name,
                "business_type": business_type,
                "district": district
            })
            
            return {
                "success": True,
                "message": f"Opened {name} ({business_type}) in district {district}!",
                "business": dict(business)
            }
            
        except Exception as e:
            self.logger.error(f"Open business failed for {user_id}: {e}")
            raise
    
    async def collect_income(self, user_id: int, business_id: int) -> Dict[str, Any]:
        try:
            business = await self.business_queries.get(business_id)
            
            if not business:
                return {"success": False, "message": "Business not found."}
            
            if business["discord_id"] != user_id:
                return {"success": False, "message": "This is not your business."}
            
            player = await self.player_queries.get(user_id)
            
            last_collected = business["last_collected"]
            hours_passed = (datetime.now(timezone.utc) - last_collected).total_seconds() / 3600
            
            if hours_passed < 4:
                return {"success": False, "message": "Business income can be collected every 4 hours."}
            
            base_income = business["daily_income"]
            tier_multiplier = business["tier"]
            efficiency = business["efficiency_override"] or 1.0
            
            income = int(base_income * tier_multiplier * efficiency * (hours_passed / 24))
            
            await self.business_queries.update_collected(business_id)
            await self.player_queries.update_balance(user_id, wallet_delta=income)
            await self.player_queries.add_transaction(
                user_id, income, player.get("wallet", 0) + income,
                "business_income", f"Collected from {business['name']}"
            )
            
            await self.event_bus.fire("business.collected", {
                "user_id": user_id,
                "business_id": business_id,
                "business_name": business["name"],
                "income": income,
                "hours_passed": hours_passed
            })
            
            return {
                "success": True,
                "message": f"Collected {income} SC from {business['name']}!",
                "income": income
            }
            
        except Exception as e:
            self.logger.error(f"Collect income failed for {user_id}: {e}")
            raise
    
    async def restock(self, user_id: int, business_id: int) -> Dict[str, Any]:
        try:
            business = await self.business_queries.get(business_id)
            
            if not business:
                return {"success": False, "message": "Business not found."}
            
            if business["discord_id"] != user_id:
                return {"success": False, "message": "This is not your business."}
            
            if business["status"] == "neglected":
                await self.business_queries.update_efficiency(business_id, 1.25)
            
            await self.business_queries.update_restocked(business_id)
            
            return {
                "success": True,
                "message": f"Restocked {business['name']}. Efficiency restored."
            }
            
        except Exception as e:
            self.logger.error(f"Restock failed for {user_id}: {e}")
            raise
    
    async def upgrade(self, user_id: int, business_id: int) -> Dict[str, Any]:
        try:
            business = await self.business_queries.get(business_id)
            
            if not business:
                return {"success": False, "message": "Business not found."}
            
            if business["discord_id"] != user_id:
                return {"success": False, "message": "This is not your business."}
            
            if business["tier"] >= 3:
                return {"success": False, "message": "Business is already max tier."}
            
            upgrade_costs = {1: 25000, 2: 100000}
            cost = upgrade_costs.get(business["tier"], 50000)
            
            player = await self.player_queries.get(user_id)
            
            if player.get("wallet", 0) < cost:
                return {"success": False, "message": f"Insufficient funds. Upgrade costs {cost} SC."}
            
            new_tier = business["tier"] + 1
            new_income = business["daily_income"] * 2
            new_upkeep = business["upkeep_cost"] * 2
            
            async with self.db.transaction():
                await self.player_queries.update_balance(user_id, wallet_delta=-cost)
                await self.business_queries.upgrade(business_id, new_tier, new_income, new_upkeep)
                
                await self.player_queries.add_transaction(
                    user_id, -cost, player.get("wallet", 0) - cost,
                    "business_upgrade", f"Upgraded {business['name']} to tier {new_tier}"
                )
            
            await self.event_bus.fire("business.upgraded", {
                "user_id": user_id,
                "business_id": business_id,
                "business_name": business["name"],
                "new_tier": new_tier,
                "cost": cost
            })
            
            return {
                "success": True,
                "message": f"Upgraded {business['name']} to tier {new_tier}! Cost: {cost} SC",
                "new_tier": new_tier,
                "cost": cost
            }
            
        except Exception as e:
            self.logger.error(f"Upgrade failed for {user_id}: {e}")
            raise
    
    async def collect_all_income(self) -> None:
        try:
            businesses = await self.business_queries.get_collectable_businesses()
            
            for business in businesses:
                try:
                    await self._auto_collect(business)
                except Exception as e:
                    self.logger.error(f"Auto collect failed for business {business['id']}: {e}")
            
            self.logger.info(f"Auto collected {len(businesses)} businesses")
            
        except Exception as e:
            self.logger.error(f"Collect all income failed: {e}")
            raise
    
    async def _auto_collect(self, business: Dict[str, Any]) -> None:
        try:
            last_collected = business["last_collected"]
            hours_passed = (datetime.now(timezone.utc) - last_collected).total_seconds() / 3600
            
            if hours_passed < 4:
                return
            
            base_income = business["daily_income"]
            tier_multiplier = business["tier"]
            efficiency = business["efficiency_override"] or 1.0
            
            income = int(base_income * tier_multiplier * efficiency * (hours_passed / 24))
            
            if income > 0:
                await self.player_queries.update_balance(business["discord_id"], wallet_delta=income)
                await self.business_queries.update_collected(business["id"])
                
        except Exception as e:
            self.logger.error(f"Auto collect failed: {e}")
            raise
    
    async def _has_item(self, user_id: int, item_id: str) -> bool:
        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT quantity FROM inventory
                    WHERE discord_id = $1 AND item_id = $2 AND quantity > 0
                """, user_id, item_id)
                
                return row is not None
                
        except Exception as e:
            self.logger.error(f"Has item check failed: {e}")
            return False
    
    async def _remove_item(self, user_id: int, item_id: str) -> None:
        try:
            async with self.db.acquire() as conn:
                await conn.execute("""
                    UPDATE inventory
                    SET quantity = quantity - 1
                    WHERE discord_id = $1 AND item_id = $2 AND quantity > 0
                """, user_id, item_id)
                
        except Exception as e:
            self.logger.error(f"Remove item failed: {e}")
            raise