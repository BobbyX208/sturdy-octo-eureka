import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import Config


class ReportsCog(commands.Cog):
    """Daily and weekly reports."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.reports")
        self.daily_report.start()
    
    def _get_report_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get daily report channel."""
        if Config.MOD_DAILY_CHANNEL_ID:
            return guild.get_channel(Config.MOD_DAILY_CHANNEL_ID)
        return None
    
    async def _generate_daily_report(self, guild: discord.Guild) -> discord.Embed:
        """Generate daily report embed."""
        
        conn = await self.bot.db.acquire()
        try:
            total_players = await conn.fetchval("SELECT COUNT(*) FROM players")
            active_today = await conn.fetchval("""
                SELECT COUNT(DISTINCT discord_id) FROM interaction_log 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            new_today = await conn.fetchval("""
                SELECT COUNT(*) FROM players 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            
            total_sc = await conn.fetchval("SELECT COALESCE(SUM(wallet + bank), 0) FROM players")
            total_transactions = await conn.fetchval("""
                SELECT COUNT(*) FROM transactions 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            
            top_earner = await conn.fetchrow("""
                SELECT username, total_earned FROM players 
                ORDER BY total_earned DESC LIMIT 1
            """)
            
            ai_calls = await conn.fetchval("""
                SELECT COUNT(*) FROM ai_response_cache 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            cache_hits = await conn.fetchval("""
                SELECT COALESCE(SUM(hit_count), 0) FROM ai_response_cache 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            
            anticheat_cog = self.bot.get_cog("AntiCheatCog")
            pending_flags = len(anticheat_cog.pending_flags) if anticheat_cog else 0
            
            open_tickets = await conn.fetchval("""
                SELECT COUNT(*) FROM tickets WHERE status = 'open'
            """)
            closed_today = await conn.fetchval("""
                SELECT COUNT(*) FROM tickets 
                WHERE closed_at > NOW() - INTERVAL '24 hours'
            """)
        finally:
            await self.bot.db.release(conn)
        
        embed = discord.Embed(
            title=f"📊 SimCoin Daily Report",
            description=f"**{datetime.now(timezone.utc).strftime('%B %d, %Y')}**",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="👥 Players",
            value=f"**Total:** {total_players}\n**Active Today:** {active_today}\n**New Today:** {new_today}",
            inline=True
        )
        
        embed.add_field(
            name="💰 Economy",
            value=f"**SC in Circulation:** {total_sc:,}\n**Transactions (24h):** {total_transactions}\n**Top Earner:** {top_earner['username'] if top_earner else 'N/A'}",
            inline=True
        )
        
        embed.add_field(
            name="🤖 AI",
            value=f"**API Calls:** {ai_calls}\n**Cache Hits:** {cache_hits}\n**Cache Rate:** {int(cache_hits / ai_calls * 100) if ai_calls > 0 else 0}%",
            inline=True
        )
        
        embed.add_field(
            name="🚩 Moderation",
            value=f"**Pending Flags:** {pending_flags}\n**Open Tickets:** {open_tickets}\n**Closed Today:** {closed_today}",
            inline=True
        )
        
        conn = await self.bot.db.acquire()
        try:
            top_3 = await conn.fetch("""
                SELECT username, wallet + bank as total FROM players 
                WHERE is_banned = FALSE
                ORDER BY total DESC LIMIT 3
            """)
        finally:
            await self.bot.db.release(conn)
        
        leaderboard = ""
        for i, player in enumerate(top_3, 1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            leaderboard += f"{medals.get(i, '•')} {player['username']}: {player['total']:,} SC\n"
        
        embed.add_field(name="📊 Leaderboard", value=leaderboard or "No data", inline=False)
        
        embed.set_footer(text="SimCoin Moderation System")
        
        return embed
    
    @tasks.loop(hours=24)
    async def daily_report(self):
        """Send daily report at 8am UTC."""
        
        now = datetime.now(timezone.utc)
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        
        if now >= target:
            target += timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        guild = self.bot.get_guild(Config.OFFICIAL_GUILD_ID)
        if not guild:
            self.logger.error("Official guild not found")
            return
        
        channel = self._get_report_channel(guild)
        if not channel:
            self.logger.error("Report channel not found")
            return
        
        embed = await self._generate_daily_report(guild)
        await channel.send(embed=embed)
        
        self.logger.info("Daily report sent")
    
    @app_commands.command(name="report_daily", description="[MOD] Trigger daily report now")
    @app_commands.default_permissions(administrator=True)
    async def report_daily(self, interaction: discord.Interaction):
        """Trigger daily report immediately."""
        
        await interaction.response.defer(ephemeral=True)
        
        embed = await self._generate_daily_report(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        self.logger.info(f"Manual daily report triggered by {interaction.user.id}")
    
    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ReportsCog(bot))