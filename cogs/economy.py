import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
import asyncio
from typing import Optional, Literal

from utils.checks import requires_profile, not_jailed, requires_premium
from utils.embeds import EmbedBuilder
from utils.formatters import format_sc, format_time, progress_bar, ordinal
from utils.delayed_response import DelayedResponse, NPCDelayedResponse
from utils.luck import Luck


class EconomyCog(commands.Cog):
    """Economy commands - balance, bank, daily, pay, send"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.cogs.economy")

    @app_commands.command(name="balance", description="View your wallet and bank balance")
    @app_commands.describe(
        user="Optional: View another player's balance",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.User] = None, ephemeral: bool = False):
        """Display wallet, bank, net worth with 7-day sparkline"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        target_user = user or interaction.user
        target_id = target_user.id
        
        player_data = await self.bot.services.player.get(target_id)
        
        if not player_data:
            if target_id == interaction.user.id:
                await interaction.followup.send(
                    "❌ You haven't started your journey yet. Use `/start` to begin.",
                    ephemeral=ephemeral
                )
            else:
                await interaction.followup.send(
                    f"❌ {target_user.name} hasn't started playing Simora City yet.",
                    ephemeral=ephemeral
                )
            return
        
        wallet = player_data.get("wallet", 0)
        bank = player_data.get("bank", 0)
        net_worth = wallet + bank
        
        history = await self.bot.services.player.get_net_worth_history(target_id, days=7)
        
        embed = discord.Embed(
            title=f"💰 {target_user.name}'s Balance",
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc)
        )
        
        wallet_percent = int((wallet / net_worth * 100)) if net_worth > 0 else 0
        
        embed.add_field(
            name="💵 Wallet",
            value=f"{format_sc(wallet)}\n{progress_bar(wallet_percent, 10, '💵')}",
            inline=True
        )
        
        embed.add_field(
            name="🏦 Bank",
            value=f"{format_sc(bank)}\n{progress_bar(100 - wallet_percent, 10, '🏦')}",
            inline=True
        )
        
        embed.add_field(
            name="📊 Net Worth",
            value=format_sc(net_worth),
            inline=True
        )
        
        if history and len(history) >= 2:
            sparkline = self._generate_sparkline(history)
            week_change = history[-1]["net_worth"] - history[0]["net_worth"]
            change_emoji = "📈" if week_change > 0 else "📉" if week_change < 0 else "➡️"
            embed.add_field(
                name=f"{change_emoji} 7-Day Trend",
                value=f"{sparkline}\n{format_sc(abs(week_change))} {'up' if week_change > 0 else 'down' if week_change < 0 else 'no change'}",
                inline=False
            )
        
        if net_worth > 0 and wallet > net_worth * 0.5:
            embed.set_footer(text="💡 Ray says: 'Wallet's heavy. Bank it before someone lifts it.'")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        
        if net_worth > 0 and wallet > net_worth * 0.5 and target_id == interaction.user.id:
            npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
            await npc_delayed.send_line(
                "ray",
                {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": player_data.get("district", 1), "premium_tier": player_data.get("premium_tier", "citizen")},
                f"Player has {format_sc(wallet)} in wallet and {format_sc(bank)} in bank. Wallet is over 50% of net worth. Warn them to bank it.",
                delay=1.5,
                ephemeral=ephemeral
            )

    def _generate_sparkline(self, history: list) -> str:
        """Generate ASCII sparkline from history data"""
        if not history:
            return "No data"
        
        values = [h["net_worth"] for h in history[-7:]]
        if not values:
            return "No data"
        
        min_val = min(values)
        max_val = max(values)
        
        if min_val == max_val:
            return "▬▬▬▬▬▬▬"
        
        spark_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        
        sparkline = ""
        for val in values:
            normalized = (val - min_val) / (max_val - min_val)
            idx = min(int(normalized * (len(spark_chars) - 1)), len(spark_chars) - 1)
            sparkline += spark_chars[idx]
        
        return sparkline

    @app_commands.command(name="bank", description="Manage your bank account")
    @app_commands.describe(
        action="deposit or withdraw",
        amount="Amount to deposit/withdraw (or 'all')",
        ephemeral="Hide the response from others (default: False)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="💰 Deposit", value="deposit"),
        app_commands.Choice(name="💸 Withdraw", value="withdraw")
    ])
    @requires_profile()
    @not_jailed()
    async def bank(self, interaction: discord.Interaction, action: str, amount: str, ephemeral: bool = False):
        """Deposit or withdraw SC from bank with interest projection"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        wallet = player_data.get("wallet", 0)
        bank_balance = player_data.get("bank", 0)
        
        try:
            if amount.lower() == "all":
                parsed_amount = None
            else:
                parsed_amount = int(amount)
                if parsed_amount <= 0:
                    raise ValueError
        except ValueError:
            await interaction.followup.send(
                "❌ Amount must be a positive number or 'all'.",
                ephemeral=ephemeral
            )
            return
        
        if action == "deposit":
            if parsed_amount is None:
                amount_to_move = wallet
            else:
                amount_to_move = parsed_amount
            
            if amount_to_move <= 0:
                await interaction.followup.send(
                    "❌ You don't have any SC to deposit.",
                    ephemeral=ephemeral
                )
                return
            
            if amount_to_move > wallet:
                await interaction.followup.send(
                    f"❌ You only have {format_sc(wallet)} in your wallet.",
                    ephemeral=ephemeral
                )
                return
            
            fee = int(amount_to_move * 0.01)
            amount_after_fee = amount_to_move - fee
            
            await self.bot.services.player.update_balance(
                interaction.user.id,
                wallet_delta=-amount_to_move,
                bank_delta=amount_after_fee
            )
            
            interest_rate = self.bot.config.BANK_INTEREST_RATE
            monthly_projection = int(bank_balance * (interest_rate / 100))
            
            embed = discord.Embed(
                title="🏦 Deposit Successful",
                description=f"Deposited {format_sc(amount_after_fee)} to your bank (1% fee: {format_sc(fee)})",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="📊 New Balance",
                value=f"Wallet: {format_sc(wallet - amount_to_move)}\nBank: {format_sc(bank_balance + amount_after_fee)}",
                inline=True
            )
            
            embed.add_field(
                name="💰 Interest Projection",
                value=f"At {interest_rate}% APY, you'll earn ~{format_sc(monthly_projection)} SC in 30 days",
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            
        else:
            if parsed_amount is None:
                amount_to_move = bank_balance
            else:
                amount_to_move = parsed_amount
            
            if amount_to_move <= 0:
                await interaction.followup.send(
                    "❌ You don't have any SC to withdraw.",
                    ephemeral=ephemeral
                )
                return
            
            if amount_to_move > bank_balance:
                await interaction.followup.send(
                    f"❌ You only have {format_sc(bank_balance)} in your bank.",
                    ephemeral=ephemeral
                )
                return
            
            await self.bot.services.player.update_balance(
                interaction.user.id,
                wallet_delta=amount_to_move,
                bank_delta=-amount_to_move
            )
            
            embed = discord.Embed(
                title="🏦 Withdrawal Successful",
                description=f"Withdrew {format_sc(amount_to_move)} to your wallet",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="📊 New Balance",
                value=f"Wallet: {format_sc(wallet + amount_to_move)}\nBank: {format_sc(bank_balance - amount_to_move)}",
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="daily", description="Claim your daily reward")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def daily(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Claim daily reward with streak tracking and itemized multipliers"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        tension = DelayedResponse(interaction, self.bot.services.ai, min_delay=1.0, max_delay=2.0)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        await tension.send_tension(
            "ray",
            {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": player_data.get("district", 1), "premium_tier": player_data.get("premium_tier", "citizen")},
            "Daily reward claim. City waking up moment.",
            ephemeral=ephemeral
        )
        
        result = await self.bot.services.economy.daily(interaction.user.id)
        
        if not result.get("success"):
            cooldown_remaining = result.get("cooldown_remaining", 0)
            if cooldown_remaining > 0:
                await tension.resolve(
                    discord.Embed(
                        title="⏰ Daily Already Claimed",
                        description=f"Come back in {format_time(cooldown_remaining)}",
                        color=discord.Color.gold()
                    )
                )
            else:
                await tension.resolve(
                    discord.Embed(
                        title="❌ Error",
                        description=result.get("message", "Could not claim daily reward."),
                        color=discord.Color.red()
                    )
                )
            return
        
        base_amount = result.get("base_amount", 1000)
        streak_bonus = result.get("streak_bonus", 0)
        premium_multiplier = result.get("premium_multiplier", 1.0)
        district_bonus = result.get("district_bonus", 1.0)
        season_bonus = result.get("season_bonus", 1.0)
        total_reward = result.get("reward", base_amount)
        streak_days = result.get("streak_days", 1)
        
        embed = discord.Embed(
            title="📅 Daily Reward Claimed",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        itemized = (
            f"**Base Reward:** +{format_sc(base_amount)}\n"
            f"**Streak Bonus (x{streak_days}):** +{format_sc(streak_bonus)}\n"
            f"**Premium ({premium_multiplier}x):** +{format_sc(int(base_amount * (premium_multiplier - 1)))}\n"
            f"**District ({district_bonus}x):** +{format_sc(int(base_amount * (district_bonus - 1)))}\n"
            f"**Season ({season_bonus}x):** +{format_sc(int(base_amount * (season_bonus - 1)))}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Total:** +{format_sc(total_reward)}"
        )
        
        embed.add_field(name="💰 Reward Breakdown", value=itemized, inline=False)
        
        if streak_days == 7:
            embed.add_field(
                name="🔥 7-Day Streak!",
                value="You're on fire! Keep it up for bonus multipliers.",
                inline=False
            )
        
        embed.set_footer(text=f"Streak: {streak_days} days")
        
        await tension.resolve(embed)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
        
        if streak_days >= 7:
            await npc_delayed.send_line(
                "ray",
                {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": player_data.get("district", 1), "premium_tier": player_data.get("premium_tier", "citizen")},
                f"Player claimed daily reward with {streak_days} day streak. Acknowledge their consistency.",
                delay=1.5,
                ephemeral=ephemeral
            )

    @app_commands.command(name="pay", description="Send SC to another player")
    @app_commands.describe(
        user="Player to pay",
        amount="Amount to send",
        note="Optional note to include",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    async def pay(self, interaction: discord.Interaction, user: discord.User, amount: int, note: Optional[str] = None, ephemeral: bool = False):
        """Send SC to another player with rich DM notification"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        if user.id == interaction.user.id:
            await interaction.followup.send(
                "❌ You cannot pay yourself.",
                ephemeral=ephemeral
            )
            return
        
        if amount <= 0:
            await interaction.followup.send(
                "❌ Amount must be positive.",
                ephemeral=ephemeral
            )
            return
        
        sender_data = await self.bot.services.player.get(interaction.user.id)
        receiver_data = await self.bot.services.player.get(user.id)
        
        if not receiver_data:
            await interaction.followup.send(
                f"❌ {user.name} hasn't started playing Simora City yet.",
                ephemeral=ephemeral
            )
            return
        
        sender_wallet = sender_data.get("wallet", 0)
        
        if amount > sender_wallet:
            await interaction.followup.send(
                f"❌ You only have {format_sc(sender_wallet)} in your wallet.",
                ephemeral=ephemeral
            )
            return
        
        await self.bot.services.player.transfer_sc(
            interaction.user.id,
            user.id,
            amount
        )
        
        sender_district = sender_data.get("district", 1)
        district_names = {
            1: "Slums",
            2: "Downtown",
            3: "Financial District",
            4: "Underground",
            5: "Industrial Zone",
            6: "The Strip"
        }
        
        npc_map = {
            1: "ray",
            2: "chen",
            3: "broker",
            4: "ghost",
            5: "marco",
            6: "lou"
        }
        
        sending_npc = npc_map.get(sender_district, "ray")
        
        embed = discord.Embed(
            title="💸 Payment Sent",
            description=f"Sent {format_sc(amount)} to {user.name}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if note:
            embed.add_field(name="📝 Note", value=note, inline=False)
        
        embed.set_footer(text=f"Your wallet: {format_sc(sender_wallet - amount)}")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        
        sender_npc_line = await self.bot.services.ai.generate_npc_line(
            sending_npc,
            {"username": interaction.user.name, "reputation": sender_data.get("reputation", 0), "rep_rank": sender_data.get("rep_rank", 1), "district": sender_district, "premium_tier": sender_data.get("premium_tier", "citizen")},
            f"Player just sent {format_sc(amount)} to {user.name}. Note: {note if note else 'No note'}."
        )
        
        receiver_embed = discord.Embed(
            title="💰 Payment Received",
            description=f"You received {format_sc(amount)} from {interaction.user.name}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if note:
            receiver_embed.add_field(name="📝 Note", value=note, inline=False)
        
        if sender_npc_line:
            receiver_embed.add_field(
                name=f"💬 From {district_names.get(sender_district, 'Simora')}",
                value=f"*{sender_npc_line}*",
                inline=False
            )
        
        receiver_embed.set_footer(text=f"Your new wallet: {format_sc(receiver_data.get('wallet', 0) + amount)}")
        
        try:
            target_user = await self.bot.fetch_user(user.id)
            await target_user.send(embed=receiver_embed)
        except discord.Forbidden:
            self.logger.warning(f"Cannot DM user {user.id}")

    @app_commands.command(name="rich", description="Alias for leaderboard wealth")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    async def rich(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Quick access to wealth leaderboard"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        last_week_snapshot = await self.bot.services.player.get_leaderboard_snapshot(weeks_ago=1)
        
        leaders = await self.bot.services.player.get_leaderboard("wealth", limit=10)
        
        if not leaders:
            await interaction.followup.send("❌ No players found on the leaderboard yet.", ephemeral=ephemeral)
            return
        
        embed = discord.Embed(
            title="🏆 Wealth Leaderboard",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        medal_emojis = ["🥇", "🥈", "🥉"]
        
        description_lines = []
        
        for i, player in enumerate(leaders):
            rank = i + 1
            medal = medal_emojis[i] if i < 3 else f"{rank}."
            
            username = player.get("username", "Unknown")
            net_worth = player.get("wallet", 0) + player.get("bank", 0)
            
            movement = ""
            if last_week_snapshot and player.get("discord_id") in last_week_snapshot:
                old_rank = last_week_snapshot[player["discord_id"]].get("rank", rank + 5)
                if old_rank < rank:
                    movement = " ▼" + str(rank - old_rank)
                elif old_rank > rank:
                    movement = " ▲" + str(old_rank - rank)
                else:
                    movement = " →"
            
            description_lines.append(f"{medal} **{username}** — {format_sc(net_worth)}{movement}")
        
        embed.description = "\n".join(description_lines)
        
        player_rank = await self.bot.services.player.get_rank(interaction.user.id, "wealth")
        
        if player_rank:
            embed.set_footer(text=f"Your rank: #{player_rank}")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="send", description="Schedule a delayed SC transfer (Elite+)")
    @app_commands.describe(
        user="Player to send to",
        amount="Amount to send",
        delay_hours="Hours to delay (1-168)",
        note="Optional note to include",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    @requires_premium("elite")
    async def send(self, interaction: discord.Interaction, user: discord.User, amount: int, delay_hours: int = 24, note: Optional[str] = None, ephemeral: bool = False):
        """Schedule SC transfer for later delivery"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        if user.id == interaction.user.id:
            await interaction.followup.send(
                "❌ You cannot send to yourself.",
                ephemeral=ephemeral
            )
            return
        
        if amount <= 0:
            await interaction.followup.send(
                "❌ Amount must be positive.",
                ephemeral=ephemeral
            )
            return
        
        if delay_hours < 1 or delay_hours > 168:
            await interaction.followup.send(
                "❌ Delay must be between 1 and 168 hours (7 days).",
                ephemeral=ephemeral
            )
            return
        
        sender_data = await self.bot.services.player.get(interaction.user.id)
        
        if not sender_data:
            await interaction.followup.send(
                "❌ You haven't started your journey yet.",
                ephemeral=ephemeral
            )
            return
        
        receiver_data = await self.bot.services.player.get(user.id)
        
        if not receiver_data:
            await interaction.followup.send(
                f"❌ {user.name} hasn't started playing Simora City yet.",
                ephemeral=ephemeral
            )
            return
        
        sender_wallet = sender_data.get("wallet", 0)
        
        if amount > sender_wallet:
            await interaction.followup.send(
                f"❌ You only have {format_sc(sender_wallet)} in your wallet.",
                ephemeral=ephemeral
            )
            return
        
        scheduled_time = datetime.now(timezone.utc) + timedelta(hours=delay_hours)
        
        await self.bot.services.player.schedule_transfer(
            interaction.user.id,
            user.id,
            amount,
            scheduled_time,
            note
        )
        
        await self.bot.services.player.update_balance(
            interaction.user.id,
            wallet_delta=-amount
        )
        
        embed = discord.Embed(
            title="⏰ Scheduled Transfer",
            description=(
                f"Scheduled {format_sc(amount)} to be sent to {user.name}\n"
                f"**Delivery:** {format_time(delay_hours * 3600)}\n"
                f"**Arrives:** {scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if note:
            embed.add_field(name="📝 Note", value=note, inline=False)
        
        embed.set_footer(text=f"Your wallet: {format_sc(sender_wallet - amount)}")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
        
        sender_district = sender_data.get("district", 1)
        npc_map = {
            1: "ray",
            2: "chen",
            3: "broker",
            4: "ghost",
            5: "marco",
            6: "lou"
        }
        npc_id = npc_map.get(sender_district, "ray")
        
        await npc_delayed.send_line(
            npc_id,
            {"username": interaction.user.name, "reputation": sender_data.get("reputation", 0), "rep_rank": sender_data.get("rep_rank", 1), "district": sender_district, "premium_tier": sender_data.get("premium_tier", "citizen")},
            f"Player scheduled {format_sc(amount)} to {user.name} in {delay_hours} hours. Note: {note if note else 'No note'}.",
            delay=1.5,
            ephemeral=ephemeral
        )
        
        self.logger.info(f"Scheduled transfer: {interaction.user.id} -> {user.id}: {amount} SC in {delay_hours}h")


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))