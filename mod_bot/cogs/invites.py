import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import Config


class InvitesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.invites")
        self.invites = {}
        self.weekly_leaderboard.start()

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(Config.OFFICIAL_GUILD_ID)
        if guild:
            self.invites = await guild.invites()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != Config.OFFICIAL_GUILD_ID:
            return

        new_invites = await member.guild.invites()

        used_invite = None
        for invite in new_invites:
            old_count = next((inv.uses for inv in self.invites if inv.code == invite.code), 0)
            if invite.uses > old_count:
                used_invite = invite
                break

        self.invites = new_invites

        if not used_invite:
            self.logger.warning(f"Could not determine invite for {member.name}")
            return

        inviter_id = used_invite.inviter.id

        inviter_reward = 500
        invitee_reward = 500

        inviter_player = await self.bot.services.player.get(inviter_id)
        if inviter_player:
            await self.bot.services.player.update_balance(inviter_id, wallet_delta=inviter_reward)
            await self.bot.services.player.queries.add_transaction(
                inviter_id, inviter_reward, inviter_player.get("wallet", 0) + inviter_reward,
                "invite_reward", f"Invited {member.name}"
            )

            async with self.bot.db.acquire() as conn:
                await conn.execute("""
                    INSERT INTO invite_tracker (discord_id, invite_code, uses, successful, sc_earned)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (discord_id, invite_code) DO UPDATE
                    SET uses = invite_tracker.uses + $3,
                        successful = invite_tracker.successful + $4,
                        sc_earned = invite_tracker.sc_earned + $5
                """, inviter_id, used_invite.code, 1, 1, inviter_reward)

        invitee_player = await self.bot.services.player.get(member.id)
        if invitee_player:
            await self.bot.services.player.update_balance(member.id, wallet_delta=invitee_reward)
            await self.bot.services.player.queries.add_transaction(
                member.id, invitee_reward, invitee_player.get("wallet", 0) + invitee_reward,
                "invite_bonus", f"Invited by {used_invite.inviter.name}"
            )

        self.logger.info(f"{member.name} joined via {used_invite.inviter.name}. Rewards given.")

        try:
            inviter = member.guild.get_member(inviter_id)
            if inviter:
                embed = discord.Embed(
                    title="🎉 Invite Reward!",
                    description=f"{member.name} joined using your invite! You received **{inviter_reward} SC**.",
                    color=discord.Color.green()
                )
                await inviter.send(embed=embed)
        except Exception:
            pass

        try:
            embed = discord.Embed(
                title="🎉 Welcome Bonus!",
                description=f"Welcome to Simora City! You received **{invitee_reward} SC** for joining via invite.\nUse `/start` to begin your journey!",
                color=discord.Color.green()
            )
            await member.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        pass

    @app_commands.command(name="invite", description="Get your invite link")
    async def invite(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        player = await self.bot.services.player.get(interaction.user.id)
        if not player:
            await interaction.followup.send("❌ You need to use `/start` first to register.", ephemeral=True)
            return

        guild = interaction.guild
        if guild.id != Config.OFFICIAL_GUILD_ID:
            await interaction.followup.send("❌ Please use this command in the official Simora City server.", ephemeral=True)
            return

        invites = await guild.invites()
        user_invite = next((inv for inv in invites if inv.inviter.id == interaction.user.id), None)

        if not user_invite:
            user_invite = await guild.create_invite(
                max_uses=0,
                max_age=86400 * 7,
                reason=f"Invite for {interaction.user.name}"
            )

        embed = discord.Embed(
            title="🔗 Your Invite Link",
            description=f"Share this link to invite friends to Simora City!\n\n**Link:** {user_invite.url}\n\n**Rewards:**\n• You get **500 SC** per invite\n• Your friend gets **500 SC** welcome bonus\n• Bonus **500 SC** when friend reaches Rep 3!",
            color=discord.Color.gold()
        )

        async with self.bot.db.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT uses, successful, sc_earned FROM invite_tracker
                WHERE discord_id = $1
                ORDER BY created_at DESC LIMIT 1
            """, interaction.user.id)

        if stats:
            embed.add_field(
                name="📊 Your Stats",
                value=f"**Invites Sent:** {stats['uses']}\n**Successful:** {stats['successful']}\n**SC Earned:** {stats['sc_earned']}",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="invite_leaderboard", description="Show top inviters")
    async def invite_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        async with self.bot.db.acquire() as conn:
            top_inviters = await conn.fetch("""
                SELECT discord_id, SUM(successful) as total_invites, SUM(sc_earned) as total_sc
                FROM invite_tracker
                GROUP BY discord_id
                ORDER BY total_invites DESC
                LIMIT 10
            """)

        if not top_inviters:
            await interaction.followup.send("No invites yet. Be the first!", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏆 Invite Leaderboard",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        description = ""
        for i, inviter in enumerate(top_inviters, 1):
            user = self.bot.get_user(inviter["discord_id"])
            username = user.name if user else f"<@{inviter['discord_id']}>"

            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            medal = medals.get(i, f"{i}.")

            description += f"{medal} **{username}** - {inviter['total_invites']} invites ({inviter['total_sc']} SC earned)\n"

        embed.description = description

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="invite_stats", description="Show your invite stats")
    async def invite_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        async with self.bot.db.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT uses, successful, sc_earned FROM invite_tracker
                WHERE discord_id = $1
                ORDER BY created_at DESC LIMIT 1
            """, interaction.user.id)

            invites = await conn.fetch("""
                SELECT invite_code, uses, successful, sc_earned, created_at
                FROM invite_tracker
                WHERE discord_id = $1
                ORDER BY created_at DESC
                LIMIT 10
            """, interaction.user.id)

        if not stats:
            await interaction.followup.send("You haven't invited anyone yet. Use `/invite` to get your link!", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 Your Invite Stats",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(name="Total Invites Sent", value=str(stats['uses']), inline=True)
        embed.add_field(name="Successful Joins", value=str(stats['successful']), inline=True)
        embed.add_field(name="SC Earned", value=f"{stats['sc_earned']} SC", inline=True)

        if invites:
            invite_list = ""
            for inv in invites[:5]:
                invite_list += f"`{inv['invite_code']}`: {inv['successful']} joins ({inv['sc_earned']} SC)\n"
            embed.add_field(name="Recent Invites", value=invite_list or "No recent invites", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(hours=168)
    async def weekly_leaderboard(self):
        guild = self.bot.get_guild(Config.OFFICIAL_GUILD_ID)
        if not guild:
            return

        channel_id = Config.INVITE_LEADERBOARD_CHANNEL_ID
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        async with self.bot.db.acquire() as conn:
            weekly_top = await conn.fetch("""
                SELECT discord_id, SUM(successful) as invites_this_week
                FROM invite_tracker
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY discord_id
                ORDER BY invites_this_week DESC
                LIMIT 10
            """)

        if not weekly_top:
            return

        embed = discord.Embed(
            title="📅 Weekly Invite Leaderboard",
            description="Top inviters this week!",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        description = ""
        for i, inviter in enumerate(weekly_top, 1):
            user = guild.get_member(inviter["discord_id"])
            username = user.mention if user else f"<@{inviter['discord_id']}>"

            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            medal = medals.get(i, f"{i}.")

            description += f"{medal} {username} - {inviter['invites_this_week']} invites\n"

        embed.description = description

        await channel.send(embed=embed)

        self.logger.info("Weekly invite leaderboard posted")

    @weekly_leaderboard.before_loop
    async def before_weekly_leaderboard(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(InvitesCog(bot))