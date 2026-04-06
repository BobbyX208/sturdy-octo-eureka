# events/handlers.py
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from events.bus import EventBus


class EventHandlers:
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.handlers")
        self._registered = False
    
    def register_all(self, bus: EventBus) -> None:
        if self._registered:
            return
        
        bus.register("player.created", self.on_player_created)
        bus.register("player.level_up", self.on_player_level_up)
        bus.register("player.prestige", self.on_player_prestige)
        
        bus.register("job.completed", self.on_job_completed)
        bus.register("job.hired", self.on_job_hired)
        bus.register("job.quit", self.on_job_quit)
        
        bus.register("crime.committed", self.on_crime_committed)
        bus.register("crime.failed", self.on_crime_failed)
        bus.register("crime.jailed", self.on_crime_jailed)
        bus.register("crime.released", self.on_crime_released)
        
        bus.register("business.opened", self.on_business_opened)
        bus.register("business.collected", self.on_business_collected)
        bus.register("business.neglected", self.on_business_neglected)
        bus.register("business.upgraded", self.on_business_upgraded)
        
        bus.register("investment.bought", self.on_investment_bought)
        bus.register("investment.sold", self.on_investment_sold)
        
        bus.register("faction.created", self.on_faction_created)
        bus.register("faction.joined", self.on_faction_joined)
        bus.register("faction.left", self.on_faction_left)
        bus.register("turf_war.resolved", self.on_turf_war_resolved)
        
        bus.register("heist.started", self.on_heist_started)
        bus.register("heist.completed", self.on_heist_completed)
        bus.register("heist.failed", self.on_heist_failed)
        
        bus.register("market_news.generated", self.on_market_news_generated)
        bus.register("stock_tick.completed", self.on_stock_tick_completed)
        
        bus.register("daily.reset", self.on_daily_reset)
        bus.register("weekly.reset", self.on_weekly_reset)
        bus.register("gazette.published", self.on_gazette_published)
        
        bus.register("ticket.created", self.on_ticket_created)
        bus.register("ticket.closed", self.on_ticket_closed)
        
        bus.register("anti_cheat.flag", self.on_anti_cheat_flag)
        
        self._registered = True
        self.logger.info("Event handlers registered")
    
    async def on_player_created(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        username = data.get("username")
        
        self.logger.info(f"Player created: {username} ({user_id})")
        
        if self.bot.services and self.bot.services.ai:
            channel = await self.bot.fetch_user(user_id)
            if channel:
                await channel.send(
                    f"Welcome to Simora City, {username}!\n"
                    f"Start your journey with /work in any server, or /travel to explore the districts.\n"
                    f"Ray says: 'Eyes open. Wallet closer.'"
                )
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "first_work"})
    
    async def on_player_level_up(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        new_rank = data.get("new_rank")
        new_title = data.get("new_title")
        
        self.logger.info(f"Player {user_id} reached rank {new_rank}: {new_title}")
        
        if self.bot.services and self.bot.services.image:
            card = await self.bot.services.image.generate_rank_up_card(user_id, new_rank, new_title)
            
            channel = await self.bot.fetch_user(user_id)
            if channel:
                await channel.send(
                    f"🎉 **Rank Up!** You are now {new_title} (Rank {new_rank})",
                    file=card
                )
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "rep_milestone", "value": data.get("reputation")})
    
    async def on_player_prestige(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        prestige_level = data.get("prestige_level")
        
        self.logger.info(f"Player {user_id} prestiged to level {prestige_level}")
        
        if self.bot.services and self.bot.services.image:
            card = await self.bot.services.image.generate_prestige_card(user_id, prestige_level)
            
            channel = await self.bot.fetch_user(user_id)
            if channel:
                await channel.send(
                    f"✨ **PRESTIGE {prestige_level}** ✨\n"
                    f"You have been reborn. The city remembers. Ghost whispers: 'Welcome back.'",
                    file=card
                )
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "prestige_achieved"})
    
    async def on_job_completed(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        job_id = data.get("job_id")
        reward = data.get("reward")
        
        self.logger.debug(f"Job completed: {user_id} earned {reward} from {job_id}")
        
        if self.bot.services and self.bot.services.ai and data.get("npc_line"):
            channel = await self.bot.fetch_user(user_id)
            if channel:
                await channel.send(data.get("npc_line"))
    
    async def on_job_hired(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        job_id = data.get("job_id")
        npc_name = data.get("npc_name")
        npc_line = data.get("npc_line")
        
        self.logger.info(f"Player {user_id} hired for {job_id}")
        
        if npc_line:
            channel = await self.bot.fetch_user(user_id)
            if channel:
                await channel.send(f"**{npc_name}:** {npc_line}")
    
    async def on_job_quit(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        job_id = data.get("job_id")
        npc_line = data.get("npc_line")
        
        self.logger.info(f"Player {user_id} quit {job_id}")
        
        if npc_line:
            channel = await self.bot.fetch_user(user_id)
            if channel:
                await channel.send(npc_line)
    
    async def on_crime_committed(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        crime_type = data.get("crime_type")
        loot = data.get("loot")
        
        self.logger.info(f"Crime committed: {user_id} got {loot} from {crime_type}")
        
        if loot > 5000:
            await self.bot.event_bus.fire("city_feed.post", {
                "event_type": "major_crime",
                "content": f"A daring {crime_type} netted a massive score in the district."
            })
    
    async def on_crime_failed(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        crime_type = data.get("crime_type")
        fine = data.get("fine")
        jailed = data.get("jailed", False)
        
        self.logger.info(f"Crime failed: {user_id} fined {fine} for {crime_type}, jailed={jailed}")
        
        if jailed:
            await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "first_jail"})
    
    async def on_crime_jailed(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        hours = data.get("hours")
        
        channel = await self.bot.fetch_user(user_id)
        if channel:
            await channel.send(
                f"🔒 **JAILED** 🔒\n"
                f"You've been caught and sentenced to {hours} hours in the Simora City Jail.\n"
                f"Ray says: 'Told you. Eyes open. Now you learn the hard way.'"
            )
    
    async def on_crime_released(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        
        channel = await self.bot.fetch_user(user_id)
        if channel:
            await channel.send(
                f"🔓 **RELEASED** 🔓\n"
                f"You walk out of jail. The sun feels different.\n"
                f"Ray says: 'Don't come back. But you will.'"
            )
    
    async def on_business_opened(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        business_name = data.get("business_name")
        
        self.logger.info(f"Business opened: {user_id} opened {business_name}")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "business_opened",
            "content": f"A new business, {business_name}, has opened its doors in the district."
        })
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "first_business"})
    
    async def on_business_collected(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        business_name = data.get("business_name")
        income = data.get("income")
        
        self.logger.debug(f"Business collected: {user_id} collected {income} from {business_name}")
    
    async def on_business_neglected(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        business_name = data.get("business_name")
        
        self.logger.warning(f"Business neglected: {user_id} neglected {business_name}")
        
        channel = await self.bot.fetch_user(user_id)
        if channel:
            await channel.send(
                f"⚠️ **BUSINESS NEGLECTED** ⚠️\n"
                f"{business_name} has been neglected for 48 hours. Efficiency has dropped 20%.\n"
                f"Ms. Chen says: 'The city doesn't wait for those who don't work.'"
            )
    
    async def on_business_upgraded(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        business_name = data.get("business_name")
        new_tier = data.get("new_tier")
        
        self.logger.info(f"Business upgraded: {user_id} upgraded {business_name} to tier {new_tier}")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "business_upgraded",
            "content": f"{business_name} has expanded to Tier {new_tier}. The district takes notice."
        })
    
    async def on_investment_bought(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        company = data.get("company")
        shares = data.get("shares")
        
        self.logger.debug(f"Investment bought: {user_id} bought {shares} of {company}")
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "first_stock"})
    
    async def on_investment_sold(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        company = data.get("company")
        shares = data.get("shares")
        profit = data.get("profit", 0)
        
        self.logger.debug(f"Investment sold: {user_id} sold {shares} of {company}, profit={profit}")
    
    async def on_faction_created(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        faction_name = data.get("faction_name")
        
        self.logger.info(f"Faction created: {faction_name} by {user_id}")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "faction_created",
            "content": f"A new faction, {faction_name}, has emerged in Simora City."
        })
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "faction_created"})
    
    async def on_faction_joined(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        faction_name = data.get("faction_name")
        
        self.logger.info(f"Player {user_id} joined faction {faction_name}")
        
        await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "faction_joined"})
        
        channel = await self.bot.fetch_user(user_id)
        if channel:
            await channel.send(
                f"⚔️ **JOINED {faction_name.upper()}** ⚔️\n"
                f"You are now part of the crew. Ghost whispers: 'Family now. Family protects. Family demands.'"
            )
    
    async def on_faction_left(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        faction_name = data.get("faction_name")
        
        self.logger.info(f"Player {user_id} left faction {faction_name}")
    
    async def on_turf_war_resolved(self, data: Dict[str, Any], event_id: str = None) -> None:
        district = data.get("district")
        faction_id = data.get("faction_id")
        faction_name = data.get("faction_name")
        
        self.logger.info(f"Turf war resolved: District {district} now controlled by {faction_name}")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "turf_war_resolved",
            "content": f"🔥 TURF WAR 🔥\nDistrict {district} has been claimed by {faction_name}!"
        })
    
    async def on_heist_started(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        district = data.get("district")
        
        self.logger.info(f"Heist started: {user_id} initiated heist in district {district}")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "heist_started",
            "content": f"⚠️ A heist is being planned in District {district}. The city holds its breath."
        })
    
    async def on_heist_completed(self, data: Dict[str, Any], event_id: str = None) -> None:
        participants = data.get("participants", [])
        loot = data.get("loot")
        
        self.logger.info(f"Heist completed: {len(participants)} players earned {loot} total")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "heist_completed",
            "content": f"💰 MASSIVE HEIST 💰\nA crew of {len(participants)} pulled off a heist worth {loot} SC!"
        })
        
        for user_id in participants:
            await self.bot.event_bus.fire("story_beat.check", {"user_id": user_id, "beat": "first_heist"})
    
    async def on_heist_failed(self, data: Dict[str, Any], event_id: str = None) -> None:
        participants = data.get("participants", [])
        
        self.logger.info(f"Heist failed: {len(participants)} players jailed")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "heist_failed",
            "content": f"🚨 HEIST FAILED 🚨\nA crew of {len(participants)} was caught. The streets are watching."
        })
    
    async def on_market_news_generated(self, data: Dict[str, Any], event_id: str = None) -> None:
        count = data.get("count", 0)
        
        self.logger.info(f"Generated {count} market news items")
        
        if count > 0:
            await self.bot.event_bus.fire("city_feed.post", {
                "event_type": "market_news",
                "content": f"📰 Market News: {count} new headlines are moving the markets."
            })
    
    async def on_stock_tick_completed(self, data: Dict[str, Any], event_id: str = None) -> None:
        companies = data.get("companies", [])
        
        self.logger.debug(f"Stock tick completed: {len(companies)} companies updated")
    
    async def on_daily_reset(self, data: Dict[str, Any], event_id: str = None) -> None:
        self.logger.info("Daily reset completed")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "daily_reset",
            "content": "🌅 A new day dawns in Simora City. Daily limits reset. The city stirs."
        })
    
    async def on_weekly_reset(self, data: Dict[str, Any], event_id: str = None) -> None:
        self.logger.info("Weekly reset completed")
        
        await self.bot.event_bus.fire("city_feed.post", {
            "event_type": "weekly_reset",
            "content": "📅 A new week begins. Weekly challenges reset. The Gazette is coming."
        })
    
    async def on_gazette_published(self, data: Dict[str, Any], event_id: str = None) -> None:
        content = data.get("content", {})
        
        self.logger.info("Weekly Gazette published")
        
        channel_id = self.bot.config.get("ANNOUNCEMENT_CHANNEL")
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send("📰 **The Simora City Gazette** 📰\n\n" + content.get("summary", "The weekly recap is here."))
    
    async def on_ticket_created(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        category = data.get("category")
        channel_id = data.get("channel_id")
        
        self.logger.info(f"Ticket created: {user_id} - {category} in #{channel_id}")
    
    async def on_ticket_closed(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        category = data.get("category")
        
        self.logger.info(f"Ticket closed: {user_id} - {category}")
    
    async def on_anti_cheat_flag(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        flag_type = data.get("flag_type")
        details = data.get("details")
        
        self.logger.warning(f"Anti-cheat flag: {user_id} - {flag_type} - {details}")
        
        mod_channel_id = self.bot.config.get("MOD_ALERTS_CHANNEL")
        if mod_channel_id:
            channel = self.bot.get_channel(mod_channel_id)
            if channel:
                await channel.send(
                    f"⚠️ **ANTI-CHEAT FLAG** ⚠️\n"
                    f"User: <@{user_id}>\n"
                    f"Type: {flag_type}\n"
                    f"Details: {details}"
                )
    
    async def on_story_beat_check(self, data: Dict[str, Any], event_id: str = None) -> None:
        user_id = data.get("user_id")
        beat = data.get("beat")
        value = data.get("value")
        
        if self.bot.services and self.bot.services.world:
            await self.bot.services.world.check_story_beat(user_id, beat, value)
    
    async def on_city_feed_post(self, data: Dict[str, Any], event_id: str = None) -> None:
        event_type = data.get("event_type")
        content = data.get("content")
        
        if self.bot.services and self.bot.services.world:
            await self.bot.services.world.post_to_city_feed(event_type, content)
    
    async def close(self) -> None:
        self.logger.info("Event handlers closed")