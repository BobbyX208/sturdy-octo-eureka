# mod_bot/cogs/admin.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import Config
from utils.checks import requires_staff, requires_dev


class AdminCog(commands.Cog):
    """Admin panel commands for moderation."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.admin")
        self.action_history = []
    
    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get mod actions log channel."""
        if Config.MOD_ACTIONS_CHANNEL_ID:
            return guild.get_channel(Config.MOD_ACTIONS_CHANNEL_ID)
        return None
    
    async def _log_action(self, guild: discord.Guild, moderator: discord.User, action: str, target: str, reason: str = None):
        """Log admin action to mod-actions channel."""
        channel = self._get_log_channel(guild)
        if channel:
            embed = discord.Embed(
                title="🔨 Admin Action",
                description=f"**Action:** {action}\n**Mod:** {moderator.mention}\n**Target:** {target}",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            await channel.send(embed=embed)
        
        # Store in history
        self.action_history.append({
            "moderator": moderator.id,
            "action": action,
            "target": target,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc)
        })
        # Keep last 100 actions
        self.action_history = self.action_history[-100:]
    
    @app_commands.command(name="admin_give", description="[DEV] Give SimCoins to a player")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player to give SC to", amount="Amount of SC to give", reason="Reason for giving")
    async def admin_give(
        self, 
        interaction: discord.Interaction, 
        user: discord.User, 
        amount: int,
        reason: Optional[str] = None
    ):
        """Give SC to a player."""
        
        await interaction.response.defer(ephemeral=True)
        
        if amount <= 0:
            await interaction.followup.send("❌ Amount must be positive.", ephemeral=True)
            return
        
        player = await self.bot.services.player.get(user.id)
        
        if not player:
            await interaction.followup.send(f"❌ Player {user.mention} not found.", ephemeral=True)
            return
        
        # Update balance
        result = await self.bot.services.player.update_balance(user.id, wallet_delta=amount)
        
        # Log transaction
        await self.bot.services.player.queries.add_transaction(
            user.id, amount, result["wallet"],
            "admin_grant", f"Admin grant: {reason or 'No reason provided'}"
        )
        
        # Log action
        await self._log_action(
            interaction.guild, 
            interaction.user, 
            f"Give {amount} SC", 
            user.mention,
            reason
        )
        
        embed = discord.Embed(
            title="✅ SC Granted",
            description=f"Gave {amount} SC to {user.mention}\nNew balance: {result['wallet']} SC",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        try:
            dm_embed = discord.Embed(
                title="💰 Admin Grant",
                description=f"You received {amount} SC from an admin.\n**Reason:** {reason or 'No reason provided'}",
                color=discord.Color.green()
            )
            await user.send(embed=dm_embed)
        except:
            pass
    
    @app_commands.command(name="admin_take", description="[DEV] Take SimCoins from a player")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player to take SC from", amount="Amount of SC to take", reason="Reason for taking")
    async def admin_take(
        self, 
        interaction: discord.Interaction, 
        user: discord.User, 
        amount: int,
        reason: Optional[str] = None
    ):
        """Take SC from a player."""
        
        await interaction.response.defer(ephemeral=True)
        
        if amount <= 0:
            await interaction.followup.send("❌ Amount must be positive.", ephemeral=True)
            return
        
        player = await self.bot.services.player.get(user.id)
        
        if not player:
            await interaction.followup.send(f"❌ Player {user.mention} not found.", ephemeral=True)
            return
        
        # Update balance
        result = await self.bot.services.player.update_balance(user.id, wallet_delta=-amount)
        
        # Log transaction
        await self.bot.services.player.queries.add_transaction(
            user.id, -amount, result["wallet"],
            "admin_deduct", f"Admin deduction: {reason or 'No reason provided'}"
        )
        
        await self._log_action(
            interaction.guild, 
            interaction.user, 
            f"Take {amount} SC", 
            user.mention,
            reason
        )
        
        embed = discord.Embed(
            title="✅ SC Removed",
            description=f"Removed {amount} SC from {user.mention}\nNew balance: {result['wallet']} SC",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        try:
            dm_embed = discord.Embed(
                title="⚠️ Admin Deduction",
                description=f"{amount} SC was removed from your account.\n**Reason:** {reason or 'No reason provided'}",
                color=discord.Color.orange()
            )
            await user.send(embed=dm_embed)
        except:
            pass
    
    @app_commands.command(name="admin_ban", description="[DEV] Ban a player from the bot")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player to ban", reason="Reason for ban")
    async def admin_ban(
        self, 
        interaction: discord.Interaction, 
        user: discord.User, 
        reason: str
    ):
        """Ban a player from using the bot."""
        
        await interaction.response.defer(ephemeral=True)
        
        player = await self.bot.services.player.get(user.id)
        
        if not player:
            await interaction.followup.send(f"❌ Player {user.mention} not found.", ephemeral=True)
            return
        
        conn = await self.bot.db.acquire()
        try:
            await conn.execute("""
                UPDATE players SET is_banned = TRUE, ban_reason = $2 WHERE discord_id = $1
            """, user.id, reason)
        finally:
            await self.bot.db.release(conn)
        
        await self._log_action(
            interaction.guild, 
            interaction.user, 
            "Ban", 
            user.mention,
            reason
        )
        
        embed = discord.Embed(
            title="🔨 Player Banned",
            description=f"{user.mention} has been banned from SimCoin.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        try:
            dm_embed = discord.Embed(
                title="🔨 You have been banned",
                description=f"You have been banned from SimCoin.\n**Reason:** {reason}",
                color=discord.Color.red()
            )
            await user.send(embed=dm_embed)
        except:
            pass
    
    @app_commands.command(name="admin_unban", description="[DEV] Unban a player")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player to unban", reason="Reason for unban")
    async def admin_unban(
        self, 
        interaction: discord.Interaction, 
        user: discord.User, 
        reason: str = "No reason provided"
    ):
        """Unban a player."""
        
        await interaction.response.defer(ephemeral=True)
        
        conn = await self.bot.db.acquire()
        try:
            await conn.execute("""
                UPDATE players SET is_banned = FALSE, ban_reason = NULL WHERE discord_id = $1
            """, user.id)
        finally:
            await self.bot.db.release(conn)
        
        await self._log_action(
            interaction.guild, 
            interaction.user, 
            "Unban", 
            user.mention,
            reason
        )
        
        embed = discord.Embed(
            title="✅ Player Unbanned",
            description=f"{user.mention} has been unbanned from SimCoin.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        try:
            dm_embed = discord.Embed(
                title="✅ You have been unbanned",
                description=f"You have been unbanned from SimCoin.\n**Reason:** {reason}",
                color=discord.Color.green()
            )
            await user.send(embed=dm_embed)
        except:
            pass
    
    @app_commands.command(name="admin_premium", description="[DEV] Grant premium tier to a player")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player", tier="Premium tier (resident/elite/obsidian)", days="Number of days")
    async def admin_premium(
        self, 
        interaction: discord.Interaction, 
        user: discord.User, 
        tier: str, 
        days: int,
        reason: str = "Admin grant"
    ):
        """Grant premium tier to a player."""
        
        await interaction.response.defer(ephemeral=True)
        
        valid_tiers = ["resident", "elite", "obsidian"]
        
        if tier.lower() not in valid_tiers:
            await interaction.followup.send(f"❌ Invalid tier. Choose: {', '.join(valid_tiers)}", ephemeral=True)
            return
        
        player = await self.bot.services.player.get(user.id)
        
        if not player:
            await interaction.followup.send(f"❌ Player {user.mention} not found.", ephemeral=True)
            return
        
        await self.bot.services.player.queries.update_premium(user.id, tier.lower(), days)
        
        await self._log_action(
            interaction.guild, 
            interaction.user, 
            f"Premium {tier.title()} ({days} days)", 
            user.mention,
            reason
        )
        
        embed = discord.Embed(
            title="💎 Premium Granted",
            description=f"{user.mention} now has **{tier.title()}** tier for {days} days.",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        try:
            dm_embed = discord.Embed(
                title="💎 Premium Tier Granted",
                description=f"You have been granted **{tier.title()}** tier for {days} days.",
                color=discord.Color.gold()
            )
            await user.send(embed=dm_embed)
        except:
            pass
    
    @app_commands.command(name="admin_stats", description="[DEV] Show bot statistics")
    @app_commands.default_permissions(administrator=True)
    async def admin_stats(self, interaction: discord.Interaction):
        """Show bot statistics."""
        
        await interaction.response.defer(ephemeral=True)
        
        conn = await self.bot.db.acquire()
        try:
            total_players = await conn.fetchval("SELECT COUNT(*) FROM players")
            active_today = await conn.fetchval("""
                SELECT COUNT(DISTINCT discord_id) FROM interaction_log 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            banned = await conn.fetchval("SELECT COUNT(*) FROM players WHERE is_banned = TRUE")
            premium = await conn.fetchval("SELECT COUNT(*) FROM players WHERE premium_tier != 'citizen'")
        finally:
            await self.bot.db.release(conn)
        
        conn = await self.bot.db.acquire()
        try:
            total_sc = await conn.fetchval("SELECT COALESCE(SUM(wallet + bank), 0) FROM players")
            avg_sc = await conn.fetchval("SELECT COALESCE(AVG(wallet + bank), 0) FROM players")
        finally:
            await self.bot.db.release(conn)
        
        embed = discord.Embed(
            title="📊 SimCoin Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="👥 Total Players", value=str(total_players), inline=True)
        embed.add_field(name="📈 Active Today", value=str(active_today), inline=True)
        embed.add_field(name="🚫 Banned", value=str(banned), inline=True)
        embed.add_field(name="💎 Premium", value=str(premium), inline=True)
        embed.add_field(name="💰 SC in Circulation", value=f"{total_sc:,}", inline=True)
        embed.add_field(name="📊 Average Wealth", value=f"{int(avg_sc):,}", inline=True)
        embed.add_field(name="🌐 Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="⏱️ Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="admin_release_jail", description="[DEV] Release a player from jail")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The player to release")
    async def admin_release_jail(
        self, 
        interaction: discord.Interaction, 
        user: discord.User
    ):
        """Release a player from jail."""
        
        await interaction.response.defer(ephemeral=True)
        
        player = await self.bot.services.player.get(user.id)
        
        if not player:
            await interaction.followup.send(f"❌ Player {user.mention} not found.", ephemeral=True)
            return
        
        if not player.get("is_jailed", False):
            await interaction.followup.send(f"⚠️ {user.mention} is not in jail.", ephemeral=True)
            return
        
        await self.bot.services.player.queries.release_jail(user.id)
        
        await self._log_action(
            interaction.guild, 
            interaction.user, 
            "Release from Jail", 
            user.mention
        )
        
        embed = discord.Embed(
            title="🔓 Player Released",
            description=f"{user.mention} has been released from jail.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        try:
            dm_embed = discord.Embed(
                title="🔓 You have been released",
                description="An admin has released you from jail.",
                color=discord.Color.green()
            )
            await user.send(embed=dm_embed)
        except:
            pass


async def setup(bot):
    await bot.add_cog(AdminCog(bot))