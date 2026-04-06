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

    async def start_heist(self, organizer_id: int, district: int) -> Dict[str, Any]:
        """Create a heist session."""
        try:
            player = await self.player_queries.get(organizer_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            if player.get("is_jailed", False):
                return {"success": False, "message": "You are in jail and cannot start a heist."}
            
            if player.get("reputation", 0) < 1000:
                return {"success": False, "message": "Requires 1000 reputation to start a heist."}
            
            active_heist = await self._get_active_heist(organizer_id)
            if active_heist:
                return {"success": False, "message": "You already have an active heist."}
            
            async with self.db.acquire() as conn:
                heist_id = await conn.fetchval("""
                    INSERT INTO heist_sessions (initiator_id, district, state, created_at)
                    VALUES ($1, $2, 'pending', NOW())
                    RETURNING id
                """, organizer_id, district)
            
            await self.event_bus.fire("heist.started", {
                "user_id": organizer_id,
                "district": district,
                "heist_id": heist_id
            })
            
            return {
                "success": True,
                "message": f"Heist planned in district {district}! Use /join_heist to recruit members. Lobby closes in {GameConstants.HEIST_LOBBY_SECONDS} seconds.",
                "heist_id": heist_id,
                "district": district,
                "join_window_seconds": GameConstants.HEIST_LOBBY_SECONDS,
                "initiator_username": player.get("username", "Unknown")
            }
            
        except Exception as e:
            self.logger.error(f"Start heist failed for {organizer_id}: {e}")
            raise

    async def join_heist(self, user_id: int, heist_id: int) -> Dict[str, Any]:
        """Join an existing heist."""
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            if player.get("is_jailed", False):
                return {"success": False, "message": "You are in jail and cannot join a heist."}
            
            async with self.db.acquire() as conn:
                heist = await conn.fetchrow("""
                    SELECT * FROM heist_sessions 
                    WHERE id = $1 AND state = 'pending'
                """, heist_id)
                
                if not heist:
                    return {"success": False, "message": "Heist not found or already started."}
                
                participants = await conn.fetchval("""
                    SELECT COUNT(*) FROM heist_participants WHERE heist_id = $1
                """, heist_id)
                
                if participants >= GameConstants.HEIST_MAX_PLAYERS:
                    return {"success": False, "message": f"Heist is full. Max {GameConstants.HEIST_MAX_PLAYERS} players."}
                
                already_joined = await conn.fetchval("""
                    SELECT 1 FROM heist_participants 
                    WHERE heist_id = $1 AND discord_id = $2
                """, heist_id, user_id)
                
                if already_joined:
                    return {"success": False, "message": "You already joined this heist."}
                
                await conn.execute("""
                    INSERT INTO heist_participants (heist_id, discord_id)
                    VALUES ($1, $2)
                """, heist_id, user_id)
            
            await self.event_bus.fire("heist.joined", {
                "user_id": user_id,
                "heist_id": heist_id,
                "username": player.get("username", "Unknown")
            })
            
            return {
                "success": True,
                "message": f"You joined the heist!",
                "heist_id": heist_id
            }
            
        except Exception as e:
            self.logger.error(f"Join heist failed for {user_id}: {e}")
            raise

    async def claim_bounty(self, claimer_id: int, target_id: int) -> Dict[str, Any]:
        """Claim a bounty on a jailed player."""
        try:
            claimer = await self.player_queries.get(claimer_id)
            target = await self.player_queries.get(target_id)
            
            if not claimer or not target:
                return {"success": False, "message": "Player not found."}
            
            if not target.get("is_jailed", False):
                return {"success": False, "message": "Target is not in jail."}
            
            async with self.db.acquire() as conn:
                bounty = await conn.fetchrow("""
                    SELECT id, amount FROM bounties
                    WHERE target_id = $1 AND status = 'active'
                    ORDER BY amount DESC
                    LIMIT 1
                """, target_id)
                
                if not bounty:
                    return {"success": False, "message": "No active bounties on this player."}
                
                async with conn.transaction():
                    await conn.execute("""
                        UPDATE bounties SET status = 'claimed', claimed_at = NOW(), claimed_by = $2
                        WHERE id = $1
                    """, bounty["id"], claimer_id)
                    
                    await self.player_queries.update_balance(claimer_id, wallet_delta=bounty["amount"])
                    
                    await self.player_queries.add_transaction(
                        claimer_id, bounty["amount"], claimer.get("wallet", 0) + bounty["amount"],
                        "bounty_claimed", f"Claimed bounty on {target_id}"
                    )
            
            await self.event_bus.fire("bounty.claimed", {
                "claimer_id": claimer_id,
                "target_id": target_id,
                "amount": bounty["amount"]
            })
            
            return {
                "success": True,
                "message": f"You claimed {bounty['amount']} SC bounty on {target.get('username', target_id)}!",
                "amount": bounty["amount"],
                "target_id": target_id
            }
            
        except Exception as e:
            self.logger.error(f"Claim bounty failed for {claimer_id}: {e}")
            raise

    async def _get_active_heist(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Check if user has an active heist."""
        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM heist_sessions
                    WHERE initiator_id = $1 AND state IN ('pending', 'active')
                    LIMIT 1
                """, user_id)
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Get active heist failed: {e}")
            return None

    async def resolve_heist(self, heist_id: int) -> Dict[str, Any]:
        """Resolve heist outcome (called by background task)."""
        try:
            async with self.db.acquire() as conn:
                heist = await conn.fetchrow("""
                    SELECT * FROM heist_sessions WHERE id = $1 AND state = 'pending'
                """, heist_id)
                
                if not heist:
                    return {"success": False, "message": "Heist not found or already resolved."}
                
                participants = await conn.fetch("""
                    SELECT hp.discord_id, p.username, p.reputation
                    FROM heist_participants hp
                    JOIN players p ON p.discord_id = hp.discord_id
                    WHERE hp.heist_id = $1
                """, heist_id)
                
                if len(participants) < GameConstants.HEIST_MIN_PLAYERS:
                    await conn.execute("""
                        UPDATE heist_sessions SET state = 'failed', resolved_at = NOW()
                        WHERE id = $1
                    """, heist_id)
                    return {"success": True, "succeeded": False, "message": "Not enough players."}
                
                total_rep = sum(p["reputation"] for p in participants)
                success_rate = self.crime_domain.calculate_heist_success(len(participants), heist["district"], total_rep)
                
                success = random.random() < success_rate
                
                if success:
                    loot = self.crime_domain.calculate_heist_loot(len(participants), heist["district"], total_rep)
                    per_player = loot // len(participants)
                    
                    for p in participants:
                        await self.player_queries.update_balance(p["discord_id"], wallet_delta=per_player)
                        await self.player_queries.add_transaction(
                            p["discord_id"], per_player, 0,
                            "heist_loot", f"Share from heist {heist_id}"
                        )
                    
                    await conn.execute("""
                        UPDATE heist_sessions 
                        SET state = 'completed', success = TRUE, loot = $2, resolved_at = NOW()
                        WHERE id = $1
                    """, heist_id, loot)
                    
                    await self.event_bus.fire("heist.completed", {
                        "heist_id": heist_id,
                        "participants": [p["discord_id"] for p in participants],
                        "loot": loot
                    })
                    
                    return {
                        "success": True,
                        "succeeded": True,
                        "total_loot": loot,
                        "participants": [{"discord_id": p["discord_id"], "username": p["username"], "share": per_player} for p in participants],
                        "narrative": f"The heist was a success! {loot} SC stolen!"
                    }
                else:
                    for p in participants:
                        await self.player_queries.jail_player(p["discord_id"], 4)
                    
                    await conn.execute("""
                        UPDATE heist_sessions SET state = 'failed', resolved_at = NOW()
                        WHERE id = $1
                    """, heist_id)
                    
                    await self.event_bus.fire("heist.failed", {
                        "heist_id": heist_id,
                        "participants": [p["discord_id"] for p in participants]
                    })
                    
                    return {
                        "success": True,
                        "succeeded": False,
                        "total_loot": 0,
                        "participants": [{"discord_id": p["discord_id"], "username": p["username"], "jailed": True} for p in participants],
                        "narrative": "The heist failed! Everyone was caught and jailed!"
                    }
                    
        except Exception as e:
            self.logger.error(f"Resolve heist failed for {heist_id}: {e}")
            raise