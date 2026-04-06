from typing import Optional, List, Dict, Any
import asyncpg
from datetime import datetime, timezone, timedelta

from database.connection import DatabasePool


class PlayerQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def create(self, discord_id: int, username: str, referrer_id: Optional[int] = None) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    INSERT INTO players (discord_id, username, referrer_id)
                    VALUES ($1, $2, $3)
                    RETURNING *
                """, discord_id, username, referrer_id)
                return row
    
    async def get(self, discord_id: int) -> Optional[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM players WHERE discord_id = $1
            """, discord_id)
    
    async def update_balance(self, discord_id: int, wallet_delta: int = 0, bank_delta: int = 0) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE players
                    SET wallet = wallet + $2, bank = bank + $3
                    WHERE discord_id = $1
                    RETURNING wallet, bank, wallet + bank as total
                """, discord_id, wallet_delta, bank_delta)
                return row
    
    async def add_transaction(self, discord_id: int, amount: int, balance_after: int, tx_type: str, description: str = None, related_id: int = None) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO transactions (discord_id, amount, balance_after, tx_type, description, related_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, discord_id, amount, balance_after, tx_type, description, related_id)
    
    async def update_district(self, discord_id: int, district: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET district = $2 WHERE discord_id = $1
            """, discord_id, district)
    
    async def update_rep(self, discord_id: int, rep_delta: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE players
                    SET reputation = reputation + $2,
                        rep_rank = GREATEST(1, LEAST(10, FLOOR((reputation + $2) / 100) + 1))
                    WHERE discord_id = $1
                    RETURNING reputation, rep_rank
                """, discord_id, rep_delta)
                return row
    
    async def jail_player(self, discord_id: int, hours: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET is_jailed = TRUE, jail_until = NOW() + ($2 || ' hours')::INTERVAL, business_efficiency = 0.5
                WHERE discord_id = $1
            """, discord_id, hours)
    
    async def release_jail(self, discord_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET is_jailed = FALSE, jail_until = NULL, business_efficiency = 1.0
                WHERE discord_id = $1
            """, discord_id)
    
    async def update_premium(self, discord_id: int, tier: str, days: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET premium_tier = $2, premium_expires = NOW() + ($3 || ' days')::INTERVAL
                WHERE discord_id = $1
            """, discord_id, tier, days)
    
    async def increment_daily_stats(self, discord_id: int, earned: int, jobs: int = 0, gambled: int = 0) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET daily_earned = daily_earned + $2,
                    daily_jobs = daily_jobs + $3,
                    daily_gambled = daily_gambled + $4
                WHERE discord_id = $1
            """, discord_id, earned, jobs, gambled)
    
    async def update_story_flag(self, discord_id: int, flag_key: str, flag_value: Any) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET story_flags = jsonb_set(story_flags, ARRAY[$2], $3::jsonb)
                WHERE discord_id = $1
            """, discord_id, flag_key, json.dumps(flag_value))
    
    async def get_leaderboard(self, sort_by: str = "wallet", limit: int = 10) -> List[asyncpg.Record]:
        valid_sort = {"wallet", "bank", "reputation", "prestige", "total_earned"}
        if sort_by not in valid_sort:
            sort_by = "wallet"
        
        async with self.db.pool.acquire() as conn:
            return await conn.fetch(f"""
                SELECT discord_id, username, {sort_by}, rep_rank, prestige, premium_tier
                FROM players
                WHERE is_banned = FALSE
                ORDER BY {sort_by} DESC
                LIMIT $1
            """, limit)


class CooldownQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def set(self, discord_id: int, action: str, expires_at: datetime) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO cooldowns (discord_id, action, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (discord_id, action) DO UPDATE SET expires_at = EXCLUDED.expires_at
            """, discord_id, action, expires_at)
    
    async def get(self, discord_id: int, action: str) -> Optional[datetime]:
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT expires_at FROM cooldowns
                WHERE discord_id = $1 AND action = $2 AND expires_at > NOW()
            """, discord_id, action)
            return row["expires_at"] if row else None
    
    async def delete(self, discord_id: int, action: str) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM cooldowns WHERE discord_id = $1 AND action = $2
            """, discord_id, action)
    
    async def delete_all(self, discord_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM cooldowns WHERE discord_id = $1
            """, discord_id)
    
    async def cleanup_expired(self) -> int:
        async with self.db.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM cooldowns WHERE expires_at <= NOW()
            """)
            return int(result.split()[-1])


class JobQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def hire(self, discord_id: int, job_id: str) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO jobs_active (discord_id, job_id, hired_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (discord_id, job_id) DO NOTHING
            """, discord_id, job_id)
    
    async def quit(self, discord_id: int, job_id: str) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM jobs_active WHERE discord_id = $1 AND job_id = $2
            """, discord_id, job_id)
    
    async def update_last_worked(self, discord_id: int, job_id: str) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE jobs_active
                SET last_worked = NOW(), daily_work_count = daily_work_count + 1
                WHERE discord_id = $1 AND job_id = $2
            """, discord_id, job_id)
    
    async def update_passive_collected(self, discord_id: int, job_id: str) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE jobs_active
                SET last_passive_collected = NOW()
                WHERE discord_id = $1 AND job_id = $2
            """, discord_id, job_id)
    
    async def get_active_jobs(self, discord_id: int) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM jobs_active WHERE discord_id = $1
            """, discord_id)
    
    async def get_job_count(self, discord_id: int) -> int:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT COUNT(*) FROM jobs_active WHERE discord_id = $1
            """, discord_id)


class BusinessQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def create(self, discord_id: int, name: str, business_type: str, district: int, daily_income: int, upkeep_cost: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                INSERT INTO businesses (discord_id, name, business_type, district, daily_income, upkeep_cost)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
            """, discord_id, name, business_type, district, daily_income, upkeep_cost)
    
    async def get(self, business_id: int) -> Optional[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM businesses WHERE id = $1
            """, business_id)
    
    async def get_user_businesses(self, discord_id: int) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM businesses WHERE discord_id = $1 AND status = 'active'
                ORDER BY opened_at DESC
            """, discord_id)
    
    async def update_collected(self, business_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE businesses
                SET last_collected = NOW()
                WHERE id = $1
            """, business_id)
    
    async def update_restocked(self, business_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE businesses
                SET last_restocked = NOW(), stock_level = 100
                WHERE id = $1
            """, business_id)
    
    async def update_efficiency(self, business_id: int, multiplier: float) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE businesses
                SET efficiency_override = COALESCE(efficiency_override, 1.0) * $2
                WHERE id = $1
            """, business_id, multiplier)
    
    async def upgrade(self, business_id: int, new_tier: int, new_income: int, new_upkeep: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE businesses
                SET tier = $2, daily_income = $3, upkeep_cost = $4
                WHERE id = $1
            """, business_id, new_tier, new_income, new_upkeep)
    
    async def get_collectable_businesses(self) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id, discord_id, daily_income, tier, efficiency_override, last_collected
                FROM businesses
                WHERE status = 'active'
                  AND last_collected < NOW() - INTERVAL '4 hours'
            """)
    
    async def get_neglected_businesses(self) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id, discord_id, name, last_restocked
                FROM businesses
                WHERE status = 'active'
                  AND last_restocked < NOW() - INTERVAL '48 hours'
            """)
    
    async def mark_neglected(self, business_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE businesses
                SET status = 'neglected'
                WHERE id = $1
            """, business_id)


class FactionQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def create(self, name: str, tag: str, leader_id: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                faction = await conn.fetchrow("""
                    INSERT INTO factions (name, tag, leader_id)
                    VALUES ($1, $2, $3)
                    RETURNING *
                """, name, tag, leader_id)
                
                await conn.execute("""
                    INSERT INTO faction_members (faction_id, discord_id, role)
                    VALUES ($1, $2, 'leader')
                """, faction["id"], leader_id)
                
                return faction
    
    async def get(self, faction_id: int) -> Optional[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM factions WHERE id = $1 AND status = 'active'
            """, faction_id)
    
    async def get_by_name(self, name: str) -> Optional[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM factions WHERE name = $1 AND status = 'active'
            """, name)
    
    async def get_user_faction(self, discord_id: int) -> Optional[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT f.* FROM factions f
                JOIN faction_members fm ON fm.faction_id = f.id
                WHERE fm.discord_id = $1 AND f.status = 'active'
            """, discord_id)
    
    async def add_member(self, faction_id: int, discord_id: int, role: str = "member") -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO faction_members (faction_id, discord_id, role)
                VALUES ($1, $2, $3)
            """, faction_id, discord_id, role)
    
    async def remove_member(self, faction_id: int, discord_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM faction_members
                WHERE faction_id = $1 AND discord_id = $2
            """, faction_id, discord_id)
    
    async def get_members(self, faction_id: int) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT fm.*, p.username, p.reputation, p.prestige
                FROM faction_members fm
                JOIN players p ON p.discord_id = fm.discord_id
                WHERE fm.faction_id = $1
                ORDER BY fm.role DESC, p.reputation DESC
            """, faction_id)
    
    async def update_treasury(self, faction_id: int, delta: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE factions
                SET treasury = treasury + $2
                WHERE id = $1
            """, faction_id, delta)
    
    async def claim_district(self, faction_id: int, district: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO district_control (district, faction_id, controlled_since)
                VALUES ($2, $1, NOW())
                ON CONFLICT (district) DO UPDATE SET faction_id = $1, controlled_since = NOW(), contest_ends = NULL
            """, faction_id, district)
    
    async def start_turf_war(self, district: int, faction_id: int, hours: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE district_control
                SET contest_ends = NOW() + ($2 || ' hours')::INTERVAL
                WHERE district = $1 AND faction_id IS NULL
            """, district, hours)
    
    async def get_district_control(self) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT dc.*, f.name as faction_name, f.tag
                FROM district_control dc
                LEFT JOIN factions f ON f.id = dc.faction_id
                ORDER BY dc.district
            """)
    
    async def deduct_dues(self) -> None:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                factions = await conn.fetch("""
                    SELECT id, weekly_dues FROM factions WHERE status = 'active'
                """)
                
                for faction in factions:
                    members = await conn.fetch("""
                        SELECT discord_id FROM faction_members WHERE faction_id = $1
                    """, faction["id"])
                    
                    for member in members:
                        await conn.execute("""
                            UPDATE players
                            SET wallet = wallet - $2
                            WHERE discord_id = $1 AND wallet >= $2
                        """, member["discord_id"], faction["weekly_dues"])
                        
                        await conn.execute("""
                            UPDATE factions
                            SET treasury = treasury + $2
                            WHERE id = $1
                        """, faction["id"], faction["weekly_dues"])


class InvestmentQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def buy_shares(self, discord_id: int, company_id: str, shares: int, price: int) -> None:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO investments (discord_id, company_id, shares, avg_buy_price)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (discord_id, company_id) DO UPDATE
                    SET shares = investments.shares + EXCLUDED.shares,
                        avg_buy_price = ((investments.shares * investments.avg_buy_price) + (EXCLUDED.shares * EXCLUDED.avg_buy_price)) / (investments.shares + EXCLUDED.shares)
                """, discord_id, company_id, shares, price)
    
    async def sell_shares(self, discord_id: int, company_id: str, shares: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                investment = await conn.fetchrow("""
                    SELECT shares, avg_buy_price FROM investments
                    WHERE discord_id = $1 AND company_id = $2
                """, discord_id, company_id)
                
                if not investment or investment["shares"] < shares:
                    return None
                
                new_shares = investment["shares"] - shares
                
                if new_shares == 0:
                    await conn.execute("""
                        DELETE FROM investments
                        WHERE discord_id = $1 AND company_id = $2
                    """, discord_id, company_id)
                else:
                    await conn.execute("""
                        UPDATE investments
                        SET shares = $3
                        WHERE discord_id = $1 AND company_id = $2
                    """, discord_id, company_id, new_shares)
                
                return investment
    
    async def get_portfolio(self, discord_id: int) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT i.*, sp.price as current_price
                FROM investments i
                JOIN (
                    SELECT DISTINCT ON (company_id) company_id, price
                    FROM stock_prices
                    ORDER BY company_id, recorded_at DESC
                ) sp ON sp.company_id = i.company_id
                WHERE i.discord_id = $1
            """, discord_id)
    
    async def get_company_price(self, company_id: str) -> Optional[int]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT price FROM stock_prices
                WHERE company_id = $1
                ORDER BY recorded_at DESC
                LIMIT 1
            """, company_id)
    
    async def save_price(self, company_id: str, price: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO stock_prices (company_id, price, recorded_at)
                VALUES ($1, $2, NOW())
            """, company_id, price)
    
    async def update_sentiment(self, company_id: str, buy_volume: int, sell_volume: int) -> None:
        async with self.db.pool.acquire() as conn:
            period_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            
            await conn.execute("""
                INSERT INTO stock_sentiment (company_id, period_start, buy_volume, sell_volume, net_pressure)
                VALUES ($1, $2, $3, $4, $3 - $4)
                ON CONFLICT (company_id, period_start) DO UPDATE
                SET buy_volume = stock_sentiment.buy_volume + EXCLUDED.buy_volume,
                    sell_volume = stock_sentiment.sell_volume + EXCLUDED.sell_volume,
                    net_pressure = (stock_sentiment.buy_volume + EXCLUDED.buy_volume) - (stock_sentiment.sell_volume + EXCLUDED.sell_volume)
            """, company_id, period_start, buy_volume, sell_volume)


class InteractionQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def log(self, discord_id: int, guild_id: int, command: str, params: Dict, outcome: Dict) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO interaction_log (discord_id, guild_id, command, params, outcome)
                VALUES ($1, $2, $3, $4, $5)
            """, discord_id, guild_id, command, json.dumps(params), json.dumps(outcome))
    
    async def get_user_history(self, discord_id: int, limit: int = 50) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT command, params, outcome, created_at
                FROM interaction_log
                WHERE discord_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, discord_id, limit)
    
    async def cleanup_old(self) -> int:
        async with self.db.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM interaction_log
                WHERE created_at < NOW() - INTERVAL '30 days'
            """)
            return int(result.split()[-1])


class AINPCQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def add_memory(self, discord_id: int, npc_id: str, context_summary: str, ai_response: str) -> None:
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM ai_npc_memory
                    WHERE discord_id = $1 AND npc_id = $2
                """, discord_id, npc_id)
                
                await conn.execute("""
                    INSERT INTO ai_npc_memory (discord_id, npc_id, context_summary, ai_response)
                    VALUES ($1, $2, $3, $4)
                """, discord_id, npc_id, context_summary, ai_response)
                
                if count >= 20:
                    await conn.execute("""
                        DELETE FROM ai_npc_memory
                        WHERE id IN (
                            SELECT id FROM ai_npc_memory
                            WHERE discord_id = $1 AND npc_id = $2
                            ORDER BY created_at ASC
                            LIMIT 1
                        )
                    """, discord_id, npc_id)
    
    async def get_memories(self, discord_id: int, npc_id: str, limit: int = 10) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT context_summary, ai_response, created_at
                FROM ai_npc_memory
                WHERE discord_id = $1 AND npc_id = $2
                ORDER BY created_at DESC
                LIMIT $3
            """, discord_id, npc_id, limit)
    
    async def cache_response(self, cache_key: str, response: str, ttl_hours: int = 72) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ai_response_cache (cache_key, response, expires_at)
                VALUES ($1, $2, NOW() + ($3 || ' hours')::INTERVAL)
                ON CONFLICT (cache_key) DO UPDATE
                SET response = EXCLUDED.response, expires_at = EXCLUDED.expires_at, hit_count = ai_response_cache.hit_count
            """, cache_key, response, ttl_hours)
    
    async def get_cached_response(self, cache_key: str) -> Optional[str]:
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE ai_response_cache
                SET hit_count = hit_count + 1
                WHERE cache_key = $1 AND expires_at > NOW()
                RETURNING response
            """, cache_key)
            return row["response"] if row else None
    
    async def log_error(self, npc_id: str, error_type: str, error_message: str = None) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ai_error_log (npc_id, error_type, error_message)
                VALUES ($1, $2, $3)
            """, npc_id, error_type, error_message)
    
    async def cleanup_cache(self) -> int:
        async with self.db.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM ai_response_cache WHERE expires_at <= NOW()
            """)
            return int(result.split()[-1])
    
    async def cleanup_errors(self) -> int:
        async with self.db.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM ai_error_log WHERE created_at < NOW() - INTERVAL '7 days'
            """)
            return int(result.split()[-1])
            

class CrimeQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def log_crime(self, discord_id: int, crime_type: str, success: bool, loot: int, fine: int, jail_hours: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO crime_logs (discord_id, crime_type, success, loot, fine, jail_hours)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, discord_id, crime_type, success, loot, fine, jail_hours)
    
    async def get_crime_stats(self, discord_id: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful
                FROM crime_logs 
                WHERE discord_id = $1
            """, discord_id)


class HeistQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def create_heist(self, initiator_id: int, district: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                INSERT INTO heist_sessions (initiator_id, district, state, created_at)
                VALUES ($1, $2, 'pending', NOW())
                RETURNING id
            """, initiator_id, district)
    
    async def add_participant(self, heist_id: int, discord_id: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO heist_participants (heist_id, discord_id)
                VALUES ($1, $2)
            """, heist_id, discord_id)
    
    async def get_participants(self, heist_id: int) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT hp.discord_id, p.username
                FROM heist_participants hp
                JOIN players p ON p.discord_id = hp.discord_id
                WHERE hp.heist_id = $1
            """, heist_id)
    
    async def resolve_heist(self, heist_id: int, success: bool, loot: int) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE heist_sessions
                SET state = 'completed', success = $2, loot = $3, resolved_at = NOW()
                WHERE id = $1
            """, heist_id, success, loot)
    
    async def get_heist_stats(self, discord_id: int) -> asyncpg.Record:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT 
                    COUNT(*) as participated,
                    SUM(CASE WHEN hs.success = true THEN 1 ELSE 0 END) as successful
                FROM heist_participants hp
                JOIN heist_sessions hs ON hs.id = hp.heist_id
                WHERE hp.discord_id = $1
            """, discord_id)


class MarketQueries:
    
    def __init__(self, db: DatabasePool):
        self.db = db
    
    async def get_all_companies(self) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM companies ORDER BY id
            """)
    
    async def get_company(self, company_id: str) -> Optional[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM companies WHERE id = $1
            """, company_id)
    
    async def get_current_price(self, company_id: str) -> Optional[int]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT price FROM stock_prices
                WHERE company_id = $1
                ORDER BY recorded_at DESC
                LIMIT 1
            """, company_id)
    
    async def get_price_history(self, company_id: str, days: int = 7) -> List[asyncpg.Record]:
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT price, recorded_at
                FROM stock_prices
                WHERE company_id = $1 AND recorded_at > NOW() - ($2 || ' days')::INTERVAL
                ORDER BY recorded_at ASC
            """, company_id, days)
    
    async def add_news(self, headline: str, sector: str, modifier: float, direction: str) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO market_news (headline, sector, modifier, direction, generated_at, expires_at)
                VALUES ($1, $2, $3, $4, NOW(), NOW() + INTERVAL '24 hours')
            """, headline, sector, modifier, direction)