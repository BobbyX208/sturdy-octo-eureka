import logging
import random
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone, timedelta

from database.connection import DatabasePool
from database.queries import PlayerQueries, CooldownQueries
from core.cache import CacheManager
from core.cooldowns import CooldownManager
from events.bus import EventBus
from domain.crimes import CrimeDomain
from config.settings import Config
from config.constants import GameConstants


class CrimeService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus, cooldowns: CooldownManager):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.cooldowns = cooldowns
        self.logger = logging.getLogger("simcoin.services.crime")
        
        self.player_queries = PlayerQueries(db)
        
        self.crime_domain = CrimeDomain(GameConstants.CRIME_TYPES)
    
    async def commit_crime(self, user_id: int, crime_type: str, target_id: Optional[int] = None) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found. Use /start first."}
            
            can_commit, reason = self.crime_domain.can_commit_crime(player, crime_type)
            
            if not can_commit:
                return {"success": False, "message": reason}
            
            cooldown_active = await self.cooldowns.is_active(user_id, "crime")
            
            if cooldown_active:
                remaining = await self.cooldowns.get_remaining(user_id, "crime")
                return {"success": False, "message": f"Crime cooldown active. Try again in {remaining} seconds."}
            
            district = player.get("district", 1)
            
            success, loot, fine, jail_hours = self.crime_domain.calculate_success(player, crime_type, district)
            
            rep_loss = self.crime_domain.calculate_rep_loss(player, crime_type, success)
            heat_gain = self.crime_domain.calculate_heat_gain(crime_type, success)
            
            result = {
                "success": success,
                "crime_type": crime_type,
                "loot": 0,
                "fine": 0,
                "jailed": False,
                "jail_hours": 0,
                "rep_loss": rep_loss
            }
            
            if success:
                result["loot"] = loot
                await self.player_queries.update_balance(user_id, wallet_delta=loot)
                await self.player_queries.add_transaction(
                    user_id, loot, player.get("wallet", 0) + loot,
                    "crime_success", f"Successful {crime_type}"
                )
                
                if target_id:
                    target = await self.player_queries.get(target_id)
                    if target:
                        stolen = min(loot, target.get("wallet", 0))
                        await self.player_queries.update_balance(target_id, wallet_delta=-stolen)
                        await self.event_bus.fire("player.robbed", {
                            "victim_id": target_id,
                            "perpetrator_id": user_id,
                            "amount": stolen
                        })
            else:
                result["fine"] = fine
                await self.player_queries.update_balance(user_id, wallet_delta=-fine)
                await self.player_queries.add_transaction(
                    user_id, -fine, player.get("wallet", 0) - fine,
                    "crime_failure", f"Failed {crime_type}"
                )
                
                if jail_hours > 0:
                    result["jailed"] = True
                    result["jail_hours"] = jail_hours
                    await self.player_queries.jail_player(user_id, jail_hours)
                    await self.event_bus.fire("crime.jailed", {
                        "user_id": user_id,
                        "crime_type": crime_type,
                        "hours": jail_hours
                    })
            
            await self.player_queries.update_rep(user_id, -rep_loss)
            
            new_heat = player.get("heat_level", 0) + heat_gain
            await self._update_heat(user_id, new_heat)
            
            await self.cooldowns.set(user_id, "crime", Config.CRIME_COOLDOWN)
            
            await self.event_bus.fire("crime.committed" if success else "crime.failed", {
                "user_id": user_id,
                "crime_type": crime_type,
                "success": success,
                "loot": loot if success else 0,
                "fine": fine if not success else 0,
                "jailed": jail_hours > 0 if not success else False
            })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Crime failed for {user_id}: {e}")
            raise
    
    async def _update_heat(self, user_id: int, new_heat: int) -> None:
        try:
            async with self.db.acquire() as conn:
                await conn.execute("""
                    UPDATE players SET heat_level = $2 WHERE discord_id = $1
                """, user_id, min(new_heat, 100))
        except Exception as e:
            self.logger.error(f"Failed to update heat: {e}")
    
    async def get_wanted_status(self, user_id: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"exists": False}
            
            return {
                "exists": True,
                "heat_level": player.get("heat_level", 0),
                "is_jailed": player.get("is_jailed", False),
                "jail_until": player.get("jail_until"),
                "bounties": await self._get_active_bounties(user_id)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get wanted status: {e}")
            raise
    
    async def _get_active_bounties(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT poster_id, amount, created_at
                    FROM bounties
                    WHERE target_id = $1 AND status = 'active'
                """, user_id)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Failed to get bounties: {e}")
            return []
    
    async def place_bounty(self, poster_id: int, target_id: int, amount: int) -> Dict[str, Any]:
        try:
            poster = await self.player_queries.get(poster_id)
            target = await self.player_queries.get(target_id)
            
            if not poster or not target:
                return {"success": False, "message": "Player not found"}
            
            if poster_id == target_id:
                return {"success": False, "message": "You cannot place a bounty on yourself"}
            
            if poster.get("wallet", 0) < amount:
                return {"success": False, "message": f"Insufficient funds. You have {poster.get('wallet', 0)} SC"}
            
            async with self.db.transaction():
                await self.player_queries.update_balance(poster_id, wallet_delta=-amount)
                
                await self.player_queries.add_transaction(
                    poster_id, -amount, poster.get("wallet", 0) - amount,
                    "bounty_placed", f"Placed {amount} SC bounty on {target_id}"
                )
                
                async with self.db.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO bounties (poster_id, target_id, amount)
                        VALUES ($1, $2, $3)
                    """, poster_id, target_id, amount)
            
            await self.event_bus.fire("bounty.placed", {
                "poster_id": poster_id,
                "target_id": target_id,
                "amount": amount
            })
            
            return {
                "success": True,
                "message": f"Placed {amount} SC bounty on {target.get('username', target_id)}",
                "amount": amount,
                "target_id": target_id
            }
            
        except Exception as e:
            self.logger.error(f"Failed to place bounty: {e}")
            raise