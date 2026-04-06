import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import Config


class RoleSyncCog(commands.Cog):
    """Automatic role sync with official server."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.rolesync")
        self.sync_queue = []
        self._sync_lock = False
    
    def _get_district_role(self, guild: discord.Guild, district: int) -> Optional[discord.Role]:
        """Get role for district."""
        role_mapping = {
            1: Config.DISTRICT_SLUMS_ROLE_ID,
            2: Config.DISTRICT_INDUSTRIAL_ROLE_ID,
            3: Config.DISTRICT_DOWNTOWN_ROLE_ID,
            4: Config.DISTRICT_FINANCIAL_ROLE_ID,
            5: Config.DISTRICT_STRIP_ROLE_ID,
            6: Config.DISTRICT_UNDERGROUND_ROLE_ID,
        }
        
        role_id = role_mapping.get(district)
        if role_id:
            return guild.get_role(role_id)
        return None
    
    def _get_premium_role(self, guild: discord.Guild, tier: str) -> Optional[discord.Role]:
        """Get role for premium tier."""
        role_mapping = {
            "resident": Config.PREMIUM_RESIDENT_ROLE_ID,
            "elite": Config.PREMIUM_ELITE_ROLE_ID,
            "obsidian": Config.PREMIUM_OBSIDIAN_ROLE_ID,
        }
        
        role_id = role_mapping.get(tier)
        if role_id:
            return guild.get_role(role_id)
        return None
    
    async def _sync_player_roles(self, guild: discord.Guild, user_id: int, player_data: dict):
        """Sync a single player's roles."""
        
        member = guild.get_member(user_id)
        if not member:
            return
        
        district_role_ids = [
            Config.DISTRICT_SLUMS_ROLE_ID,
            Config.DISTRICT_INDUSTRIAL_ROLE_ID,
            Config.DISTRICT_DOWNTOWN_ROLE_ID,
            Config.DISTRICT_FINANCIAL_ROLE_ID,
            Config.DISTRICT_STRIP_ROLE_ID,
            Config.DISTRICT_UNDERGROUND_ROLE_ID,
        ]
        
        for role_id in district_role_ids:
            role = guild.get_role(role_id)
            if role and role in member.roles:
                await member.remove_roles(role)
        
        premium_role_ids = [
            Config.PREMIUM_RESIDENT_ROLE_ID,
            Config.PREMIUM_ELITE_ROLE_ID,
            Config.PREMIUM_OBSIDIAN_ROLE_ID,
        ]
        
        for role_id in premium_role_ids:
            role = guild.get_role(role_id)
            if role and role in member.roles:
                await member.remove_roles(role)
        
        district = player_data.get("district", 1)
        district_role = self._get_district_role(guild, district)
        if district_role:
            await member.add_roles(district_role)
        
        premium_tier = player_data.get("premium_tier", "citizen")
        if premium_tier != "citizen":
            premium_role = self._get_premium_role(guild, premium_tier)
            if premium_role:
                await member.add_roles(premium_role)
        
        system_role = player_data.get("system_role", "player")
        if system_role == "beta_tester" and Config.BETA_TESTER_ROLE_ID:
            role = guild.get_role(Config.BETA_TESTER_ROLE_ID)
            if role and role not in member.roles:
                await member.add_roles(role)
        elif Config.BETA_TESTER_ROLE_ID:
            role = guild.get_role(Config.BETA_TESTER_ROLE_ID)
            if role and role in member.roles:
                await member.remove_roles(role)
        
        if system_role in ["mod", "dev"] and Config.MOD_ROLE_ID:
            role = guild.get_role(Config.MOD_ROLE_ID)
            if role and role not in member.roles:
                await member.add_roles(role)
        
        self.logger.info(f"Synced roles for {user_id}: District {district}, Premium {premium_tier}")
    
    @commands.Cog.listener()
    async def on_player_traveled(self, data: dict, event_id: str = None):
        """Listen for player travel events from main bot."""
        
        user_id = data.get("user_id")
        new_district = data.get("new_district")
        
        if not user_id:
            return
        
        guild = self.bot.get_guild(Config.OFFICIAL_GUILD_ID)
        if not guild:
            self.logger.warning("Official guild not found")
            return
        
        player = await self.bot.services.player.get(user_id)
        if not player:
            return
        
        await self._sync_player_roles(guild, user_id, player)
    
    @commands.Cog.listener()
    async def on_player_premium_change(self, data: dict, event_id: str = None):
        """Listen for premium changes."""
        
        user_id = data.get("user_id")
        
        if not user_id:
            return
        
        guild = self.bot.get_guild(Config.OFFICIAL_GUILD_ID)
        if not guild:
            return
        
        player = await self.bot.services.player.get(user_id)
        if not player:
            return
        
        await self._sync_player_roles(guild, user_id, player)
    
    @app_commands.command(name="rolesync_sync", description="[MOD] Force sync a player's roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player to sync")
    async def rolesync_sync(
        self, 
        interaction: discord.Interaction, 
        user: discord.User
    ):
        """Force sync a player's roles."""
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if guild.id != Config.OFFICIAL_GUILD_ID:
            await interaction.followup.send("❌ This command can only be used in the official server.", ephemeral=True)
            return
        
        player = await self.bot.services.player.get(user.id)
        
        if not player:
            await interaction.followup.send(f"❌ Player {user.mention} not found in database.", ephemeral=True)
            return
        
        await self._sync_player_roles(guild, user.id, player)
        
        await interaction.followup.send(f"✅ Synced roles for {user.mention}", ephemeral=True)
    
    @app_commands.command(name="rolesync_sync_all", description="[DEV] Sync all players (use sparingly)")
    @app_commands.default_permissions(administrator=True)
    async def rolesync_sync_all(self, interaction: discord.Interaction):
        """Sync all players (use sparingly - rate limit risk)."""
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if guild.id != Config.OFFICIAL_GUILD_ID:
            await interaction.followup.send("❌ This command can only be used in the official server.", ephemeral=True)
            return
        
        conn = await self.bot.db.acquire()
        try:
            players = await conn.fetch("SELECT discord_id FROM players WHERE is_banned = FALSE")
        finally:
            await self.bot.db.release(conn)
        
        count = 0
        for player in players:
            member = guild.get_member(player["discord_id"])
            if member:
                player_data = await self.bot.services.player.get(player["discord_id"])
                if player_data:
                    await self._sync_player_roles(guild, player["discord_id"], player_data)
                    count += 1
                    await interaction.followup.send(f"Syncing... {count}/{len(players)}", ephemeral=True)
        
        await interaction.followup.send(f"✅ Synced {count} players.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RoleSyncCog(bot))