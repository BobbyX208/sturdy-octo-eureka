import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import random

from database.connection import DatabasePool
from services.ai_service import AIService
from core.cache import CacheManager
from events.bus import EventBus
from config.settings import Config


class WorldService:
    
    def __init__(self, db: DatabasePool, ai_service: AIService, cache: CacheManager, event_bus: EventBus):
        self.db = db
        self.ai_service = ai_service
        self.cache = cache
        self.event_bus = event_bus
        self.logger = logging.getLogger("simcoin.services.world")
        
        self.story_beats = self._load_story_beats()
    
    def _load_story_beats(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(f"{Config.DATA_DIR}/story_beats.json", "r") as f:
                data = json.load(f)
                return {beat["id"]: beat for beat in data.get("beats", [])}
        except Exception as e:
            self.logger.error(f"Failed to load story beats: {e}")
            return {}
    
    async def check_story_beat(self, user_id: int, trigger: str, value: Any = None) -> None:
        try:
            conn = await self.db.acquire()
            try:
                for beat_id, beat in self.story_beats.items():
                    if beat["trigger"] != trigger:
                        continue
                    
                    if "trigger_value" in beat and beat["trigger_value"] != value:
                        continue
                    
                    already_triggered = await conn.fetchval("""
                        SELECT 1 FROM story_beats_log
                        WHERE discord_id = $1 AND beat_id = $2
                    """, user_id, beat_id)
                    
                    if already_triggered:
                        continue
                    
                    await conn.execute("""
                        INSERT INTO story_beats_log (discord_id, beat_id)
                        VALUES ($1, $2)
                    """, user_id, beat_id)
                    
                    await self.event_bus.fire("story_beat.triggered", {
                        "user_id": user_id,
                        "beat_id": beat_id,
                        "title": beat["title"],
                        "content": beat["content"],
                        "delay_seconds": beat.get("delay_seconds", 0)
                    })
                    
                    self.logger.info(f"Story beat triggered for {user_id}: {beat['title']}")
            finally:
                await self.db.release(conn)
                    
        except Exception as e:
            self.logger.error(f"Check story beat failed: {e}")
    
    async def post_to_city_feed(self, event_type: str, content: str) -> None:
        try:
            conn = await self.db.acquire()
            try:
                await conn.execute("""
                    INSERT INTO city_feed_log (event_type, event_key, content, posted_at)
                    VALUES ($1, $2, $3, NOW())
                """, event_type, f"{event_type}_{datetime.now(timezone.utc).timestamp()}", content)
            finally:
                await self.db.release(conn)
            
            self.logger.info(f"City feed post: {event_type} - {content[:50]}")
            
        except Exception as e:
            self.logger.error(f"Post to city feed failed: {e}")
    
    async def generate_weekly_gazette(self) -> Dict[str, Any]:
        try:
            conn = await self.db.acquire()
            try:
                top_earner = await conn.fetchrow("""
                    SELECT username, total_earned FROM players
                    ORDER BY total_earned DESC
                    LIMIT 1
                """)
                
                biggest_heist = await conn.fetchrow("""
                    SELECT loot, participants FROM heist_sessions
                    WHERE state = 'completed' AND resolved_at > NOW() - INTERVAL '7 days'
                    ORDER BY loot DESC
                    LIMIT 1
                """)
                
                top_stock = await conn.fetchrow("""
                    SELECT company_id, price FROM stock_prices
                    WHERE recorded_at > NOW() - INTERVAL '7 days'
                    ORDER BY price DESC
                    LIMIT 1
                """)
                
                faction_news = await conn.fetch("""
                    SELECT f.name, COUNT(dc.district) as districts
                    FROM factions f
                    LEFT JOIN district_control dc ON dc.faction_id = f.id
                    WHERE dc.controlled_since > NOW() - INTERVAL '7 days'
                    GROUP BY f.id
                    ORDER BY districts DESC
                    LIMIT 3
                """)
            finally:
                await self.db.release(conn)
            
            npc_quote = await self.ai_service.generate_npc_line("gazette", {})
            
            gazette = {
                "summary": f"This week in Simora City...",
                "top_earner": dict(top_earner) if top_earner else None,
                "biggest_heist": dict(biggest_heist) if biggest_heist else None,
                "top_stock": dict(top_stock) if top_stock else None,
                "faction_news": [dict(f) for f in faction_news],
                "npc_quote": npc_quote,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.post_to_city_feed("weekly_gazette", f"📰 Weekly Gazette: {gazette['summary']}")
            
            return gazette
            
        except Exception as e:
            self.logger.error(f"Generate weekly gazette failed: {e}")
            return {"error": str(e)}
    
    async def generate_city_event(self) -> Optional[Dict[str, Any]]:
        try:
            events = [
                {"type": "market_boom", "modifier": 1.2, "duration_hours": 6},
                {"type": "crime_wave", "modifier": 1.3, "duration_hours": 4},
                {"type": "festival", "modifier": 1.1, "duration_hours": 12},
                {"type": "power_outage", "modifier": 0.8, "duration_hours": 3}
            ]
            
            if random.random() < 0.3:
                event = random.choice(events)
                
                description = await self.ai_service.generate_event_description(event["type"])
                
                await self.post_to_city_feed("city_event", f"🌆 {description}")
                
                return {
                    "event": event["type"],
                    "modifier": event["modifier"],
                    "duration_hours": event["duration_hours"],
                    "description": description
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Generate city event failed: {e}")
            return None
    
    async def get_city_feed(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            conn = await self.db.acquire()
            try:
                rows = await conn.fetch("""
                    SELECT event_type, content, posted_at
                    FROM city_feed_log
                    ORDER BY posted_at DESC
                    LIMIT $1
                """, limit)
                
                return [dict(row) for row in rows]
            finally:
                await self.db.release(conn)
                
        except Exception as e:
            self.logger.error(f"Get city feed failed: {e}")
            return []
    
    async def get_active_season(self) -> Optional[Dict[str, Any]]:
        try:
            conn = await self.db.acquire()
            try:
                season = await conn.fetchrow("""
                    SELECT * FROM seasons
                    WHERE is_active = TRUE AND starts_at <= NOW() AND ends_at >= NOW()
                    LIMIT 1
                """)
                
                return dict(season) if season else None
            finally:
                await self.db.release(conn)
                
        except Exception as e:
            self.logger.error(f"Get active season failed: {e}")
            return None
    
    async def get_active_challenges(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            season = await self.get_active_season()
            
            conn = await self.db.acquire()
            try:
                if season:
                    rows = await conn.fetch("""
                        SELECT * FROM challenges
                        WHERE season_id = $1 OR season_id IS NULL
                        ORDER BY challenge_type
                    """, season["id"])
                else:
                    rows = await conn.fetch("""
                        SELECT * FROM challenges
                        WHERE season_id IS NULL
                        ORDER BY challenge_type
                    """)
                
                return [dict(row) for row in rows]
            finally:
                await self.db.release(conn)
                
        except Exception as e:
            self.logger.error(f"Get active challenges failed: {e}")
            return []

    async def travel(self, user_id: int, target_district: int) -> Dict[str, Any]:
        """Travel to a district."""
        try:
            from services.player_service import PlayerService
            player_service = PlayerService(self.db, self.cache, self.event_bus)
            success, message = await player_service.travel(user_id, target_district)
            
            if not success:
                return {"success": False, "message": message}
            
            player = await player_service.get(user_id)
            
            npc_map = {1: "ray", 2: "marco", 3: "chen", 4: "broker", 5: "lou", 6: "ghost"}
            npc_id = npc_map.get(target_district, "ray")
            
            greeting = await self.ai_service.generate_npc_line(
                npc_id,
                player or {},
                f"Player just arrived in district {target_district}. Welcome them briefly."
            )
            
            return {
                "success": True,
                "new_district": target_district,
                "district_name": Config.DISTRICTS[target_district - 1]["name"] if target_district <= len(Config.DISTRICTS) else "Unknown",
                "npc_greeting": greeting,
                "active_events": [],
                "travel_cost": 0
            }
            
        except Exception as e:
            self.logger.error(f"Travel failed for {user_id}: {e}")
            return {"success": False, "message": "Travel failed."}