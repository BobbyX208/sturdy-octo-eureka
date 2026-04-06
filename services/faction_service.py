import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from database.connection import DatabasePool
from database.queries import FactionQueries, PlayerQueries
from core.cache import CacheManager
from events.bus import EventBus
from domain.premium import PremiumDomain
from config.settings import Config
from config.constants import GameConstants


class FactionService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.logger = logging.getLogger("simcoin.services.faction")
        
        self.faction_queries = FactionQueries(db)
        self.player_queries = PlayerQueries(db)
        
        self.premium_domain = PremiumDomain(Config.PREMIUM_TIERS)
    
    async def create_faction(self, user_id: int, name: str, tag: str) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            if player.get("reputation", 0) < GameConstants.FACTION_MIN_REP_TO_CREATE:
                return {"success": False, "message": f"Requires reputation {GameConstants.FACTION_MIN_REP_TO_CREATE}."}
            
            existing = await self.faction_queries.get_by_name(name)
            
            if existing:
                return {"success": False, "message": "Faction name already exists."}
            
            has_charter = await self._has_item(user_id, "faction_charter")
            
            if not has_charter:
                return {"success": False, "message": "You need a Faction Charter. Purchase from the market."}
            
            if player.get("wallet", 0) < GameConstants.FACTION_BASE_CREATION_COST:
                return {"success": False, "message": f"Insufficient funds. Creation costs {GameConstants.FACTION_BASE_CREATION_COST} SC."}
            
            async with self.db.transaction():
                await self.player_queries.update_balance(user_id, wallet_delta=-GameConstants.FACTION_BASE_CREATION_COST)
                await self._remove_item(user_id, "faction_charter")
                
                faction = await self.faction_queries.create(name, tag.upper(), user_id)
                
                await self.player_queries.add_transaction(
                    user_id, -GameConstants.FACTION_BASE_CREATION_COST, player.get("wallet", 0) - GameConstants.FACTION_BASE_CREATION_COST,
                    "faction_creation", f"Created faction {name}"
                )
            
            await self.event_bus.fire("faction.created", {
                "user_id": user_id,
                "faction_id": faction["id"],
                "faction_name": name,
                "tag": tag
            })
            
            return {
                "success": True,
                "message": f"Created faction {name} ({tag.upper()})!",
                "faction": dict(faction)
            }
            
        except Exception as e:
            self.logger.error(f"Create faction failed for {user_id}: {e}")
            raise
    
    async def invite_member(self, faction_id: int, inviter_id: int, target_id: int) -> Dict[str, Any]:
        try:
            faction = await self.faction_queries.get(faction_id)
            
            if not faction:
                return {"success": False, "message": "Faction not found."}
            
            member = await self.faction_queries.get_member(faction_id, inviter_id)
            
            if not member or member["role"] not in ["leader", "officer"]:
                return {"success": False, "message": "You don't have permission to invite members."}
            
            members = await self.faction_queries.get_members(faction_id)
            
            if len(members) >= GameConstants.FACTION_MAX_MEMBERS:
                return {"success": False, "message": f"Faction is full. Max {GameConstants.FACTION_MAX_MEMBERS} members."}
            
            target_faction = await self.faction_queries.get_user_faction(target_id)
            
            if target_faction:
                return {"success": False, "message": "That player is already in a faction."}
            
            await self.event_bus.fire("faction.invite_sent", {
                "faction_id": faction_id,
                "faction_name": faction["name"],
                "inviter_id": inviter_id,
                "target_id": target_id
            })
            
            return {
                "success": True,
                "message": f"Invited <@{target_id}> to {faction['name']}."
            }
            
        except Exception as e:
            self.logger.error(f"Invite member failed: {e}")
            raise
    
    async def accept_invite(self, user_id: int, faction_id: int) -> Dict[str, Any]:
        try:
            faction = await self.faction_queries.get(faction_id)
            
            if not faction:
                return {"success": False, "message": "Faction not found."}
            
            existing = await self.faction_queries.get_user_faction(user_id)
            
            if existing:
                return {"success": False, "message": "You are already in a faction."}
            
            members = await self.faction_queries.get_members(faction_id)
            
            if len(members) >= GameConstants.FACTION_MAX_MEMBERS:
                return {"success": False, "message": "Faction is full."}
            
            await self.faction_queries.add_member(faction_id, user_id, "member")
            
            await self.event_bus.fire("faction.joined", {
                "user_id": user_id,
                "faction_id": faction_id,
                "faction_name": faction["name"]
            })
            
            return {
                "success": True,
                "message": f"You have joined {faction['name']}!",
                "faction": dict(faction)
            }
            
        except Exception as e:
            self.logger.error(f"Accept invite failed: {e}")
            raise
    
    async def leave_faction(self, user_id: int) -> Dict[str, Any]:
        try:
            faction = await self.faction_queries.get_user_faction(user_id)
            
            if not faction:
                return {"success": False, "message": "You are not in a faction."}
            
            member = await self.faction_queries.get_member(faction["id"], user_id)
            
            if member["role"] == "leader":
                members = await self.faction_queries.get_members(faction["id"])
                
                if len(members) > 1:
                    return {"success": False, "message": "Transfer leadership before leaving."}
            
            await self.faction_queries.remove_member(faction["id"], user_id)
            
            await self.event_bus.fire("faction.left", {
                "user_id": user_id,
                "faction_id": faction["id"],
                "faction_name": faction["name"]
            })
            
            return {
                "success": True,
                "message": f"You have left {faction['name']}."
            }
            
        except Exception as e:
            self.logger.error(f"Leave faction failed: {e}")
            raise
    
    async def deposit_treasury(self, user_id: int, faction_id: int, amount: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            faction = await self.faction_queries.get(faction_id)
            
            if not faction:
                return {"success": False, "message": "Faction not found."}
            
            member = await self.faction_queries.get_member(faction_id, user_id)
            
            if not member:
                return {"success": False, "message": "You are not a member of this faction."}
            
            if player.get("wallet", 0) < amount:
                return {"success": False, "message": f"Insufficient funds. You have {player.get('wallet', 0)} SC."}
            
            async with self.db.transaction():
                await self.player_queries.update_balance(user_id, wallet_delta=-amount)
                await self.faction_queries.update_treasury(faction_id, amount)
                
                await self.player_queries.add_transaction(
                    user_id, -amount, player.get("wallet", 0) - amount,
                    "faction_deposit", f"Deposited {amount} to {faction['name']}"
                )
            
            await self.event_bus.fire("faction.deposit", {
                "user_id": user_id,
                "faction_id": faction_id,
                "faction_name": faction["name"],
                "amount": amount
            })
            
            return {
                "success": True,
                "message": f"Deposited {amount} SC to {faction['name']} treasury.",
                "new_treasury": faction.get("treasury", 0) + amount
            }
            
        except Exception as e:
            self.logger.error(f"Deposit treasury failed: {e}")
            raise
    
    async def claim_district(self, faction_id: int, user_id: int, district: int) -> Dict[str, Any]:
        try:
            faction = await self.faction_queries.get(faction_id)
            
            if not faction:
                return {"success": False, "message": "Faction not found."}
            
            member = await self.faction_queries.get_member(faction_id, user_id)
            
            if not member or member["role"] not in ["leader", "officer"]:
                return {"success": False, "message": "You don't have permission."}
            
            if faction.get("treasury", 0) < GameConstants.FACTION_CLAIM_COST:
                return {"success": False, "message": f"Insufficient treasury. Need {GameConstants.FACTION_CLAIM_COST} SC."}
            
            async with self.db.transaction():
                await self.faction_queries.update_treasury(faction_id, -GameConstants.FACTION_CLAIM_COST)
                await self.faction_queries.claim_district(faction_id, district)
            
            await self.event_bus.fire("faction.claimed_district", {
                "faction_id": faction_id,
                "faction_name": faction["name"],
                "district": district,
                "user_id": user_id
            })
            
            return {
                "success": True,
                "message": f"{faction['name']} has claimed District {district}!",
                "district": district
            }
            
        except Exception as e:
            self.logger.error(f"Claim district failed: {e}")
            raise
    
    async def get_faction_info(self, faction_id: int) -> Dict[str, Any]:
        try:
            faction = await self.faction_queries.get(faction_id)
            
            if not faction:
                return {"success": False, "message": "Faction not found."}
            
            members = await self.faction_queries.get_members(faction_id)
            district_control = await self.faction_queries.get_district_control()
            
            controlled_districts = [dc for dc in district_control if dc["faction_id"] == faction_id]
            
            return {
                "success": True,
                "faction": dict(faction),
                "members": members,
                "member_count": len(members),
                "controlled_districts": controlled_districts
            }
            
        except Exception as e:
            self.logger.error(f"Get faction info failed: {e}")
            raise
    
    async def get_district_control_map(self) -> List[Dict[str, Any]]:
        try:
            return await self.faction_queries.get_district_control()
            
        except Exception as e:
            self.logger.error(f"Get district control map failed: {e}")
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