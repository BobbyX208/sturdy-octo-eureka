import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import json

from config.settings import Config


class LeaderboardDropdown(discord.ui.Select):
    """Leaderboard category dropdown."""
    
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="💰 Wealth", description="Richest players in Simora", emoji="💰"),
            discord.SelectOption(label="⭐ Reputation", description="Most respected citizens", emoji="⭐"),
            discord.SelectOption(label="🏪 Businesses", description="Most successful entrepreneurs", emoji="🏪"),
            discord.SelectOption(label="💎 Prestige", description="Most reborn legends", emoji="💎"),
            discord.SelectOption(label="🔪 Heists", description="Biggest scores", emoji="🔪"),
        ]
        super().__init__(placeholder="Select leaderboard type...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle leaderboard selection."""
        
        await interaction.response.defer(ephemeral=True)
        
        category = self.values[0]
        
        sort_map = {
            "💰 Wealth": "wallet + bank",
            "⭐ Reputation": "reputation",
            "🏪 Businesses": "business_count",
            "💎 Prestige": "prestige",
            "🔪 Heists": "heist_count"
        }
        
        sort_field = sort_map.get(category, "wallet + bank")
        
        conn = await self.bot.db.acquire()
        try:
            if category == "🏪 Businesses":
                rows = await conn.fetch("""
                    SELECT p.username, COUNT(b.id) as count
                    FROM players p
                    LEFT JOIN businesses b ON b.discord_id = p.discord_id
                    WHERE p.is_banned = FALSE
                    GROUP BY p.discord_id, p.username
                    ORDER BY count DESC
                    LIMIT 10
                """)
            elif category == "🔪 Heists":
                rows = await conn.fetch("""
                    SELECT p.username, COUNT(h.id) as count
                    FROM players p
                    LEFT JOIN heist_sessions h ON h.initiator_id = p.discord_id
                    WHERE p.is_banned = FALSE AND h.state = 'completed'
                    GROUP BY p.discord_id, p.username
                    ORDER BY count DESC
                    LIMIT 10
                """)
            else:
                rows = await conn.fetch(f"""
                    SELECT username, {sort_field} as value
                    FROM players
                    WHERE is_banned = FALSE
                    ORDER BY value DESC
                    LIMIT 10
                """)
        finally:
            await self.bot.db.release(conn)
        
        embed = discord.Embed(
            title=f"🏆 {category} Leaderboard",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        description = ""
        for i, row in enumerate(rows, 1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            medal = medals.get(i, f"{i}.")
            value = row.get("value") or row.get("count", 0)
            username = row["username"]
            
            if category in ["💰 Wealth", "⭐ Reputation"]:
                value_str = f"{value:,}"
            else:
                value_str = str(value)
            
            description += f"{medal} **{username}** - {value_str}\n"
        
        embed.description = description or "No data available"
        
        await interaction.followup.send(embed=embed, ephemeral=True)


class StocksDropdown(discord.ui.Select):
    """Stocks dropdown."""
    
    def __init__(self, bot):
        self.bot = bot
        self.companies = [
            ("chen_enterprises", "🏢 Chen Enterprises"),
            ("industrial_steel", "🏭 Industrial Steel"),
            ("strip_entertainment", "🎰 Strip Entertainment"),
            ("shadow_holdings", "🌑 Shadow Holdings"),
            ("simora_bank", "🏦 Simora Bank"),
            ("tech_core", "💻 Tech Core"),
            ("slums_renewal", "🏚️ Slums Renewal"),
            ("district_logistics", "🚚 District Logistics"),
            ("heist_insurance", "🔒 Heist Insurance"),
            ("faction_warfare", "⚔️ Faction Warfare"),
        ]
        
        options = [
            discord.SelectOption(label=name, value=company_id, emoji=emoji)
            for company_id, name in self.companies
        ]
        
        super().__init__(placeholder="Select stock to view...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle stock selection."""
        
        await interaction.response.defer(ephemeral=True)
        
        company_id = self.values[0]
        
        conn = await self.bot.db.acquire()
        try:
            price = await conn.fetchval("""
                SELECT price FROM stock_prices
                WHERE company_id = $1
                ORDER BY recorded_at DESC
                LIMIT 1
            """, company_id)
            
            yesterday = await conn.fetchval("""
                SELECT price FROM stock_prices
                WHERE company_id = $1 AND recorded_at < NOW() - INTERVAL '24 hours'
                ORDER BY recorded_at DESC
                LIMIT 1
            """, company_id)
        finally:
            await self.bot.db.release(conn)
            
            company_name = next((name for cid, name in self.companies if cid == company_id), company_id)
        
        if not price:
            await interaction.followup.send("❌ No stock data available.", ephemeral=True)
            return
        
        change = price - (yesterday or price)
        change_percent = (change / (yesterday or price)) * 100 if (yesterday or price) > 0 else 0
        
        color = discord.Color.green() if change >= 0 else discord.Color.red()
        emoji = "📈" if change >= 0 else "📉"
        
        embed = discord.Embed(
            title=f"{emoji} {company_name}",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="Current Price", value=f"{price} SC", inline=True)
        embed.add_field(name="24h Change", value=f"{change:+,} SC ({change_percent:+.1f}%)", inline=True)
        
        player = await self.bot.services.player.get(interaction.user.id)
        if player and player.get("premium_tier") in ["elite", "obsidian"]:
            embed.add_field(
                name="📊 Analyst Note",
                value="*Premium users can use /analyst for detailed reports*",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


class WebhooksCog(commands.Cog):
    """Webhook manager for public channels."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.webhooks")
        self.market_news_task.start()
    
    @tasks.loop(hours=6)
    async def market_news_task(self):
        """Post market news every 6 hours."""
        
        guild = self.bot.get_guild(Config.OFFICIAL_GUILD_ID)
        if not guild:
            return
        
        channel_id = Config.CITY_FEED_CHANNEL_ID
        if not channel_id:
            return
        
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        
        headlines = await self.bot.services.ai.generate_market_headlines()
        
        webhooks = await channel.webhooks()
        webhook = webhooks[0] if webhooks else await channel.create_webhook(name="Market News")
        
        for headline in headlines[:3]:
            emoji = "📈" if headline["direction"] == "positive" else "📉" if headline["direction"] == "negative" else "📊"
            content = f"{emoji} **{headline['headline']}**\n*{headline['sector']} sector shows {headline['direction']} movement*"
            
            await webhook.send(content, username="SimCoin Market News", avatar_url=None)
        
        self.logger.info("Market news posted")
    
    @app_commands.command(name="webhook_rules", description="[MOD] Post rules via webhook")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to post rules in")
    async def webhook_rules(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel
    ):
        """Post server rules via webhook."""
        
        await interaction.response.defer(ephemeral=True)
        
        rules = [
            "**📜 Simora City Rules**",
            "",
            "**1. Be Respectful** - Treat all citizens with respect. Harassment will result in bans.",
            "",
            "**2. No Exploiting** - Using bugs or glitches to gain unfair advantages is prohibited.",
            "",
            "**3. No Spam** - Excessive command usage, self-promotion, or spam will be flagged.",
            "",
            "**4. Fair Play** - Alt accounts, multi-accounting, or account sharing is forbidden.",
            "",
            "**5. Follow Discord TOS** - All Discord Terms of Service apply.",
            "",
            "**6. Have Fun!** - Simora City is meant to be enjoyed. Help make it great!"
        ]
        
        content = "\n".join(rules)
        
        webhooks = await channel.webhooks()
        webhook = webhooks[0] if webhooks else await channel.create_webhook(name="Simora City Rules")
        
        embed = discord.Embed(
            title="🏛️ Simora City Rules",
            description=content,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await webhook.send(embed=embed, username="City Hall", avatar_url=None)
        
        await interaction.followup.send(f"✅ Rules posted to {channel.mention}", ephemeral=True)
    
    @app_commands.command(name="webhook_leaderboard", description="[MOD] Setup leaderboard dropdown")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to put leaderboard dropdown in")
    async def webhook_leaderboard(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel
    ):
        """Create leaderboard dropdown menu."""
        
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title="🏆 Leaderboards",
            description="Select a leaderboard category from the dropdown below to view rankings.",
            color=discord.Color.gold()
        )
        
        view = discord.ui.View()
        view.add_item(LeaderboardDropdown(self.bot))
        
        await channel.send(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Leaderboard dropdown created in {channel.mention}", ephemeral=True)
    
    @app_commands.command(name="webhook_stocks", description="[MOD] Setup stocks dropdown")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to put stocks dropdown in")
    async def webhook_stocks(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel
    ):
        """Create stocks dropdown menu."""
        
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title="📈 Simora Stock Exchange",
            description="Select a stock from the dropdown below to view current price.",
            color=discord.Color.gold()
        )
        
        view = discord.ui.View()
        view.add_item(StocksDropdown(self.bot))
        
        await channel.send(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Stocks dropdown created in {channel.mention}", ephemeral=True)
    
    @app_commands.command(name="webhook_market_news", description="[MOD] Toggle auto market news")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(enable="Enable or disable auto market news")
    async def webhook_market_news(
        self, 
        interaction: discord.Interaction, 
        enable: bool
    ):
        """Toggle auto market news posting."""
        
        await interaction.response.defer(ephemeral=True)
        
        if enable:
            if not self.market_news_task.is_running():
                self.market_news_task.start()
                await interaction.followup.send("✅ Auto market news enabled (every 6 hours)", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ Auto market news is already running", ephemeral=True)
        else:
            if self.market_news_task.is_running():
                self.market_news_task.stop()
                await interaction.followup.send("⏸️ Auto market news disabled", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ Auto market news is not running", ephemeral=True)
    
    @app_commands.command(name="webhook_test", description="[MOD] Test webhook connection")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to test in")
    async def webhook_test(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel
    ):
        """Test webhook connection."""
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            webhooks = await channel.webhooks()
            
            if webhooks:
                await interaction.followup.send(f"✅ Webhook found: {webhooks[0].name}", ephemeral=True)
            else:
                webhook = await channel.create_webhook(name="Test Webhook")
                await webhook.send("Test message")
                await webhook.delete()
                
                await interaction.followup.send("✅ Test webhook created and deleted successfully", ephemeral=True)
                
        except Exception as e:
            await interaction.followup.send(f"❌ Webhook test failed: {e}", ephemeral=True)
    
    @market_news_task.before_loop
    async def before_market_news(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(WebhooksCog(bot))