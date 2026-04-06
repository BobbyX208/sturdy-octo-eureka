import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import json

from config.settings import Config


class AntiCheatCog(commands.Cog):
    """Anti-cheat monitoring and flag management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.anticheat")
        self.pending_flags = []
        self.dismissed_flags = {}
        self.flag_thresholds = {
            "income_spike": 4.0,
            "command_spam": 30,
            "balance_jump": 250000,
            "new_account": 3,
            "heist_spam": 3,
            "transfer_pattern": 10,
        }
    
    def _get_alert_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get mod alerts channel."""
        if Config.MOD_ALERTS_CHANNEL_ID:
            return guild.get_channel(Config.MOD_ALERTS_CHANNEL_ID)
        return None
    
    def _get_mod_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Get mod role to ping."""
        if Config.MOD_ROLE_ID:
            return guild.get_role(Config.MOD_ROLE_ID)
        return None
    
    async def _send_flag(
        self, 
        guild: discord.Guild, 
        user: discord.User, 
        flag_type: str, 
        details: str,
        severity: str = "medium"
    ):
        """Send flag to mod alerts channel with ping."""
        channel = self._get_alert_channel(guild)
        mod_role = self._get_mod_role(guild)
        
        if not channel:
            return
        
        colors = {
            "low": discord.Color.blue(),
            "medium": discord.Color.gold(),
            "high": discord.Color.red()
        }
        
        embed = discord.Embed(
            title="🚨 ANTI-CHEAT FLAG",
            description=f"**Type:** {flag_type}\n**User:** {user.mention}\n**Details:** {details}",
            color=colors.get(severity, discord.Color.gold()),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_footer(text=f"User ID: {user.id}")
        
        view = discord.ui.View(timeout=3600)
        review_button = discord.ui.Button(
            label="Review", 
            style=discord.ButtonStyle.primary,
            custom_id=f"flag_review_{user.id}_{flag_type}"
        )
        dismiss_button = discord.ui.Button(
            label="Dismiss", 
            style=discord.ButtonStyle.secondary,
            custom_id=f"flag_dismiss_{user.id}_{flag_type}"
        )
        view.add_item(review_button)
        view.add_item(dismiss_button)
        
        flag = {
            "id": len(self.pending_flags) + 1,
            "user_id": user.id,
            "user_name": str(user),
            "type": flag_type,
            "details": details,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc),
            "reviewed": False
        }
        self.pending_flags.append(flag)
        
        ping = mod_role.mention if mod_role else ""
        await channel.send(f"{ping}", embed=embed, view=view)
        
        self.logger.info(f"Flag sent: {flag_type} for {user.id}")
    
    async def check_income_spike(self, user_id: int, guild: discord.Guild, user: discord.User):
        """Check for income spikes."""
        conn = await self.bot.db.acquire()
        try:
            avg = await conn.fetchval("""
                SELECT AVG(daily_earned) FROM players 
                WHERE discord_id = $1 
                AND created_at > NOW() - INTERVAL '7 days'
            """, user_id)
            
            today = await conn.fetchval("""
                SELECT daily_earned FROM players WHERE discord_id = $1
            """, user_id)
        finally:
            await self.bot.db.release(conn)
        
        if avg and today > avg * self.flag_thresholds["income_spike"]:
            await self._send_flag(
                guild, user, 
                "Income Spike", 
                f"Earned {today} SC today vs average {int(avg)} SC",
                "medium"
            )
    
    async def check_balance_jump(self, user_id: int, guild: discord.Guild, user: discord.User):
        """Check for sudden balance jumps."""
        conn = await self.bot.db.acquire()
        try:
            one_hour_ago = await conn.fetchval("""
                SELECT balance_after FROM transactions 
                WHERE discord_id = $1 
                AND created_at > NOW() - INTERVAL '1 hour'
                ORDER BY created_at ASC LIMIT 1
            """, user_id)
            
            current = await conn.fetchval("""
                SELECT wallet + bank FROM players WHERE discord_id = $1
            """, user_id)
        finally:
            await self.bot.db.release(conn)
        
        if one_hour_ago and current - one_hour_ago > self.flag_thresholds["balance_jump"]:
            await self._send_flag(
                guild, user,
                "Balance Jump",
                f"Gained {current - one_hour_ago} SC in 1 hour",
                "high"
            )
    
    async def check_new_account(self, user_id: int, guild: discord.Guild, user: discord.User):
        """Flag new accounts for monitoring."""
        async with self.bot.db.acquire() as conn:
            created = await conn.fetchval("""
                SELECT created_at FROM players WHERE discord_id = $1
            """, user_id)
            
            if created and (datetime.now(timezone.utc) - created).days < self.flag_thresholds["new_account"]:
                await self._send_flag(
                    guild, user,
                    "New Account",
                    f"Account age: {(datetime.now(timezone.utc) - created).days} days",
                    "low"
                )
    
    @app_commands.command(name="flags_list", description="[MOD] List pending flags")
    @app_commands.default_permissions(administrator=True)
    async def flags_list(self, interaction: discord.Interaction):
        """List all pending flags."""
        
        await interaction.response.defer(ephemeral=True)
        
        if not self.pending_flags:
            await interaction.followup.send("✅ No pending flags.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🚩 Pending Flags",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        for flag in self.pending_flags[-10:]:
            embed.add_field(
                name=f"#{flag['id']} - {flag['type']}",
                value=f"User: {flag['user_name']}\n{flag['details']}\nTime: {flag['timestamp'].strftime('%H:%M')}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="flags_review", description="[MOD] Review and approve a flag")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(flag_id="Flag ID to review", action="approve or dismiss")
    async def flags_review(
        self, 
        interaction: discord.Interaction, 
        flag_id: int, 
        action: str
    ):
        """Review a flag."""
        
        await interaction.response.defer(ephemeral=True)
        
        flag = None
        for f in self.pending_flags:
            if f["id"] == flag_id:
                flag = f
                break
        
        if not flag:
            await interaction.followup.send(f"❌ Flag #{flag_id} not found.", ephemeral=True)
            return
        
        if flag["reviewed"]:
            await interaction.followup.send(f"⚠️ Flag #{flag_id} already reviewed.", ephemeral=True)
            return
        
        if action.lower() == "approve":
            flag["reviewed"] = True
            flag["approved_by"] = interaction.user.id
            
            channel = interaction.guild.get_channel(Config.MOD_ACTIONS_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="✅ Flag Approved",
                    description=f"**Flag:** {flag['type']}\n**User:** {flag['user_name']}\n**Approved by:** {interaction.user.mention}",
                    color=discord.Color.green()
                )
                await channel.send(embed=embed)
            
            await interaction.followup.send(f"✅ Flag #{flag_id} approved for review.", ephemeral=True)
            
        elif action.lower() == "dismiss":
            flag["reviewed"] = True
            flag["dismissed_by"] = interaction.user.id
            self.dismissed_flags[flag["user_id"]] = datetime.now(timezone.utc)
            
            await interaction.followup.send(f"✅ Flag #{flag_id} dismissed as false positive.", ephemeral=True)
        
        else:
            await interaction.followup.send("❌ Invalid action. Use 'approve' or 'dismiss'.", ephemeral=True)
    
    @app_commands.command(name="flags_threshold", description="[DEV] Adjust flag thresholds")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(threshold="Threshold name", value="New value")
    async def flags_threshold(
        self, 
        interaction: discord.Interaction, 
        threshold: str, 
        value: float
    ):
        """Adjust flag thresholds."""
        
        await interaction.response.defer(ephemeral=True)
        
        if threshold not in self.flag_thresholds:
            await interaction.followup.send(
                f"❌ Invalid threshold. Options: {', '.join(self.flag_thresholds.keys())}",
                ephemeral=True
            )
            return
        
        old = self.flag_thresholds[threshold]
        self.flag_thresholds[threshold] = value
        
        embed = discord.Embed(
            title="⚙️ Threshold Updated",
            description=f"**{threshold}** changed from {old} to {value}",
            color=discord.Color.green()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="flags_history", description="[MOD] Show flag history for a user")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The user to check")
    async def flags_history(
        self, 
        interaction: discord.Interaction, 
        user: discord.User
    ):
        """Show flag history for a user."""
        
        await interaction.response.defer(ephemeral=True)
        
        user_flags = [f for f in self.pending_flags if f["user_id"] == user.id]
        
        if not user_flags:
            await interaction.followup.send(f"✅ No flags for {user.mention}.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🚩 Flag History - {user.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        for flag in user_flags[-10:]:
            status = "✅ Approved" if flag.get("approved_by") else "❌ Dismissed" if flag.get("dismissed_by") else "⏳ Pending"
            embed.add_field(
                name=f"{flag['type']} - {status}",
                value=flag['details'],
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntiCheatCog(bot))