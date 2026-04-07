import logging
import discord
from typing import Optional
from datetime import datetime, timezone

from services import ServiceContainer
from database.connection import DatabasePool
from core.cache import CacheManager


class SimContext:

    def __init__(self, services: ServiceContainer, db: DatabasePool, cache: CacheManager):
        self.services = services
        self.db = db
        self.cache = cache
        self.logger = logging.getLogger("simcoin.middleware")

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────

    def _ok(self, data=None, message: str = None) -> dict:
        return {"success": True, "data": data, "message": message}

    def _err(self, message: str) -> dict:
        return {"success": False, "data": None, "message": message}

    # ─────────────────────────────────────────────────────────────
    # PLAYER MODULE
    # ─────────────────────────────────────────────────────────────

    async def get_player(self, discord_id: int) -> dict:
        """
        Full player profile in ONE query.
        Includes: faction name/role, business count, active bounty total, streak.

        Returns:
            {
                discord_id, username, wallet, bank, net_worth,
                reputation, rep_rank, district, premium_tier, prestige,
                is_jailed, jail_until, heat_level, streak_days,
                total_earned, total_spent, system_role,
                faction_name, faction_role, business_count,
                active_bounty_total, created_at
            }
        """
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        p.discord_id, p.username, p.wallet, p.bank,
                        p.wallet + p.bank AS net_worth,
                        p.reputation, p.rep_rank, p.district,
                        p.premium_tier, p.prestige, p.is_jailed,
                        p.jail_until, p.heat_level, p.daily_streak AS streak_days,
                        p.total_earned, p.system_role, p.created_at,
                        p.is_banned, p.premium_expires,
                        f.name AS faction_name,
                        fm.role AS faction_role,
                        COUNT(DISTINCT b.id) AS business_count,
                        COALESCE(SUM(bo.amount) FILTER (WHERE bo.status = 'active'), 0) AS active_bounty_total
                    FROM players p
                    LEFT JOIN faction_members fm ON fm.discord_id = p.discord_id
                    LEFT JOIN factions f ON f.id = fm.faction_id AND f.status = 'active'
                    LEFT JOIN businesses b ON b.discord_id = p.discord_id AND b.status = 'active'
                    LEFT JOIN bounties bo ON bo.target_id = p.discord_id
                    WHERE p.discord_id = $1
                    GROUP BY p.discord_id, f.name, fm.role
                """, discord_id)

            if not row:
                return self._err("Player not found. Use `/start` to begin.")

            return self._ok(dict(row))

        except Exception as e:
            self.logger.error(f"get_player failed for {discord_id}: {e}")
            return self._err("Something went wrong fetching your profile.")

    async def register_player(self, discord_id: int, username: str, referrer_id: Optional[int] = None) -> dict:
        """
        Register a new player. Grants 5,000 SC starting balance.
        Idempotent — returns existing player if already registered.
        """
        try:
            result = await self.services.player.create(discord_id, username, referrer_id)
            if not result["success"]:
                return self._err(result["message"])
            return await self.get_player(discord_id)
        except Exception as e:
            self.logger.error(f"register_player failed for {discord_id}: {e}")
            return self._err("Failed to register. Please try again.")

    async def get_player_stats(self, discord_id: int) -> dict:
        """
        Lifetime stats for /stats command. Single aggregated query.

        Returns all get_player fields plus:
            crimes_total, crimes_successful, crimes_failed,
            heists_participated, heists_successful,
            businesses_owned, stocks_traded, items_owned
        """
        try:
            player_result = await self.get_player(discord_id)
            if not player_result["success"]:
                return player_result

            async with self.db.pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT
                        COUNT(cl.id) AS crimes_total,
                        COUNT(cl.id) FILTER (WHERE cl.succeeded) AS crimes_successful,
                        COUNT(cl.id) FILTER (WHERE NOT cl.succeeded) AS crimes_failed,
                        COUNT(DISTINCT hp.heist_id) AS heists_participated,
                        COUNT(DISTINCT hp.heist_id) FILTER (WHERE hs.state = 'completed' AND hs.success = TRUE) AS heists_successful,
                        COUNT(DISTINCT biz.id) AS businesses_owned,
                        COUNT(DISTINCT inv_log.id) AS stocks_traded,
                        COALESCE(SUM(i.quantity), 0) AS items_owned
                    FROM players p
                    LEFT JOIN crime_logs cl ON cl.discord_id = p.discord_id
                    LEFT JOIN heist_participants hp ON hp.discord_id = p.discord_id
                    LEFT JOIN heist_sessions hs ON hs.id = hp.heist_id
                    LEFT JOIN businesses biz ON biz.discord_id = p.discord_id AND biz.status = 'active'
                    LEFT JOIN investments inv_log ON inv_log.discord_id = p.discord_id
                    LEFT JOIN inventory i ON i.discord_id = p.discord_id
                    WHERE p.discord_id = $1
                    GROUP BY p.discord_id
                """, discord_id)

            data = player_result["data"]
            if stats:
                data.update(dict(stats))
            else:
                data.update({
                    "crimes_total": 0, "crimes_successful": 0, "crimes_failed": 0,
                    "heists_participated": 0, "heists_successful": 0,
                    "businesses_owned": 0, "stocks_traded": 0, "items_owned": 0
                })

            return self._ok(data)

        except Exception as e:
            self.logger.error(f"get_player_stats failed for {discord_id}: {e}")
            return self._err("Failed to load stats.")

    async def get_leaderboard(self, board_type: str, limit: int = 10) -> dict:
        """
        Top players with rank movement vs last week.
        board_type: 'wealth' | 'reputation' | 'businesses' | 'prestige'

        Returns:
            data: list of { rank, discord_id, username, value, rank_delta, premium_tier, prestige }
            player_rank: calling user's rank (pass discord_id as kwarg or use get_player_rank)
        """
        try:
            leaders = await self.services.player.get_leaderboard(board_type, limit)
            return self._ok(leaders)
        except Exception as e:
            self.logger.error(f"get_leaderboard failed: {e}")
            return self._err("Failed to load leaderboard.")

    async def get_player_rank(self, discord_id: int, board_type: str) -> dict:
        """Returns player's rank position on a leaderboard. 0 if unranked."""
        try:
            rank = await self.services.player.get_rank(discord_id, board_type)
            return self._ok({"rank": rank})
        except Exception as e:
            self.logger.error(f"get_player_rank failed: {e}")
            return self._ok({"rank": 0})

    # ─────────────────────────────────────────────────────────────
    # ECONOMY MODULE
    # ─────────────────────────────────────────────────────────────

    async def work(self, discord_id: int, job_id: str) -> dict:
        """
        Execute a work action. Handles cooldown, validates job, applies premium multiplier.

        Returns:
            { reward, job_id, new_wallet, cooldown_seconds, daily_work_count }
        """
        try:
            result = await self.services.economy.work(discord_id, job_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"work failed for {discord_id}: {e}")
            return self._err("Work failed. Please try again.")

    async def daily(self, discord_id: int) -> dict:
        """
        Claim daily reward. Calculates streak, penalty, premium bonus atomically.

        Returns:
            { reward, streak, streak_bonus, penalty_applied, new_wallet, next_available }
        """
        try:
            result = await self.services.economy.daily(discord_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"daily failed for {discord_id}: {e}")
            return self._err("Daily claim failed. Please try again.")

    async def bank(self, discord_id: int, action: str, amount: int) -> dict:
        """
        Bank deposit or withdrawal. Applies tier-based fee.
        action: 'deposit' | 'withdraw'

        Returns:
            { action, amount, fee, amount_after_fee, new_wallet, new_bank }
        """
        try:
            result = await self.services.economy.bank_transaction(discord_id, action, amount)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"bank failed for {discord_id}: {e}")
            return self._err("Bank transaction failed. Please try again.")

    async def transfer(self, sender_id: int, receiver_id: int, amount: int) -> dict:
        """
        Transfer SC between players. Applies transfer fee.

        Returns:
            { amount_sent, fee, receiver_username, new_sender_wallet }
        """
        try:
            result = await self.services.economy.transfer(sender_id, receiver_id, amount)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"transfer failed: {e}")
            return self._err("Transfer failed. Please try again.")

    async def get_jobs(self, discord_id: int) -> dict:
        """
        Returns active jobs + all available jobs with eligibility in one query.

        Returns:
            { active: [...], available: [...] }
        """
        try:
            async with self.db.pool.acquire() as conn:
                active = await conn.fetch("""
                    SELECT job_id, hired_at, last_worked, daily_work_count
                    FROM jobs_active WHERE discord_id = $1
                """, discord_id)

            return self._ok({
                "active": [dict(r) for r in active],
            })
        except Exception as e:
            self.logger.error(f"get_jobs failed for {discord_id}: {e}")
            return self._err("Failed to load jobs.")

    async def apply_for_job(self, discord_id: int, job_id: str) -> dict:
        """Apply for a job. Validates rep and max job limit."""
        try:
            result = await self.services.economy.apply_job(discord_id, job_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"apply_for_job failed: {e}")
            return self._err("Failed to apply for job.")

    async def quit_job(self, discord_id: int, job_id: str) -> dict:
        """Quit a job."""
        try:
            result = await self.services.economy.quit_job(discord_id, job_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"quit_job failed: {e}")
            return self._err("Failed to quit job.")

    # ─────────────────────────────────────────────────────────────
    # CRIME MODULE
    # ─────────────────────────────────────────────────────────────

    async def commit_crime(self, discord_id: int, crime_type: str) -> dict:
        """
        Execute a crime attempt. Handles RNG, heat, jail chance, cooldown atomically.

        Returns:
            { crime_type, succeeded, reward, heat_change, new_heat,
              jailed, jail_hours, rep_change, new_wallet, narrative }
        """
        try:
            result = await self.services.crime.commit_crime(discord_id, crime_type)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"commit_crime failed for {discord_id}: {e}")
            return self._err("Crime attempt failed. Try again.")

    async def start_heist(self, organizer_id: int, district: int) -> dict:
        """
        Create a heist session. Returns heist_id and join window info.

        Returns:
            { heist_id, district, join_window_seconds, initiator_username }
        """
        try:
            result = await self.services.crime.start_heist(organizer_id, district)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"start_heist failed: {e}")
            return self._err("Failed to start heist.")

    async def join_heist(self, discord_id: int, heist_id: int) -> dict:
        """Join an active heist session."""
        try:
            result = await self.services.crime.join_heist(discord_id, heist_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"join_heist failed: {e}")
            return self._err("Failed to join heist.")

    async def get_active_heist(self, discord_id: int) -> dict:
        """Returns heist the player is currently part of, or None."""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM heist_sessions
                    WHERE initiator_id = $1 AND state IN ('pending', 'active')
                    ORDER BY created_at DESC LIMIT 1
                """, discord_id)
            return self._ok(dict(row) if row else None)
        except Exception as e:
            self.logger.error(f"get_active_heist failed: {e}")
            return self._ok(None)

    async def place_bounty(self, placer_id: int, target_id: int, amount: int, reason: str = None) -> dict:
        """
        Place a bounty on a player. Locks amount from placer wallet.

        Returns:
            { bounty_id, target_username, amount, new_wallet }
        """
        try:
            result = await self.services.crime.place_bounty(placer_id, target_id, amount)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"place_bounty failed: {e}")
            return self._err("Failed to place bounty.")

    async def get_bounties(self, discord_id: int) -> dict:
        """Returns active bounties on this player."""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT b.*, p.username AS poster_username
                    FROM bounties b
                    JOIN players p ON p.discord_id = b.poster_id
                    WHERE b.target_id = $1 AND b.status = 'active'
                    ORDER BY b.amount DESC
                """, discord_id)
            return self._ok([dict(r) for r in rows])
        except Exception as e:
            self.logger.error(f"get_bounties failed: {e}")
            return self._ok([])

    # ─────────────────────────────────────────────────────────────
    # MARKET MODULE
    # ─────────────────────────────────────────────────────────────

    async def get_market_snapshot(self) -> dict:
        """
        Full market view in ONE query. All companies with price, 24h change, sector, last headline.

        Returns:
            list of { company_id, name, ticker, sector, current_price,
                      price_24h_ago, change_pct, direction, last_headline }
        """
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        c.id AS company_id,
                        c.name,
                        c.symbol AS ticker,
                        c.sector,
                        sp_now.price AS current_price,
                        sp_ago.price AS price_24h_ago,
                        CASE
                            WHEN sp_ago.price > 0
                            THEN ROUND(((sp_now.price - sp_ago.price)::numeric / sp_ago.price) * 100, 2)
                            ELSE 0
                        END AS change_pct,
                        mn.headline AS last_headline
                    FROM companies c
                    JOIN LATERAL (
                        SELECT price FROM stock_prices
                        WHERE company_id = c.id
                        ORDER BY recorded_at DESC LIMIT 1
                    ) sp_now ON true
                    LEFT JOIN LATERAL (
                        SELECT price FROM stock_prices
                        WHERE company_id = c.id
                          AND recorded_at <= NOW() - INTERVAL '24 hours'
                        ORDER BY recorded_at DESC LIMIT 1
                    ) sp_ago ON true
                    LEFT JOIN LATERAL (
                        SELECT headline FROM market_news
                        WHERE sector = c.sector
                        ORDER BY generated_at DESC LIMIT 1
                    ) mn ON true
                    ORDER BY c.id
                """)

            data = []
            for r in rows:
                row = dict(r)
                change = float(row.get("change_pct") or 0)
                row["direction"] = "up" if change > 0 else ("down" if change < 0 else "flat")
                data.append(row)

            return self._ok(data)

        except Exception as e:
            self.logger.error(f"get_market_snapshot failed: {e}")
            return self._err("Failed to load market data.")

    async def get_portfolio(self, discord_id: int) -> dict:
        """
        Player portfolio with current values and P&L in ONE query.

        Returns:
            { holdings: [...], total_invested, total_current_value, total_pnl }
        """
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        i.company_id,
                        c.symbol AS ticker,
                        c.name AS company_name,
                        i.shares AS quantity,
                        i.avg_buy_price,
                        sp.price AS current_price,
                        i.shares * sp.price AS current_value,
                        (i.shares * sp.price) - (i.shares * i.avg_buy_price) AS pnl,
                        CASE
                            WHEN i.avg_buy_price > 0
                            THEN ROUND(((sp.price - i.avg_buy_price)::numeric / i.avg_buy_price) * 100, 2)
                            ELSE 0
                        END AS pnl_pct
                    FROM investments i
                    JOIN companies c ON c.id = i.company_id
                    JOIN LATERAL (
                        SELECT price FROM stock_prices
                        WHERE company_id = i.company_id
                        ORDER BY recorded_at DESC LIMIT 1
                    ) sp ON true
                    WHERE i.discord_id = $1
                    ORDER BY current_value DESC
                """, discord_id)

            holdings = [dict(r) for r in rows]
            total_invested = sum(h["avg_buy_price"] * h["quantity"] for h in holdings)
            total_current = sum(h["current_value"] for h in holdings)

            return self._ok({
                "holdings": holdings,
                "total_invested": total_invested,
                "total_current_value": total_current,
                "total_pnl": total_current - total_invested
            })

        except Exception as e:
            self.logger.error(f"get_portfolio failed for {discord_id}: {e}")
            return self._err("Failed to load portfolio.")

    async def buy_stock(self, discord_id: int, company_id: int, quantity: int) -> dict:
        """Buy shares. Validates balance, updates position atomically."""
        try:
            result = await self.services.investment.buy(discord_id, company_id, quantity)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"buy_stock failed: {e}")
            return self._err("Purchase failed. Please try again.")

    async def sell_stock(self, discord_id: int, company_id: int, quantity: int) -> dict:
        """Sell shares. Calculates P&L vs avg buy price."""
        try:
            result = await self.services.investment.sell(discord_id, company_id, quantity)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"sell_stock failed: {e}")
            return self._err("Sale failed. Please try again.")

    # ─────────────────────────────────────────────────────────────
    # BUSINESS MODULE
    # ─────────────────────────────────────────────────────────────

    async def get_businesses(self, discord_id: int) -> dict:
        """
        All player businesses with collectability status in ONE query.

        Returns:
            list of { business_id, name, type, tier, district, daily_income,
                      stock_level, status, can_collect, collect_amount, last_collected }
        """
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        b.id AS business_id, b.name, b.business_type AS type,
                        b.tier, b.district, b.daily_income, b.stock_level,
                        b.status, b.last_collected, b.efficiency_override,
                        b.last_collected < NOW() - INTERVAL '4 hours' AS can_collect,
                        FLOOR(b.daily_income * COALESCE(b.efficiency_override, 1.0) / 6) AS collect_amount
                    FROM businesses b
                    WHERE b.discord_id = $1
                    ORDER BY b.opened_at DESC
                """, discord_id)
            return self._ok([dict(r) for r in rows])
        except Exception as e:
            self.logger.error(f"get_businesses failed for {discord_id}: {e}")
            return self._err("Failed to load businesses.")

    async def open_business(self, discord_id: int, business_type: str, name: str, district: int) -> dict:
        """Open a new business. Validates rep, max businesses, cost."""
        try:
            result = await self.services.business.open_business(discord_id, business_type, name, district)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"open_business failed: {e}")
            return self._err("Failed to open business.")

    async def collect_business(self, discord_id: int, business_id: int) -> dict:
        """Collect income from a business."""
        try:
            result = await self.services.business.collect_income(discord_id, business_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"collect_business failed: {e}")
            return self._err("Collection failed.")

    async def upgrade_business(self, discord_id: int, business_id: int) -> dict:
        """Upgrade a business tier."""
        try:
            result = await self.services.business.upgrade_business(discord_id, business_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"upgrade_business failed: {e}")
            return self._err("Upgrade failed.")

    async def restock_business(self, discord_id: int, business_id: int) -> dict:
        """Restock a business."""
        try:
            result = await self.services.business.restock(discord_id, business_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"restock_business failed: {e}")
            return self._err("Restock failed.")

    # ─────────────────────────────────────────────────────────────
    # FACTION MODULE
    # ─────────────────────────────────────────────────────────────

    async def get_faction(self, faction_id: int) -> dict:
        """
        Full faction info with members and controlled districts in ONE query.

        Returns:
            { id, name, tag, treasury, reputation, leader_id,
              members: [...], controlled_districts: [...] }
        """
        try:
            async with self.db.pool.acquire() as conn:
                faction = await conn.fetchrow("""
                    SELECT f.*,
                        COUNT(fm.discord_id) AS member_count
                    FROM factions f
                    LEFT JOIN faction_members fm ON fm.faction_id = f.id
                    WHERE f.id = $1 AND f.status = 'active'
                    GROUP BY f.id
                """, faction_id)

                if not faction:
                    return self._err("Faction not found.")

                members = await conn.fetch("""
                    SELECT fm.discord_id, fm.role, fm.joined_at, p.username
                    FROM faction_members fm
                    JOIN players p ON p.discord_id = fm.discord_id
                    WHERE fm.faction_id = $1
                    ORDER BY fm.role DESC, fm.joined_at ASC
                """, faction_id)

                districts = await conn.fetch("""
                    SELECT district, controlled_since
                    FROM district_control WHERE faction_id = $1
                """, faction_id)

            data = dict(faction)
            data["members"] = [dict(m) for m in members]
            data["controlled_districts"] = [dict(d) for d in districts]
            return self._ok(data)

        except Exception as e:
            self.logger.error(f"get_faction failed: {e}")
            return self._err("Failed to load faction.")

    async def get_player_faction(self, discord_id: int) -> dict:
        """Returns the faction the player belongs to, or None."""
        try:
            result = await self.services.faction.get_user_faction(discord_id)
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"get_player_faction failed: {e}")
            return self._ok(None)

    async def create_faction(self, discord_id: int, name: str, tag: str) -> dict:
        """Create a faction. Validates charter item, cost, name uniqueness."""
        try:
            result = await self.services.faction.create_faction(discord_id, name, tag)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"create_faction failed: {e}")
            return self._err("Failed to create faction.")

    async def join_faction(self, discord_id: int, faction_id: int) -> dict:
        """Accept a faction invite and join."""
        try:
            result = await self.services.faction.accept_invite(discord_id, faction_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"join_faction failed: {e}")
            return self._err("Failed to join faction.")

    async def leave_faction(self, discord_id: int) -> dict:
        """Leave current faction. Blocks if leader with remaining members."""
        try:
            result = await self.services.faction.leave_faction(discord_id)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"leave_faction failed: {e}")
            return self._err("Failed to leave faction.")

    async def get_district_map(self) -> dict:
        """Full district control map for all factions in ONE query."""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT dc.district, dc.controlled_since,
                           f.name AS faction_name, f.tag AS faction_tag
                    FROM district_control dc
                    LEFT JOIN factions f ON f.id = dc.faction_id
                    ORDER BY dc.district
                """)
            return self._ok([dict(r) for r in rows])
        except Exception as e:
            self.logger.error(f"get_district_map failed: {e}")
            return self._err("Failed to load district map.")

    # ─────────────────────────────────────────────────────────────
    # WORLD MODULE
    # ─────────────────────────────────────────────────────────────

    async def travel(self, discord_id: int, target_district: int) -> dict:
        """
        Travel to a district. Validates requirements, updates location, returns NPC greeting.

        Returns:
            { new_district, district_name, npc_greeting, active_events, travel_cost }
        """
        try:
            result = await self.services.world.travel(discord_id, target_district)
            if not result["success"]:
                return self._err(result["message"])
            return self._ok(result)
        except Exception as e:
            self.logger.error(f"travel failed: {e}")
            return self._err("Travel failed.")

    async def get_city_state(self) -> dict:
        """
        Active events, season info, district control summary in ONE query.

        Returns:
            { active_event, season, district_summary }
        """
        try:
            async with self.db.pool.acquire() as conn:
                season = await conn.fetchrow("""
                    SELECT id, name, theme FROM seasons
                    WHERE is_active = TRUE AND starts_at <= NOW() AND ends_at >= NOW()
                    LIMIT 1
                """)

                districts = await conn.fetch("""
                    SELECT dc.district, f.name AS faction_name, f.tag
                    FROM district_control dc
                    LEFT JOIN factions f ON f.id = dc.faction_id
                    ORDER BY dc.district
                """)

            return self._ok({
                "season": dict(season) if season else None,
                "district_summary": [dict(d) for d in districts]
            })
        except Exception as e:
            self.logger.error(f"get_city_state failed: {e}")
            return self._err("Failed to load city state.")

    async def get_city_feed(self, limit: int = 20) -> dict:
        """Recent city feed events."""
        try:
            feed = await self.services.world.get_city_feed(limit)
            return self._ok(feed)
        except Exception as e:
            self.logger.error(f"get_city_feed failed: {e}")
            return self._ok([])

    async def get_active_challenges(self, discord_id: int) -> dict:
        """Season + permanent challenges with progress."""
        try:
            challenges = await self.services.world.get_active_challenges(discord_id)
            return self._ok(challenges)
        except Exception as e:
            self.logger.error(f"get_active_challenges failed: {e}")
            return self._ok([])

    # ─────────────────────────────────────────────────────────────
    # IMAGE MODULE
    # ─────────────────────────────────────────────────────────────

    async def get_profile_card(self, player_data: dict) -> Optional[discord.File]:
        """
        Returns discord.File directly. Pass straight to followup.send(file=...).
        Pass the dict from get_player()['data'].
        Returns None if generation fails — handle gracefully with fallback embed.
        """
        try:
            return await self.services.image.generate_profile_card(player_data)
        except Exception as e:
            self.logger.error(f"get_profile_card failed: {e}")
            return None

    async def get_stats_card(self, stats_data: dict) -> Optional[discord.File]:
        """
        Returns discord.File or None. Pass dict from get_player_stats()['data'].
        """
        try:
            return await self.services.image.generate_stats_card(stats_data)
        except Exception as e:
            self.logger.error(f"get_stats_card failed: {e}")
            return None

    async def get_city_map(self, district: int) -> Optional[discord.File]:
        """Returns city map image with active district highlighted."""
        try:
            return await self.services.image.generate_city_map(district)
        except Exception as e:
            self.logger.error(f"get_city_map failed: {e}")
            return None

    # ─────────────────────────────────────────────────────────────
    # AI MODULE
    # ─────────────────────────────────────────────────────────────

    async def get_npc_line(self, npc_id: str, discord_id: int, context: str) -> str:
        """
        NPC dialogue with memory. Always returns a string — never raises.
        """
        try:
            async with self.db.pool.acquire() as conn:
                memory = await conn.fetch("""
                    SELECT context_summary, ai_response FROM ai_npc_memory
                    WHERE discord_id = $1 AND npc_id = $2
                    ORDER BY created_at DESC LIMIT 5
                """, discord_id, npc_id)

            player_result = await self.get_player(discord_id)
            player_data = player_result.get("data", {})

            return await self.services.ai.generate_npc_line(
                npc_id, player_data, context, [dict(m) for m in memory]
            )
        except Exception as e:
            self.logger.error(f"get_npc_line failed: {e}")
            return "The city speaks, but the words fade."

    async def get_analyst_report(self, discord_id: int) -> str:
        """Elite/Obsidian only. Fetches portfolio + market internally."""
        try:
            player_result = await self.get_player(discord_id)
            portfolio_result = await self.get_portfolio(discord_id)
            market_result = await self.get_market_snapshot()

            return await self.services.ai.generate_analyst_report(
                player_result.get("data", {}),
                portfolio_result.get("data", {}).get("holdings", []),
                market_result.get("data", [])
            )
        except Exception as e:
            self.logger.error(f"get_analyst_report failed: {e}")
            return "• Data insufficient. • Recalibrating. • Await market movement."

    async def moderate_content(self, content: str) -> tuple[bool, str]:
        """Returns (approved, reason). Use for billboard submissions."""
        try:
            return await self.services.ai.moderate_content(content)
        except Exception as e:
            self.logger.error(f"moderate_content failed: {e}")
            return True, ""

    # ─────────────────────────────────────────────────────────────
    # ADMIN MODULE
    # ─────────────────────────────────────────────────────────────

    async def admin_give_sc(self, target_id: int, amount: int, reason: str, mod_id: int) -> dict:
        """Dev only. Give SC to a player. Logs to transactions."""
        try:
            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow("""
                        UPDATE players SET wallet = wallet + $2
                        WHERE discord_id = $1
                        RETURNING wallet
                    """, target_id, amount)

                    if not row:
                        return self._err("Player not found.")

                    await conn.execute("""
                        INSERT INTO transactions (discord_id, amount, balance_after, tx_type, description, related_id)
                        VALUES ($1, $2, $3, 'admin_grant', $4, $5)
                    """, target_id, amount, row["wallet"], reason, mod_id)

            return self._ok({"new_wallet": row["wallet"], "amount_given": amount})
        except Exception as e:
            self.logger.error(f"admin_give_sc failed: {e}")
            return self._err("Failed to give SC.")

    async def admin_ban(self, target_id: int, reason: str, mod_id: int) -> dict:
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE players SET is_banned = TRUE, ban_reason = $2 WHERE discord_id = $1
                """, target_id, reason)
            return self._ok({"target_id": target_id})
        except Exception as e:
            self.logger.error(f"admin_ban failed: {e}")
            return self._err("Ban failed.")

    async def admin_unban(self, target_id: int, mod_id: int) -> dict:
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE players SET is_banned = FALSE, ban_reason = NULL WHERE discord_id = $1
                """, target_id)
            return self._ok({"target_id": target_id})
        except Exception as e:
            self.logger.error(f"admin_unban failed: {e}")
            return self._err("Unban failed.")

    async def admin_jail(self, target_id: int, hours: int, reason: str, mod_id: int) -> dict:
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE players
                    SET is_jailed = TRUE,
                        jail_until = NOW() + ($2 || ' hours')::INTERVAL,
                        business_efficiency = 0.5
                    WHERE discord_id = $1
                """, target_id, str(hours))
            return self._ok({"target_id": target_id, "hours": hours})
        except Exception as e:
            self.logger.error(f"admin_jail failed: {e}")
            return self._err("Jail failed.")

    async def admin_release_jail(self, target_id: int, mod_id: int) -> dict:
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE players
                    SET is_jailed = FALSE, jail_until = NULL, business_efficiency = 1.0
                    WHERE discord_id = $1
                """, target_id)
            return self._ok({"target_id": target_id})
        except Exception as e:
            self.logger.error(f"admin_release_jail failed: {e}")
            return self._err("Release failed.")

    async def admin_set_premium(self, target_id: int, tier: str, days: int, mod_id: int) -> dict:
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE players
                    SET premium_tier = $2,
                        premium_expires = NOW() + ($3 || ' days')::INTERVAL
                    WHERE discord_id = $1
                """, target_id, tier, str(days))
            return self._ok({"target_id": target_id, "tier": tier, "days": days})
        except Exception as e:
            self.logger.error(f"admin_set_premium failed: {e}")
            return self._err("Failed to set premium.")

    async def admin_reset_cooldown(self, target_id: int, action: str) -> dict:
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM cooldowns WHERE discord_id = $1 AND action = $2
                """, target_id, action)
            return self._ok({"target_id": target_id, "action": action})
        except Exception as e:
            self.logger.error(f"admin_reset_cooldown failed: {e}")
            return self._err("Failed to reset cooldown.")

    async def get_bot_stats(self) -> dict:
        """Bot-wide stats in ONE aggregated query."""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) AS total_players,
                        COUNT(*) FILTER (WHERE is_banned) AS banned_players,
                        COUNT(*) FILTER (WHERE premium_tier != 'citizen') AS premium_players,
                        COALESCE(SUM(wallet + bank), 0) AS sc_in_circulation,
                        COALESCE(AVG(wallet + bank), 0) AS avg_wealth,
                        COUNT(*) FILTER (
                            WHERE discord_id IN (
                                SELECT DISTINCT discord_id FROM interaction_log
                                WHERE created_at > NOW() - INTERVAL '24 hours'
                            )
                        ) AS active_today
                    FROM players
                """)
            return self._ok(dict(row))
        except Exception as e:
            self.logger.error(f"get_bot_stats failed: {e}")
            return self._err("Failed to load bot stats.")