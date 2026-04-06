import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import Config


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.welcome")

    def _get_welcome_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        if Config.WELCOME_CHANNEL_ID:
            return guild.get_channel(Config.WELCOME_CHANNEL_ID)
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != Config.OFFICIAL_GUILD_ID:
            return

        try:
            test_data = {
                "discord_id": member.id,
                "username": member.name,
                "wallet": 0,
                "bank": 0,
                "reputation": 0,
                "rep_rank": 1,
                "district": 1,
                "premium_tier": "citizen",
                "prestige": 0,
                "system_role": "player",
                "is_jailed": False
            }

            welcome_card = await self.bot.services.image.generate_profile_card(test_data)

            embed = discord.Embed(
                title="🏙️ Welcome to Simora City!",
                description="You've been invited to join the SimCoin economy game.\n\n**Get Started:**\n1. Use `/start` to register\n2. Use `/work` to earn your first SimCoins\n3. Use `/travel` to explore districts\n\nJoin other players and build your empire!",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )

            await member.send(embed=embed, file=welcome_card)

        except Exception as e:
            self.logger.error(f"Failed to send welcome DM to {member.id}: {e}")

        channel = self._get_welcome_channel(member.guild)
        if channel:
            welcome_embed = discord.Embed(
                title="🎉 New Citizen Arrives!",
                description=f"Welcome to Simora City, {member.mention}!\nUse `/start` to begin your journey.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            welcome_embed.set_thumbnail(url=member.display_avatar.url)

            await channel.send(embed=welcome_embed)

        self.logger.info(f"Welcomed new member: {member.name}")

    @app_commands.command(name="welcome_preview", description="[MOD] Preview welcome card")
    @app_commands.default_permissions(administrator=True)
    async def welcome_preview(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        test_data = {
            "discord_id": interaction.user.id,
            "username": interaction.user.name,
            "wallet": 0,
            "bank": 0,
            "reputation": 0,
            "rep_rank": 1,
            "district": 1,
            "premium_tier": "citizen",
            "prestige": 0,
            "system_role": "player",
            "is_jailed": False
        }

        card = await self.bot.services.image.generate_profile_card(test_data)

        embed = discord.Embed(
            title="📧 Welcome DM Preview",
            description="New members will receive this DM with their profile card.",
            color=discord.Color.blue()
        )

        await interaction.followup.send(embed=embed, file=card, ephemeral=True)

    @app_commands.command(name="welcome_test", description="[MOD] Send test welcome to a user")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="User to send test welcome to")
    async def welcome_test(
        self,
        interaction: discord.Interaction,
        user: discord.User
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            test_data = {
                "discord_id": user.id,
                "username": user.name,
                "wallet": 0,
                "bank": 0,
                "reputation": 0,
                "rep_rank": 1,
                "district": 1,
                "premium_tier": "citizen",
                "prestige": 0,
                "system_role": "player",
                "is_jailed": False
            }

            card = await self.bot.services.image.generate_profile_card(test_data)

            embed = discord.Embed(
                title="🏙️ Welcome to Simora City! (Test)",
                description="This is a test welcome message.",
                color=discord.Color.gold()
            )

            await user.send(embed=embed, file=card)

            await interaction.followup.send(f"✅ Test welcome sent to {user.mention}", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))