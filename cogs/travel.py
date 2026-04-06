import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
import asyncio
from typing import Optional
import random

from utils.checks import requires_profile, not_jailed
from utils.embeds import EmbedBuilder
from utils.formatters import format_sc, format_time, progress_bar, ordinal
from utils.delayed_response import DelayedResponse, NPCDelayedResponse, TensionBuilder
from utils.luck import Luck


class TravelCog(commands.Cog):
    """Travel commands - explore Simora City districts"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.cogs.travel")
        
        self.district_names = {
            1: "🏚️ Slums",
            2: "🏢 Downtown",
            3: "💹 Financial District",
            4: "🌿 Underground",
            5: "🏭 Industrial Zone",
            6: "🎰 The Strip"
        }
        
        self.district_npcs = {
            1: "ray",
            2: "chen",
            3: "broker",
            4: "ghost",
            5: "marco",
            6: "lou"
        }
        
        self.district_requirements = {
            2: {"rep_rank": 2, "sc": 10000, "name": "Downtown"},
            3: {"rep_rank": 4, "sc": 50000, "name": "Financial District"},
            4: {"rep_rank": 3, "sc": 25000, "name": "Underground"},
            5: {"rep_rank": 2, "sc": 15000, "name": "Industrial Zone"},
            6: {"rep_rank": 5, "sc": 75000, "name": "The Strip"}
        }
        
        self.district_activities = {
            1: ["Work at Ray's odd jobs", "Petty crime in back alleys", "Visit the community center"],
            2: ["Apply at corporate offices", "Shop at premium stores", "Attend city hall meetings"],
            3: ["Trade stocks at SSX", "Meet The Broker", "Invest in startups"],
            4: ["Plan heists with Ghost", "Buy black market items", "Gather intel"],
            5: ["Manage warehouses", "Run freight operations", "Marco's logistics hub"],
            6: ["Gamble at Lucky Lou's", "High-stakes poker", "Neon nightlife"]
        }

    @app_commands.command(name="travel", description="Travel to a different district")
    @app_commands.describe(
        district="District number (1-6) or name",
        ephemeral="Hide the response from others (default: False)"
    )
    @app_commands.choices(district=[
        app_commands.Choice(name="🏚️ Slums", value="1"),
        app_commands.Choice(name="🏢 Downtown", value="2"),
        app_commands.Choice(name="💹 Financial District", value="3"),
        app_commands.Choice(name="🌿 Underground", value="4"),
        app_commands.Choice(name="🏭 Industrial Zone", value="5"),
        app_commands.Choice(name="🎰 The Strip", value="6")
    ])
    @requires_profile()
    @not_jailed()
    async def travel(self, interaction: discord.Interaction, district: str, ephemeral: bool = False):
        """Travel to another district with travel animation and NPC arrival"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        try:
            target_district = int(district)
        except ValueError:
            district_lower = district.lower()
            district_map = {
                "slums": 1, "downtown": 2, "financial": 3, "financial district": 3,
                "underground": 4, "industrial": 5, "industrial zone": 5, "strip": 6, "the strip": 6
            }
            target_district = district_map.get(district_lower)
            if not target_district:
                await interaction.followup.send(
                    "❌ Invalid district. Use 1-6 or name: Slums, Downtown, Financial District, Underground, Industrial Zone, The Strip",
                    ephemeral=ephemeral
                )
                return
        
        if target_district < 1 or target_district > 6:
            await interaction.followup.send(
                "❌ District must be between 1 and 6.",
                ephemeral=ephemeral
            )
            return
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        current_district = player_data.get("district", 1)
        
        if target_district == current_district:
            await interaction.followup.send(
                f"❌ You're already in {self.district_names.get(target_district, 'Unknown')}.",
                ephemeral=ephemeral
            )
            return
        
        cooldown_remaining = await self.bot.services.player.check_cooldown(
            interaction.user.id, "travel"
        )
        
        if cooldown_remaining > 0:
            await interaction.followup.send(
                f"⏰ You're still recovering from your last travel. Try again in {format_time(cooldown_remaining)}.",
                ephemeral=ephemeral
            )
            return
        
        if target_district > 1:
            req = self.district_requirements.get(target_district)
            if req:
                rep_rank = player_data.get("rep_rank", 1)
                wallet = player_data.get("wallet", 0)
                
                if rep_rank < req["rep_rank"]:
                    await interaction.followup.send(
                        f"❌ **{req['name']} is locked**\n"
                        f"Requires: Reputation Rank {req['rep_rank']}\n"
                        f"Your rank: {rep_rank}\n"
                        f"{progress_bar(min(100, int(rep_rank / req['rep_rank'] * 100)), 10)}",
                        ephemeral=ephemeral
                    )
                    return
                
                if wallet < req["sc"]:
                    await interaction.followup.send(
                        f"❌ **{req['name']} is locked**\n"
                        f"Requires: {format_sc(req['sc'])}\n"
                        f"You have: {format_sc(wallet)}\n"
                        f"{progress_bar(min(100, int(wallet / req['sc'] * 100)), 10)}",
                        ephemeral=ephemeral
                    )
                    return
        
        tension = DelayedResponse(interaction, self.bot.services.ai, min_delay=2.0, max_delay=2.5)
        
        travel_messages = [
            "The city blurs as you move through the streets...",
            f"Leaving {self.district_names.get(current_district)} behind...",
            "Neon lights streak past. District lines cross...",
            "The pulse of the city carries you forward..."
        ]
        
        tension_embed = discord.Embed(
            description=f"*{random.choice(travel_messages)}*",
            color=0x2b2d31
        )
        tension_embed.set_footer(text="Simora City")
        
        await tension.send_tension_custom(tension_embed, ephemeral=ephemeral)
        
        await self.bot.services.player.update_district(interaction.user.id, target_district)
        
        await self.bot.services.player.set_cooldown(interaction.user.id, "travel", 300)
        
        first_visit_key = f"visited_{target_district}"
        story_flags = player_data.get("story_flags", {})
        is_first_visit = not story_flags.get(first_visit_key, False)
        
        if is_first_visit:
            story_flags[first_visit_key] = datetime.now(timezone.utc).isoformat()
            await self.bot.services.player.update_story_flags(interaction.user.id, story_flags)
        
        result_embed = discord.Embed(
            title=f"🚌 Arrived at {self.district_names.get(target_district)}",
            description=f"You step into the heart of {self.district_names.get(target_district)}.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        activities = self.district_activities.get(target_district, ["Explore the area"])
        result_embed.add_field(
            name="📍 Things to do",
            value="\n".join([f"• {a}" for a in activities[:3]]),
            inline=False
        )
        
        result_embed.set_footer(text="Use /whereami for more details")
        
        await tension.resolve(result_embed)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
        
        npc_id = self.district_npcs.get(target_district, "ray")
        
        if is_first_visit:
            await npc_delayed.send_line(
                npc_id,
                {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": target_district, "premium_tier": player_data.get("premium_tier", "citizen")},
                f"Player's first time visiting {self.district_names.get(target_district)}. Welcome them to your territory.",
                delay=1.5,
                ephemeral=ephemeral
            )
            
            await self.bot.event_bus.fire("district.unlocked", {
                "discord_id": interaction.user.id,
                "username": interaction.user.name,
                "district": target_district,
                "district_name": self.district_names.get(target_district)
            })
        else:
            await npc_delayed.send_line(
                npc_id,
                {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": target_district, "premium_tier": player_data.get("premium_tier", "citizen")},
                f"Player returned to {self.district_names.get(target_district)}. Acknowledge their return briefly.",
                delay=1.5,
                ephemeral=ephemeral
            )
        
        await self.bot.event_bus.fire("player.travel", {
            "discord_id": interaction.user.id,
            "username": interaction.user.name,
            "from_district": current_district,
            "to_district": target_district,
            "from_name": self.district_names.get(current_district),
            "to_name": self.district_names.get(target_district),
            "first_visit": is_first_visit
        })
        
        self.logger.info(f"Player traveled: {interaction.user.id} {current_district} -> {target_district}")

    @app_commands.command(name="map", description="View the city map with faction control")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def map(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Display Pillow city map with faction borders and event markers"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        current_district = player_data.get("district", 1)
        
        district_control = await self.bot.services.faction.get_district_control_map()
        
        active_events = await self.bot.services.world.get_active_events()
        
        map_image = await self.bot.services.image.generate_city_map(
            current_district,
            district_control,
            active_events
        )
        
        if map_image:
            file = discord.File(map_image, filename="city_map.png")
            await interaction.followup.send(file=file, ephemeral=ephemeral)
        else:
            embed = self._build_fallback_map_embed(district_control, current_district)
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    def _build_fallback_map_embed(self, district_control: dict, current_district: int) -> discord.Embed:
        """Fallback text map if image generation fails"""
        
        control_emojis = {
            None: "⚪",
            "contested": "🟡"
        }
        
        district_control_map = {
            1: "Slums",
            2: "Downtown", 
            3: "Financial District",
            4: "Underground",
            5: "Industrial Zone",
            6: "The Strip"
        }
        
        embed = discord.Embed(
            title="🗺️ Simora City Map",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        description = []
        
        for district_id, name in district_control_map.items():
            control = district_control.get(district_id) if district_control else None
            current_marker = "📍 " if district_id == current_district else ""
            
            if control and control.get("faction_name"):
                faction_name = control["faction_name"]
                emoji = "🔴"
                description.append(f"{current_marker}{emoji} **{name}** — Controlled by {faction_name}")
            elif control and control.get("contested"):
                description.append(f"{current_marker}🟡 **{name}** — CONTESTED")
            else:
                description.append(f"{current_marker}⚪ **{name}** — Neutral")
        
        embed.description = "\n".join(description)
        
        embed.add_field(
            name="📍 Legend",
            value="🔴 Controlled by faction\n🟡 Contested territory\n⚪ Neutral zone\n📍 Your location",
            inline=False
        )
        
        embed.set_footer(text="Faction wars rage. Claim territory with /faction claim")
        
        return embed

    @app_commands.command(name="districts", description="View all districts and unlock requirements")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    async def districts(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Show all 6 districts with lock status and progress bars"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        current_district = player_data.get("district", 1)
        rep_rank = player_data.get("rep_rank", 1)
        wallet = player_data.get("wallet", 0)
        
        embed = discord.Embed(
            title="🏙️ Simora City Districts",
            description="Explore the six districts of the city. Each offers unique opportunities.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        district_descriptions = {
            1: "The heart of the city's underbelly. Ray runs operations here. Low risk, steady income.",
            2: "Corporate towers and government buildings. Ms. Chen oversees bureaucracy. High stability.",
            3: "Where fortunes are made and lost. The Broker watches the markets. High risk, high reward.",
            4: "The hidden world beneath. Ghost moves in shadows. Illegal opportunities await.",
            5: "Industry and logistics. Marco keeps things moving. Passive income hub.",
            6: "Neon lights and high stakes. Lucky Lou's casino. Gambling and luxury."
        }
        
        for district_id in range(1, 7):
            name = self.district_names.get(district_id, "Unknown")
            is_current = district_id == current_district
            is_unlocked = district_id == 1
            
            if district_id > 1:
                req = self.district_requirements.get(district_id)
                if req:
                    rep_ok = rep_rank >= req["rep_rank"]
                    sc_ok = wallet >= req["sc"]
                    is_unlocked = rep_ok and sc_ok
            
            status = []
            if is_current:
                status.append("📍 **CURRENT LOCATION**")
            if not is_unlocked and district_id > 1:
                status.append("🔒 **LOCKED**")
            
            status_text = " · ".join(status) if status else "✅ Unlocked"
            
            field_value = f"*{district_descriptions.get(district_id, 'Explore this district.')}*\n"
            
            if district_id > 1 and not is_unlocked:
                req = self.district_requirements.get(district_id)
                if req:
                    rep_progress = min(100, int(rep_rank / req["rep_rank"] * 100))
                    sc_progress = min(100, int(wallet / req["sc"] * 100))
                    
                    field_value += f"\n**Requirements:**"
                    field_value += f"\n• Reputation Rank {req['rep_rank']} ({rep_rank}/{req['rep_rank']}) {progress_bar(rep_progress, 8)}"
                    field_value += f"\n• {format_sc(req['sc'])} ({format_sc(wallet)}/{format_sc(req['sc'])}) {progress_bar(sc_progress, 8)}"
            
            embed.add_field(
                name=f"{'📍 ' if is_current else ''}{name}",
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text="Travel to unlocked districts with /travel")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="whereami", description="Get detailed info about your current district")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def whereami(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Show current district, NPC, activities, and active events"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        current_district = player_data.get("district", 1)
        district_name = self.district_names.get(current_district, "Unknown")
        npc_id = self.district_npcs.get(current_district, "ray")
        
        npc_data = await self.bot.services.ai.get_npc_profile(npc_id)
        npc_name = npc_data.get("name", npc_id.title()) if npc_data else npc_id.title()
        
        district_control = await self.bot.services.faction.get_district_control_map()
        control = district_control.get(current_district) if district_control else None
        
        active_events = await self.bot.services.world.get_active_events_in_district(current_district)
        
        activities = self.district_activities.get(current_district, ["Explore the area"])
        
        embed = discord.Embed(
            title=f"📍 {district_name}",
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if control and control.get("faction_name"):
            embed.add_field(
                name="⚔️ Faction Control",
                value=f"Controlled by **{control['faction_name']}**\nControlled since {control.get('controlled_since', 'unknown')}",
                inline=False
            )
        elif control and control.get("contested"):
            embed.add_field(
                name="⚔️ Territory Status",
                value="🟡 **CONTESTED** - Turf war in progress!",
                inline=False
            )
        
        npc_line = await self.bot.services.ai.generate_npc_line(
            npc_id,
            {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": current_district, "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Player is asking where they are. They are in {district_name}. Tell them something about your district."
        )
        
        embed.add_field(
            name=f"💬 {npc_name} says",
            value=f"*{npc_line}*",
            inline=False
        )
        
        embed.add_field(
            name="🏃 Things to do",
            value="\n".join([f"• {a}" for a in activities[:4]]),
            inline=False
        )
        
        if active_events:
            events_text = []
            for event in active_events[:3]:
                events_text.append(f"**{event['name']}** — {event.get('description', 'Active now')}")
            embed.add_field(
                name="🎪 Active Events",
                value="\n".join(events_text),
                inline=False
            )
        
        adjacent = self._get_adjacent_districts(current_district)
        if adjacent:
            embed.add_field(
                name="🚪 Adjacent districts",
                value=", ".join([self.district_names.get(a, "Unknown") for a in adjacent]),
                inline=False
            )
        
        embed.set_footer(text="Use /travel to move to another district")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        
        if control and control.get("contested"):
            npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
            await npc_delayed.send_line(
                "ghost",
                {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": current_district, "premium_tier": player_data.get("premium_tier", "citizen")},
                f"District {district_name} is contested. Warn the player briefly about the turf war.",
                delay=1.5,
                ephemeral=ephemeral
            )

    def _get_adjacent_districts(self, district: int) -> list:
        """Get adjacent districts for navigation"""
        adjacency = {
            1: [2, 4],
            2: [1, 3, 5],
            3: [2, 6],
            4: [1, 5],
            5: [2, 4, 6],
            6: [3, 5]
        }
        return adjacency.get(district, [])

    @app_commands.command(name="district_info", description="Get detailed info about any district")
    @app_commands.describe(
        district="District number (1-6) or name",
        ephemeral="Hide the response from others (default: False)"
    )
    @app_commands.choices(district=[
        app_commands.Choice(name="🏚️ Slums", value="1"),
        app_commands.Choice(name="🏢 Downtown", value="2"),
        app_commands.Choice(name="💹 Financial District", value="3"),
        app_commands.Choice(name="🌿 Underground", value="4"),
        app_commands.Choice(name="🏭 Industrial Zone", value="5"),
        app_commands.Choice(name="🎰 The Strip", value="6")
    ])
    @requires_profile()
    async def district_info(self, interaction: discord.Interaction, district: str, ephemeral: bool = False):
        """Get detailed info about a specific district without traveling"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        try:
            district_id = int(district)
        except ValueError:
            district_lower = district.lower()
            district_map = {
                "slums": 1, "downtown": 2, "financial": 3, "financial district": 3,
                "underground": 4, "industrial": 5, "industrial zone": 5, "strip": 6, "the strip": 6
            }
            district_id = district_map.get(district_lower)
            if not district_id:
                await interaction.followup.send(
                    "❌ Invalid district. Use 1-6 or name.",
                    ephemeral=ephemeral
                )
                return
        
        if district_id < 1 or district_id > 6:
            await interaction.followup.send(
                "❌ District must be between 1 and 6.",
                ephemeral=ephemeral
            )
            return
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        rep_rank = player_data.get("rep_rank", 1)
        wallet = player_data.get("wallet", 0)
        
        district_name = self.district_names.get(district_id, "Unknown")
        npc_id = self.district_npcs.get(district_id, "ray")
        
        npc_data = await self.bot.services.ai.get_npc_profile(npc_id)
        npc_name = npc_data.get("name", npc_id.title()) if npc_data else npc_id.title()
        
        district_control = await self.bot.services.faction.get_district_control_map()
        control = district_control.get(district_id) if district_control else None
        
        activities = self.district_activities.get(district_id, ["Explore the area"])
        
        embed = discord.Embed(
            title=f"📋 {district_name}",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if district_id > 1:
            req = self.district_requirements.get(district_id)
            if req:
                rep_ok = rep_rank >= req["rep_rank"]
                sc_ok = wallet >= req["sc"]
                is_unlocked = rep_ok and sc_ok
                
                if is_unlocked:
                    embed.add_field(
                        name="🔓 Status",
                        value="✅ Unlocked",
                        inline=True
                    )
                else:
                    rep_progress = min(100, int(rep_rank / req["rep_rank"] * 100))
                    sc_progress = min(100, int(wallet / req["sc"] * 100))
                    embed.add_field(
                        name="🔒 Locked",
                        value=(
                            f"**Requirements:**\n"
                            f"• Reputation Rank {req['rep_rank']} ({rep_rank}/{req['rep_rank']})\n"
                            f"  {progress_bar(rep_progress, 10)}\n"
                            f"• {format_sc(req['sc'])} ({format_sc(wallet)}/{format_sc(req['sc'])})\n"
                            f"  {progress_bar(sc_progress, 10)}"
                        ),
                        inline=False
                    )
        
        if control and control.get("faction_name"):
            embed.add_field(
                name="⚔️ Controlled by",
                value=f"**{control['faction_name']}**\nSince {control.get('controlled_since', 'unknown')}",
                inline=True
            )
        elif control and control.get("contested"):
            embed.add_field(
                name="⚔️ Status",
                value="🟡 CONTESTED",
                inline=True
            )
        
        embed.add_field(
            name="💬 Resident NPC",
            value=f"**{npc_name}**",
            inline=True
        )
        
        embed.add_field(
            name="🏃 Activities",
            value="\n".join([f"• {a}" for a in activities[:5]]),
            inline=False
        )
        
        npc_line = await self.bot.services.ai.generate_npc_line(
            npc_id,
            {"username": interaction.user.name, "reputation": rep_rank, "rep_rank": rep_rank, "district": district_id, "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Player is asking about {district_name}. Give a brief, enticing description of your district."
        )
        
        embed.add_field(
            name=f"💬 A word from {npc_name}",
            value=f"*{npc_line}*",
            inline=False
        )
        
        embed.set_footer(text=f"Use /travel {district_id} to go here")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)


async def setup(bot):
    await bot.add_cog(TravelCog(bot))