import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import discord

from config.settings import Config
from core.cooldowns import CooldownManager
from database.connection import DatabasePool
from events.bus import EventBus
from services.ai_service import AIService
from services.world_service import WorldService


class BackgroundTaskManager:
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.tasks")
        self.tasks: List[asyncio.Task] = []
        self._running = False
    
    async def start_all(self) -> None:
        self._running = True
        
        self.tasks = [
            asyncio.create_task(self._daily_reset(), name="daily_reset"),
            asyncio.create_task(self._gbm_stock_tick(), name="gbm_stock_tick"),
            asyncio.create_task(self._generate_market_news(), name="generate_market_news"),
            asyncio.create_task(self._collect_business_income(), name="collect_business_income"),
            asyncio.create_task(self._check_business_neglect(), name="check_business_neglect"),
            asyncio.create_task(self._check_jail_releases(), name="check_jail_releases"),
            asyncio.create_task(self._apply_taxes(), name="apply_taxes"),
            asyncio.create_task(self._resolve_turf_wars(), name="resolve_turf_wars"),
            asyncio.create_task(self._weekly_gazette(), name="weekly_gazette"),
            asyncio.create_task(self._weekly_challenge_reset(), name="weekly_challenge_reset"),
            asyncio.create_task(self._monthly_challenge_reset(), name="monthly_challenge_reset"),
            asyncio.create_task(self._weekly_faction_dues(), name="weekly_faction_dues"),
            asyncio.create_task(self._billboard_poster(), name="billboard_poster"),
            asyncio.create_task(self._ai_cache_cleanup(), name="ai_cache_cleanup"),
            asyncio.create_task(self._heartbeat_monitor(), name="heartbeat_monitor"),
        ]
        
        self.logger.info(f"Started {len(self.tasks)} background tasks")
    
    async def stop_all(self) -> None:
        self._running = False
        
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.logger.info("All background tasks stopped")
    
    async def _daily_reset(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_midnight = (midnight - now).total_seconds()
                
                await asyncio.sleep(seconds_until_midnight)
                
                async with self.bot.db.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("""
                            UPDATE players 
                            SET daily_earned = 0, daily_jobs = 0, daily_gambled = 0
                        """)
                        
                        await conn.execute("""
                            DELETE FROM cooldowns WHERE expires_at <= NOW()
                        """)
                        
                        await conn.execute("""
                            DELETE FROM market_listings WHERE expires_at <= NOW()
                        """)
                        
                        await conn.execute("""
                            DELETE FROM interaction_log 
                            WHERE created_at < NOW() - INTERVAL '30 days'
                        """)
                        
                        await conn.execute("""
                            DELETE FROM ai_error_log 
                            WHERE created_at < NOW() - INTERVAL '7 days'
                        """)
                
                await self.bot.event_bus.fire("daily_reset.completed", {"timestamp": datetime.now(timezone.utc).isoformat()})
                self.logger.info("Daily reset completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Daily reset failed: {e}")
                await asyncio.sleep(60)
    
    async def _gbm_stock_tick(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(3600)
                
                if not self.bot.ctx or not self.bot.ctx.services.investment:
                    continue
                
                await self.bot.ctx.services.investment.process_gbm_tick()
                self.logger.info("GBM stock tick completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"GBM stock tick failed: {e}")
                await asyncio.sleep(60)
    
    async def _generate_market_news(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(21600)
                
                if not self.bot.ctx or not self.bot.ctx.services.ai:
                    continue
                
                headlines = await self.bot.ctx.services.ai.generate_market_headlines()
                
                async with self.bot.db.pool.acquire() as conn:
                    for headline in headlines:
                        await conn.execute("""
                            INSERT INTO market_news (headline, sector, modifier, direction, generated_at, expires_at)
                            VALUES ($1, $2, $3, $4, NOW(), NOW() + INTERVAL '24 hours')
                        """, headline.get("headline"), headline.get("sector"), 
                            headline.get("modifier", 1.0), headline.get("direction", "neutral"))
                
                await self.bot.event_bus.fire("market_news.generated", {"count": len(headlines)})
                self.logger.info(f"Generated {len(headlines)} market news items")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Market news generation failed: {e}")
                await asyncio.sleep(300)
    
    async def _collect_business_income(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(14400)
                
                if not self.bot.ctx or not self.bot.ctx.services.business:
                    continue
                
                await self.bot.ctx.services.business.collect_all_income()
                self.logger.info("Business income collection completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Business income collection failed: {e}")
                await asyncio.sleep(60)
    
    async def _check_business_neglect(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(7200)
                
                async with self.bot.db.pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT id, discord_id, name, last_restocked
                        FROM businesses
                        WHERE last_restocked < NOW() - INTERVAL '48 hours'
                          AND status = 'active'
                    """)
                    
                    for row in rows:
                        await conn.execute("""
                            UPDATE businesses
                            SET efficiency_override = COALESCE(efficiency_override, 1.0) * 0.8
                            WHERE id = $1
                        """, row["id"])
                        
                        await self.bot.event_bus.fire("business.neglected", {
                            "business_id": row["id"],
                            "owner_id": row["discord_id"],
                            "business_name": row["name"]
                        })
                
                self.logger.info(f"Checked {len(rows)} businesses for neglect")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Business neglect check failed: {e}")
                await asyncio.sleep(60)
    
    async def _check_jail_releases(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(300)
                
                async with self.bot.db.pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT discord_id FROM players
                        WHERE is_jailed = TRUE AND jail_until <= NOW()
                    """)
                    
                    for row in rows:
                        await conn.execute("""
                            UPDATE players
                            SET is_jailed = FALSE, jail_until = NULL, business_efficiency = 1.0
                            WHERE discord_id = $1
                        """, row["discord_id"])
                        
                        await self.bot.event_bus.fire("crime.released", {
                            "user_id": row["discord_id"]
                        })
                
                if rows:
                    self.logger.info(f"Released {len(rows)} players from jail")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Jail release check failed: {e}")
                await asyncio.sleep(60)
    
    async def _apply_taxes(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                target_time = now.replace(hour=2, minute=0, second=0, microsecond=0)
                
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                seconds_until = (target_time - now).total_seconds()
                await asyncio.sleep(seconds_until)
                
                async with self.bot.db.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("""
                            UPDATE players
                            SET wallet = GREATEST(wallet - LEAST(wallet * 0.01, 500), 0)
                            WHERE wallet > 0
                        """)
                        
                        await conn.execute("""
                            UPDATE players
                            SET bank = GREATEST(bank - ((wallet + bank - 500000) * 0.005), 0)
                            WHERE wallet + bank > 500000
                        """)
                
                self.logger.info("Taxes applied")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Tax application failed: {e}")
                await asyncio.sleep(60)
    
    async def _resolve_turf_wars(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(300)
                
                async with self.bot.db.pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT district, faction_id FROM district_control
                        WHERE contest_ends <= NOW() AND contest_ends IS NOT NULL
                    """)
                    
                    for row in rows:
                        await self.bot.event_bus.fire("turf_war.resolved", {
                            "district": row["district"],
                            "faction_id": row["faction_id"]
                        })
                
                if rows:
                    self.logger.info(f"Resolved {len(rows)} turf wars")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Turf war resolution failed: {e}")
                await asyncio.sleep(60)
    
    async def _weekly_gazette(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.hour >= 0:
                    days_until_monday = 7
                
                target_time = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until = (target_time - now).total_seconds()
                
                await asyncio.sleep(seconds_until)
                
                if not self.bot.ctx or not self.bot.ctx.services.world:
                    continue
                
                gazette = await self.bot.ctx.services.world.generate_weekly_gazette()
                
                async with self.bot.db.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO weekly_gazette (content, generated_at)
                        VALUES ($1, NOW())
                    """, gazette)
                
                await self.bot.event_bus.fire("gazette.published", {"content": gazette})
                self.logger.info("Weekly gazette generated")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Weekly gazette generation failed: {e}")
                await asyncio.sleep(3600)

    
    async def _weekly_challenge_reset(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.hour >= 0:
                    days_until_monday = 7
                
                target_time = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until = (target_time - now).total_seconds()
                
                await asyncio.sleep(seconds_until)
                
                async with self.bot.db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE players
                        SET weekly_challenges = '{}'::jsonb
                        WHERE weekly_challenges IS NOT NULL
                    """)
                
                self.logger.info("Weekly challenges reset")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Weekly challenge reset failed: {e}")
                await asyncio.sleep(3600)
    
    async def _monthly_challenge_reset(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                
                if now >= first_of_month:
                    first_of_month = (first_of_month + timedelta(days=32)).replace(day=1)
                
                seconds_until = (first_of_month - now).total_seconds()
                await asyncio.sleep(seconds_until)
                
                async with self.bot.db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE players
                        SET monthly_challenges = '{}'::jsonb
                        WHERE monthly_challenges IS NOT NULL
                    """)
                
                self.logger.info("Monthly challenges reset")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monthly challenge reset failed: {e}")
                await asyncio.sleep(3600)
    
    async def _weekly_faction_dues(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.hour >= 0:
                    days_until_monday = 7
                
                target_time = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until = (target_time - now).total_seconds()
                
                await asyncio.sleep(seconds_until)
                
                async with self.bot.db.pool.acquire() as conn:
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
                                SET wallet = wallet - $1
                                WHERE discord_id = $2 AND wallet >= $1
                            """, faction["weekly_dues"], member["discord_id"])
                            
                            await conn.execute("""
                                UPDATE factions
                                SET treasury = treasury + $1
                                WHERE id = $2
                            """, faction["weekly_dues"], faction["id"])
                
                self.logger.info("Weekly faction dues collected")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Weekly faction dues failed: {e}")
                await asyncio.sleep(3600)
    
    async def _billboard_poster(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(172800)
                
                async with self.bot.db.pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT id, discord_id, ai_output
                        FROM billboard_queue
                        WHERE status = 'approved' AND posted_at IS NULL
                        ORDER BY submitted_at ASC
                        LIMIT 1
                    """)
                    
                    for row in rows:
                        await conn.execute("""
                            UPDATE billboard_queue
                            SET posted_at = NOW(), status = 'posted'
                            WHERE id = $1
                        """, row["id"])
                        
                        await self.bot.event_bus.fire("billboard.posted", {
                            "user_id": row["discord_id"],
                            "content": row["ai_output"]
                        })
                
                self.logger.info("Billboard poster check completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Billboard poster failed: {e}")
                await asyncio.sleep(3600)
    
    async def _ai_cache_cleanup(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(21600)
                
                async with self.bot.db.pool.acquire() as conn:
                    await conn.execute("""
                        DELETE FROM ai_response_cache
                        WHERE expires_at <= NOW()
                    """)
                
                self.logger.info("AI cache cleanup completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"AI cache cleanup failed: {e}")
                await asyncio.sleep(3600)
    
    async def _heartbeat_monitor(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(60)
                
                async with self.bot.db.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO heartbeat_log (bot_id, timestamp, guild_count, latency)
                        VALUES ($1, NOW(), $2, $3)
                    """, self.bot.user.id, len(self.bot.guilds), self.bot.latency)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat monitor failed: {e}")