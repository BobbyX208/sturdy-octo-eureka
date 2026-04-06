import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from datetime import datetime, timezone, timedelta
from database.connection import DatabasePool
from database.queries import PlayerQueries, CooldownQueries, AINPCQueries
from core.cache import CacheManager
from events.bus import EventBus
from domain.progression import ProgressionDomain
from domain.premium import PremiumDomain
from config.settings import Config
from config.constants import GameConstants


class PlayerService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.logger = logging.getLogger("simcoin.services.player")
        
        self.queries = PlayerQueries(db)
        self.cooldown_queries = CooldownQueries(db)
        self.ai_queries = AINPCQueries(db)
        
        self.progression = ProgressionDomain(Config.REP_RANKS) 
        self.premium = PremiumDomain(Config.PREMIUM_TIERS)
    
    async def get(self, discord_id: int) -> Optional[Dict[str, Any]]:
        try:
            cache_key = self.cache.generate_key("player", discord_id)
            cached = await self.cache.get(cache_key)
            
            if cached:
                return cached
            
            row = await self.queries.get(discord_id)
            
            if not row:
                return None
            
            player = dict(row)
            await self.cache.set(cache_key, player, ttl=300)
            
            return player
            
        except Exception as e:
            self.logger.error(f"Failed to get player {discord_id}: {e}")
            raise
    
    async def create(self, discord_id: int, username: str, referrer_id: Optional[int] = None) -> Dict[str, Any]:
        try:
            existing = await self.get(discord_id)
            
            if existing:
                return existing
            
            row = await self.queries.create(discord_id, username, referrer_id)
            
            await self.queries.update_balance(discord_id, wallet_delta=5000)
            
            player = dict(row)
            player["wallet"] = 5000
            
            cache_key = self.cache.generate_key("player", discord_id)
            await self.cache.set(cache_key, player, ttl=300)
            
            await self.event_bus.fire("player.created", {
                "user_id": discord_id,
                "username": username,
                "referrer_id": referrer_id
            })
            
            if referrer_id:
                await self._process_referral(referrer_id, discord_id)
            
            self.logger.info(f"Created player {username} ({discord_id})")
            
            return player
            
        except Exception as e:
            self.logger.error(f"Failed to create player {discord_id}: {e}")
            raise
    
    async def _process_referral(self, referrer_id: int, new_user_id: int) -> None:
        try:
            referrer = await self.get(referrer_id)
            
            if not referrer:
                return
            
            bonus = GameConstants.REFERRAL_BONUS
            
            await self.queries.update_balance(referrer_id, wallet_delta=bonus)
            await self.queries.add_transaction(
                referrer_id, bonus, referrer.get("wallet", 0) + bonus,
                "referral_bonus", f"Referred user {new_user_id}"
            )
            
            await self.queries.update_balance(new_user_id, wallet_delta=bonus)
            await self.queries.add_transaction(
                new_user_id, bonus, 0,
                "referral_bonus", f"Referred by {referrer_id}"
            )
            
            await self.event_bus.fire("referral.completed", {
                "referrer_id": referrer_id,
                "new_user_id": new_user_id,
                "bonus": bonus
            })
            
        except Exception as e:
            self.logger.error(f"Failed to process referral: {e}")
    
    async def update_balance(self, discord_id: int, wallet_delta: int = 0, bank_delta: int = 0) -> Dict[str, int]:
        try:
            row = await self.queries.update_balance(discord_id, wallet_delta, bank_delta)
            
            await self.cache.delete(self.cache.generate_key("player", discord_id))
            
            return {"wallet": row["wallet"], "bank": row["bank"], "total": row["total"]}
            
        except Exception as e:
            self.logger.error(f"Failed to update balance for {discord_id}: {e}")
            raise
    
    async def update_rep(self, discord_id: int, delta: int) -> Tuple[int, int, bool]:
        try:
            row = await self.queries.update_rep(discord_id, delta)
            
            old_rank = (await self.get(discord_id)).get("rep_rank", 1)
            new_rank = row["rep_rank"]
            
            rank_up = new_rank > old_rank
            
            await self.cache.delete(self.cache.generate_key("player", discord_id))
            
            if rank_up:
                await self.event_bus.fire("player.level_up", {
                    "user_id": discord_id,
                    "new_rank": new_rank,
                    "old_rank": old_rank,
                    "reputation": row["reputation"]
                })
            
            return row["reputation"], row["rep_rank"], rank_up
            
        except Exception as e:
            self.logger.error(f"Failed to update rep for {discord_id}: {e}")
            raise
    
    async def travel(self, discord_id: int, new_district: int) -> Tuple[bool, str]:
        try:
            player = await self.get(discord_id)
            
            if not player:
                return False, "Player not found"
            
            if player.get("is_jailed", False):
                return False, "You are in jail and cannot travel"
            
            unlocked_districts = self.progression.calculate_district_unlock(player.get("reputation", 0))
            
            if new_district not in unlocked_districts:
                return False, f"District {new_district} is locked. Reach higher reputation to unlock."
            
            old_district = player.get("district", 1)
            
            await self.queries.update_district(discord_id, new_district)
            await self.cache.delete(self.cache.generate_key("player", discord_id))
            
            await self.event_bus.fire("player.traveled", {
                "user_id": discord_id,
                "old_district": old_district,
                "new_district": new_district
            })
            
            if new_district not in player.get("story_flags", {}).get("visited_districts", []):
                await self.event_bus.fire("district.unlocked", {
                    "user_id": discord_id,
                    "district": new_district
                })
                
                story_flags = player.get("story_flags", {})
                visited = story_flags.get("visited_districts", [])
                visited.append(new_district)
                await self.queries.update_story_flag(discord_id, "visited_districts", visited)
            
            return True, f"Traveled to district {new_district}"
            
        except Exception as e:
            self.logger.error(f"Failed to travel for {discord_id}: {e}")
            raise
    
    async def prestige(self, discord_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        try:
            player = await self.get(discord_id)
            
            if not player:
                return False, "Player not found", None
            
            can_prestige, reason = self.progression.can_prestige(player)
            
            if not can_prestige:
                return False, reason, None
            
            reset_data = self.progression.calculate_prestige_reset(player)
            
            await self.queries.update_balance(discord_id, wallet_delta=-player.get("wallet", 0), bank_delta=-player.get("bank", 0))
            await self.queries.update_rep(discord_id, -player.get("reputation", 0))
            await self.cooldown_queries.delete_all(discord_id)
            
            await self.queries.update_balance(discord_id, wallet_delta=10000)
            
            await self.queries.add_transaction(
                discord_id, player.get("total_earned", 0), 10000,
                "prestige_reset", f"Prestige {reset_data['new_prestige']}"
            )
            
            await self.cache.delete(self.cache.generate_key("player", discord_id))
            
            await self.event_bus.fire("player.prestige", {
                "user_id": discord_id,
                "prestige_level": reset_data["new_prestige"],
                "old_prestige": player.get("prestige", 0)
            })
            
            return True, f"You have prestiged to level {reset_data['new_prestige']}!", reset_data
            
        except Exception as e:
            self.logger.error(f"Failed to prestige for {discord_id}: {e}")
            raise
    
    async def get_leaderboard(self, sort_by: str = "wallet", limit: int = 10) -> list:
        try:
            return await self.queries.get_leaderboard(sort_by, limit)
            
        except Exception as e:
            self.logger.error(f"Failed to get leaderboard: {e}")
            raise
    
    async def get_district_info(self, district_id: int) -> Dict[str, Any]:
        try:
            districts = {
                1: {"name": "Slums", "description": "The forgotten quarter. Crime runs deep here.", "npc": "Ray"},
                2: {"name": "Industrial", "description": "Factories and warehouses. Marco runs a tight ship.", "npc": "Marco"},
                3: {"name": "Downtown", "description": "The heart of the city. Ms. Chen watches everything.", "npc": "Ms. Chen"},
                4: {"name": "Financial District", "description": "Where fortunes are made and lost. The Broker holds court.", "npc": "The Broker"},
                5: {"name": "The Strip", "description": "Neon lights and high stakes. Lucky Lou owns the night.", "npc": "Lucky Lou"},
                6: {"name": "Underground", "description": "The city beneath. Ghost moves in shadows.", "npc": "Ghost"}
            }
            
            return districts.get(district_id, {"name": "Unknown", "description": "Unknown district"})
            
        except Exception as e:
            self.logger.error(f"Failed to get district info: {e}")
            raise

    async def get_streak(self, discord_id: int) -> dict:
        """Get player's daily streak information."""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT daily_streak, last_daily FROM players WHERE discord_id = $1",
                    discord_id
                )
                
                if not row:
                    return {"streak_days": 0, "last_claimed": None}
                
                streak_days = row["daily_streak"] or 0
                last_daily = row["last_daily"]
                
                if last_daily:
                    days_since = (datetime.now(timezone.utc) - last_daily).days
                    if days_since > 1:
                        streak_days = 0
                
                return {
                    "streak_days": streak_days,
                    "last_claimed": last_daily
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get streak: {e}")
            return {"streak_days": 0, "last_claimed": None}


    async def get_active_bounties(self, discord_id: int) -> list:
        """Get active bounties placed on a player."""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT id, poster_id, amount, created_at 
                    FROM bounties 
                    WHERE target_id = $1 AND status = 'active'
                    ORDER BY amount DESC""",
                    discord_id
                )
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Failed to get active bounties: {e}")
            return []


    async def get_crime_stats(self, discord_id: int) -> dict:
        """Get player's crime statistics."""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful
                    FROM crime_logs 
                    WHERE discord_id = $1""",
                    discord_id
                )
                
                if not row:
                    return {"total": 0, "successful": 0}
                
                return {
                    "total": row["total"] or 0,
                    "successful": row["successful"] or 0
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get crime stats: {e}")
            return {"total": 0, "successful": 0}


    async def get_heist_stats(self, discord_id: int) -> dict:
        """Get player's heist statistics."""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT 
                        COUNT(*) as participated,
                        SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful
                    FROM heist_participants 
                    WHERE discord_id = $1""",
                    discord_id
                )
                
                if not row:
                    return {"participated": 0, "successful": 0}
                
                return {
                    "participated": row["participated"] or 0,
                    "successful": row["successful"] or 0
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get heist stats: {e}")
            return {"participated": 0, "successful": 0}


    async def get_business_stats(self, discord_id: int) -> dict:
        """Get player's business statistics."""
        try:
            async with self.db.pool.acquire() as conn:
                owned = await conn.fetchval(
                    "SELECT COUNT(*) FROM businesses WHERE discord_id = $1",
                    discord_id
                )
                
                trades = await conn.fetchval(
                    "SELECT COUNT(*) FROM transactions WHERE discord_id = $1 AND tx_type = 'stock_trade'",
                    discord_id
                )
                
                return {
                    "owned": owned or 0,
                    "trades": trades or 0
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get business stats: {e}")
            return {"owned": 0, "trades": 0}


    async def update_district(self, discord_id: int, district: int) -> None:
        """Update player's current district."""
        try:
            await self.queries.update_district(discord_id, district)
            await self.cache.delete(self.cache.generate_key("player", discord_id))
        except Exception as e:
            self.logger.error(f"Failed to update district for {discord_id}: {e}")
            raise


    async def update_story_flags(self, discord_id: int, story_flags: dict) -> None:
        """Update player's story flags."""
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE players SET story_flags = $2 WHERE discord_id = $1",
                    discord_id, story_flags
                )
            await self.cache.delete(self.cache.generate_key("player", discord_id))
        except Exception as e:
            self.logger.error(f"Failed to update story flags for {discord_id}: {e}")
            raise


    async def set_cooldown(self, discord_id: int, action: str, seconds: int) -> None:
        """Set a cooldown for a player action."""
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            async with self.db.pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO cooldowns (discord_id, action, expires_at) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT (discord_id, action) 
                    DO UPDATE SET expires_at = EXCLUDED.expires_at""",
                    discord_id, action, expires_at
                )
        except Exception as e:
            self.logger.error(f"Failed to set cooldown for {discord_id}: {e}")


    async def check_cooldown(self, discord_id: int, action: str) -> int:
        """Check remaining cooldown seconds for a player action."""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT expires_at FROM cooldowns WHERE discord_id = $1 AND action = $2",
                    discord_id, action
                )
                
                if not row or not row["expires_at"]:
                    return 0
                
                remaining = (row["expires_at"] - datetime.now(timezone.utc)).total_seconds()
                return max(0, int(remaining))
                
        except Exception as e:
            self.logger.error(f"Failed to check cooldown for {discord_id}: {e}")
            return 0


    async def transfer_sc(self, from_id: int, to_id: int, amount: int) -> None:
        """Transfer SC from one player to another."""
        try:
            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE players SET wallet = wallet - $2 WHERE discord_id = $1",
                        from_id, amount
                    )
                    await conn.execute(
                        "UPDATE players SET wallet = wallet + $2 WHERE discord_id = $1",
                        to_id, amount
                    )
                    
                    await conn.execute(
                        """INSERT INTO transactions (discord_id, amount, balance_after, tx_type, description) 
                        VALUES ($1, -$2, (SELECT wallet FROM players WHERE discord_id = $1), 'transfer', $3)""",
                        from_id, amount, f"Sent to {to_id}"
                    )
                    
                    await conn.execute(
                        """INSERT INTO transactions (discord_id, amount, balance_after, tx_type, description) 
                        VALUES ($1, $2, (SELECT wallet FROM players WHERE discord_id = $1), 'transfer', $3)""",
                        to_id, amount, f"Received from {from_id}"
                    )
            
            await self.cache.delete(self.cache.generate_key("player", from_id))
            await self.cache.delete(self.cache.generate_key("player", to_id))
            
        except Exception as e:
            self.logger.error(f"Failed to transfer SC from {from_id} to {to_id}: {e}")
            raise


    async def prestige_reset(self, discord_id: int, new_prestige: int) -> None:
        """Reset player for prestige."""
        try:
            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """UPDATE players 
                        SET wallet = 5000, 
                            bank = 0, 
                            reputation = 0, 
                            rep_rank = 1,
                            prestige = $2,
                            total_earned = 0
                        WHERE discord_id = $1""",
                        discord_id, new_prestige
                    )
                    
                    await conn.execute(
                        "DELETE FROM businesses WHERE discord_id = $1",
                        discord_id
                    )
                    
                    await conn.execute(
                        "DELETE FROM investments WHERE discord_id = $1",
                        discord_id
                    )
                    
                    await conn.execute(
                        "DELETE FROM cooldowns WHERE discord_id = $1",
                        discord_id
                    )
            
            await self.cache.delete(self.cache.generate_key("player", discord_id))
            
        except Exception as e:
            self.logger.error(f"Failed to prestige reset for {discord_id}: {e}")
            raise


    async def get_leaderboard_snapshot(self, weeks_ago: int = 1) -> dict:
        """Get leaderboard snapshot from X weeks ago."""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT discord_id, rank, net_worth 
                    FROM leaderboard_snapshots 
                    WHERE snapshot_date >= NOW() - INTERVAL '1 week' * $1
                    ORDER BY snapshot_date DESC LIMIT 100""",
                    weeks_ago
                )
                
                result = {}
                for row in rows:
                    result[row["discord_id"]] = {
                        "rank": row["rank"],
                        "net_worth": row["net_worth"]
                    }
                
                return result
                
        except Exception as e:
            self.logger.error(f"Failed to get leaderboard snapshot: {e}")
            return {}


    async def get_rank(self, discord_id: int, leaderboard_type: str) -> int:
        """Get player's rank on a specific leaderboard."""
        try:
            async with self.db.pool.acquire() as conn:
                if leaderboard_type == "wealth":
                    row = await conn.fetchrow(
                        """SELECT COUNT(*) + 1 as rank 
                        FROM players 
                        WHERE (wallet + bank) > (
                            SELECT wallet + bank FROM players WHERE discord_id = $1
                        )""",
                        discord_id
                    )
                elif leaderboard_type == "reputation":
                    row = await conn.fetchrow(
                        """SELECT COUNT(*) + 1 as rank 
                        FROM players 
                        WHERE reputation > (
                            SELECT reputation FROM players WHERE discord_id = $1
                        )""",
                        discord_id
                    )
                elif leaderboard_type == "prestige":
                    row = await conn.fetchrow(
                        """SELECT COUNT(*) + 1 as rank 
                        FROM players 
                        WHERE prestige > (
                            SELECT prestige FROM players WHERE discord_id = $1
                        )""",
                        discord_id
                    )
                else:
                    return 0
                
                return row["rank"] if row else 0
                
        except Exception as e:
            self.logger.error(f"Failed to get rank: {e}")
            return 0


    async def get_leaderboard(self, leaderboard_type: str, limit: int = 10) -> list:
        """Get top players for a specific leaderboard type."""
        try:
            async with self.db.pool.acquire() as conn:
                if leaderboard_type == "wealth":
                    rows = await conn.fetch(
                        """SELECT discord_id, username, wallet, bank 
                        FROM players 
                        ORDER BY (wallet + bank) DESC 
                        LIMIT $1""",
                        limit
                    )
                    return [dict(row) for row in rows]
                    
                elif leaderboard_type == "reputation":
                    rows = await conn.fetch(
                        """SELECT discord_id, username, reputation 
                        FROM players 
                        ORDER BY reputation DESC 
                        LIMIT $1""",
                        limit
                    )
                    return [dict(row) for row in rows]
                    
                elif leaderboard_type == "businesses":
                    rows = await conn.fetch(
                        """SELECT p.discord_id, p.username, COUNT(b.id) as business_count
                        FROM players p
                        LEFT JOIN businesses b ON p.discord_id = b.discord_id
                        GROUP BY p.discord_id, p.username
                        ORDER BY business_count DESC
                        LIMIT $1""",
                        limit
                    )
                    return [dict(row) for row in rows]
                    
                elif leaderboard_type == "prestige":
                    rows = await conn.fetch(
                        """SELECT discord_id, username, prestige 
                        FROM players 
                        ORDER BY prestige DESC 
                        LIMIT $1""",
                        limit
                    )
                    return [dict(row) for row in rows]
                    
                else:
                    return []
                    
        except Exception as e:
            self.logger.error(f"Failed to get leaderboard: {e}")
            return []