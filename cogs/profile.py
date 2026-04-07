import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
import asyncio
from typing import Optional

from utils.checks import requires_profile, not_jailed, requires_premium
from utils.embeds import EmbedBuilder
from utils.formatters import format_sc, format_time, progress_bar, ordinal
from utils.delayed_response import DelayedResponse, NPCDelayedResponse, TensionBuilder
from utils.luck import Luck
from config.settings import Config


class ProfileCog(commands.Cog):
    """Profile commands - identity, stats, leaderboards, prestige"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.cogs.profile")
        self.luck = Luck()

    @app_commands.command(name="start", description="Begin your journey in Simora City")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    async def start(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Register new player with official server verification"""
        
        result = await self.bot.ctx.get_player(interaction.user.id)
        
        if result.get("success"):
            await interaction.response.send_message(
                "❌ You've already started your journey in Simora City. Use `/profile` to view your stats.",
                ephemeral=ephemeral
            )
            return
        
        official_guild_id = Config.OFFICIAL_GUILD_ID
        
        if official_guild_id:
            guild = self.bot.get_guild(official_guild_id)
            if guild:
                member = guild.get_member(interaction.user.id)
                if not member:
                    await interaction.response.send_message(
                        f"❌ You must join the official Simora City Discord server before starting.\n"
                        f"Join here: {Config.OFFICIAL_GUILD_INVITE}",
                        ephemeral=ephemeral
                    )
                    return
        
        import random
        import string
        
        word_pool = [
            "SIMORA", "CITY", "NEON", "CYBER", "RAY", "GHOST", 
            "CHEN", "BROKER", "MARCO", "LOU", "UNDERGROUND", 
            "STRIP", "DOWNTOWN", "INDUSTRIAL", "FINANCIAL", "SLUMS"
        ]
        
        emoji_pool = [
            "🏙️", "🔑", "⭐", "🌃", "🤖", "👻", "💀", "🎰", "🏢", "📈", 
            "💰", "⚡", "🔪", "🚗", "🏭", "💎", "👑", "🔒", "🗝️", "📜"
        ]
        
        selected_word = random.choice(word_pool)
        selected_emoji = random.choice(emoji_pool)
        pattern = f"{selected_emoji} {selected_word}"
        
        hints = [
            f"Type the word after the {selected_emoji} emoji",
            f"What word comes after {selected_emoji}?",
            f"Copy the word shown after the emoji",
            f"Type: {selected_word}"
        ]
        hint = random.choice(hints)
        
        captcha_key = f"start_captcha:{interaction.user.id}"
        await self.bot.cache.set(captcha_key, selected_word, ttl=120)
        
        terms = [
            "No botting, scripting, or automation",
            "No exploiting bugs or glitches",
            "Be respectful to other players",
            "SC has no real-world value",
            "You can delete your data anytime with `/delete_profile`",
            "Don't manipulate the market with multiple accounts",
            "No harassment or toxic behavior",
            "Report bugs in tickets for rewards"
        ]
        
        selected_terms = random.sample(terms, min(5, len(terms)))
        terms_text = "\n".join([f"• {t}" for t in selected_terms])
        
        terms_embed = discord.Embed(
            title="📜 Welcome to Simora City",
            description=(
                f"Before you begin, please read and accept our Terms of Service.\n\n"
                f"**📋 Terms Summary:**\n{terms_text}\n\n"
                f"**✅ To verify you're human:**\n"
                f"```\n{pattern}\n```\n"
                f"*{hint}*\n\n"
                f"Type your answer in this channel within 120 seconds."
            ),
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=terms_embed, ephemeral=ephemeral)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id
        
        try:
            msg = await self.bot.wait_for("message", timeout=120.0, check=check)
            
            stored_answer = await self.bot.cache.get(captcha_key)
            user_answer = msg.content.strip().upper().replace(" ", "")
            
            is_correct = user_answer == stored_answer
            
            if not is_correct:
                fail_memes = [
                    f"```\n🤡 VERIFICATION FAILED\n┻━┻ ︵ヽ(`Д´)ﾉ︵ ┻━┻\nExpected '{stored_answer}', got '{msg.content}'\nRay is disappointed.\n```",
                    f"```\n💀 BOT DETECTED\n     ⚰️\n     ⚰️\nYou typed '{msg.content}'. The city rejects you.\n```",
                    f"```\n🚫 ACCESS DENIED\n    (▀̿Ĺ̯▀̿ ̿)\n'{msg.content}' ≠ '{stored_answer}'\nTry again, human.\n```",
                    f"```\n👾 ALERT: NON-HUMAN\n    ○\n   /|\\\n   / \\\nEven Ray knows that's wrong.\n```"
                ]
                fail_meme = random.choice(fail_memes)
                
                fail_embed = discord.Embed(
                    title="🤖 VERIFICATION FAILED",
                    description=fail_meme,
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=fail_embed, ephemeral=ephemeral)
                await self.bot.cache.delete(captcha_key)
                return
            
        except asyncio.TimeoutError:
            timeout_meme = random.choice([
                "```\n⏰ TIME'S UP\n    ⌛\n    ⏳\n    ⌛\nRay got tired of waiting.\n```",
                "```\n🐌 TOO SLOW\nEven snails move faster than you.\nRun /start again.\n```",
                "```\n💤 ZZZ...\nThe city moved on without you.\nTry again.\n```"
            ])
            timeout_embed = discord.Embed(
                title="⏰ VERIFICATION TIMEOUT",
                description=timeout_meme,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=timeout_embed, ephemeral=ephemeral)
            await self.bot.cache.delete(captcha_key)
            return
        
        # Create player via middleware
        player_result = await self.bot.ctx.register_player(
            interaction.user.id,
            interaction.user.name
        )
        
        if not player_result.get("success"):
            await interaction.followup.send(
                f"❌ {player_result.get('message', 'Registration failed.')}",
                ephemeral=ephemeral
            )
            return
        
        player_data = player_result.get("data", {})
        
        tension = DelayedResponse(interaction, self.bot.ctx, min_delay=2.0, max_delay=3.0)
        
        await tension.send_tension(
            "ray",
            {"discord_id": interaction.user.id, "username": interaction.user.name, "reputation": 0, "rep_rank": 1, "district": 1, "premium_tier": "citizen"},
            "New player registration. Welcome to Simora City.",
            ephemeral=ephemeral
        )
        
        result_embed = discord.Embed(
            title="🏙️ Welcome to Simora City",
            description=(
                f"**{interaction.user.name}**, your journey begins.\n\n"
                f"💰 **Starting Wallet:** {format_sc(5000)}\n"
                f"🏦 **Starting Bank:** {format_sc(1000)}\n"
                f"📍 **Starting District:** Slums\n"
                f"⭐ **Starting Reputation:** 0 (Rank 1)\n\n"
                f"*Ray hands you the keys to the city. Don't lose them.*"
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        result_embed.set_footer(text="Simora City | Your story begins now")
        
        await tension.resolve(result_embed)
        
        await asyncio.sleep(1.5)
        
        onboarding_embed = discord.Embed(
            title="📖 What is SimCoin?",
            description=(
                "SimCoin is a **living economy RPG** set in the cyberpunk city of **Simora**.\n\n"
                "**You can:**\n"
                "💰 Work jobs to earn SC\n"
                "🏦 Invest in the stock market\n"
                "🔪 Commit crimes (with risk!)\n"
                "🏢 Run your own businesses\n"
                "⚔️ Form factions and control districts\n"
                "🎰 Gamble at Lucky Lou's\n"
                "🤖 Talk to AI NPCs who remember you\n\n"
                "*The city runs 24/7. Stocks move. News drops. Turf wars happen.*"
            ),
            color=discord.Color.teal()
        )
        await interaction.followup.send(embed=onboarding_embed, ephemeral=ephemeral)
        
        await asyncio.sleep(2)
        
        guide_embed = discord.Embed(
            title="🚀 Quick Start Guide",
            description=(
                "**Essential Commands:**\n"
                "• `/profile` - View your stats\n"
                "• `/daily` - Claim daily reward\n"
                "• `/travel` - Move between districts\n"
                "• `/jobs` - Find work\n"
                "• `/balance` - Check your SC\n"
                "• `/map` - See the city\n\n"
                "**Pro Tips:**\n"
                "• Keep SC in the bank to avoid theft\n"
                "• Higher reputation = better jobs\n"
                "• Join the official server for events\n"
                "• Vote on Top.gg for badges\n\n"
                "*Need help? Join our support server!*"
            ),
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=guide_embed, ephemeral=ephemeral)
        
        await asyncio.sleep(2)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.ctx)
        
        await npc_delayed.send_line(
            "ray",
            {"discord_id": interaction.user.id, "username": interaction.user.name, "reputation": 0, "rep_rank": 1, "district": 1, "premium_tier": "citizen"},
            "Player just finished onboarding. Give them a final encouraging welcome to Simora City.",
            delay=1.0,
            ephemeral=ephemeral
        )
        
        await self.bot.event_bus.fire("player.registered", {
            "discord_id": interaction.user.id,
            "username": interaction.user.name
        })
        
        await self.bot.cache.delete(captcha_key)
        
        self.logger.info(f"New player registered: {interaction.user.id}")

    @app_commands.command(name="delete_profile", description="Permanently delete your profile and all data")
    @app_commands.describe(
        confirm="Type 'DELETE' to confirm",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    async def delete_profile(self, interaction: discord.Interaction, confirm: str, ephemeral: bool = False):
        """Permanently delete player profile and all associated data"""
        
        if confirm != "DELETE":
            embed = discord.Embed(
                title="⚠️ Confirm Profile Deletion",
                description=(
                    "This will permanently delete:\n"
                    "• All SC (wallet and bank)\n"
                    "• All reputation and progress\n"
                    "• All businesses and investments\n"
                    "• All inventory items\n"
                    "• All faction memberships\n"
                    "• All crime and heist records\n\n"
                    f"**Type `/delete_profile confirm:DELETE` to confirm.**"
                ),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            return
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        try:
            player_result = await self.bot.ctx.get_player(interaction.user.id)
            
            if not player_result.get("success"):
                await interaction.followup.send("❌ Profile not found.", ephemeral=ephemeral)
                return
            
            async with self.bot.db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM scheduled_transfers WHERE from_id = $1 OR to_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM bounties WHERE poster_id = $1 OR target_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM heist_sessions WHERE initiator_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM faction_members WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM investments WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM market_listings WHERE seller_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM businesses WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM jobs_active WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM ai_npc_memory WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM interaction_log WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM transactions WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM inventory WHERE discord_id = $1", interaction.user.id)
                    await conn.execute("DELETE FROM cooldowns WHERE discord_id = $1", interaction.user.id)
                    
                    try:
                        await conn.execute("DELETE FROM properties WHERE discord_id = $1", interaction.user.id)
                    except Exception:
                        pass
                    
                    await conn.execute("DELETE FROM players WHERE discord_id = $1", interaction.user.id)
            
            await self.bot.cache.delete(self.bot.cache.generate_key("player", interaction.user.id))
            
            await self.bot.event_bus.fire("player.deleted", {
                "discord_id": interaction.user.id,
                "username": interaction.user.name
            })
            
            embed = discord.Embed(
                title="🗑️ Profile Deleted",
                description="Your Simora City profile has been permanently deleted.\n\nUse `/start` to begin a new journey if you wish to return.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            
            self.logger.info(f"Player deleted profile: {interaction.user.id}")
            
        except Exception as e:
            self.logger.error(f"Failed to delete profile for {interaction.user.id}: {e}")
            await interaction.followup.send("❌ Failed to delete profile. Please contact support.", ephemeral=ephemeral)

            
    @app_commands.command(name="profile", description="View your player profile")
    @app_commands.describe(
        user="Optional: View another player's profile",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.User] = None, ephemeral: bool = False):
        """Display Pillow-generated profile card"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        target_user = user or interaction.user
        target_id = target_user.id
        
        result = await self.bot.ctx.get_player(target_id)
        
        if not result.get("success"):
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
        
        player_data = result.get("data", {})
        
        status_line = await self._build_status_line(target_id, player_data)
        
        player_data["status_line"] = status_line
        
        bounties_result = await self.bot.ctx.get_bounties(target_id)
        active_bounties = bounties_result.get("data", [])
        player_data["active_bounties"] = len(active_bounties)
        
        if active_bounties:
            total_bounty = sum(b.get("amount", 0) for b in active_bounties)
            player_data["total_bounty"] = total_bounty
        
        player_data["streak_days"] = player_data.get("streak_days", 0)
        
        if player_data.get("premium_tier") == "obsidian" and player_data.get("premium_expires"):
            expires = player_data["premium_expires"]
            if isinstance(expires, datetime):
                player_data["premium_expires_str"] = expires.strftime("%Y-%m-%d")
        
        profile_card = await self.bot.ctx.get_profile_card(player_data)

        if profile_card:
            await interaction.followup.send(file=profile_card, ephemeral=ephemeral)
        else:
            embed = self._build_fallback_profile_embed(player_data, target_user)
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    async def _build_status_line(self, discord_id: int, player_data: dict) -> str:
        """Build live status line with streak, wanted, district info"""
        
        status_parts = []
        
        district_names = {
            1: "Slums",
            2: "Downtown",
            3: "Financial District",
            4: "Underground",
            5: "Industrial Zone",
            6: "The Strip"
        }
        district = player_data.get("district", 1)
        status_parts.append(f"📍 {district_names.get(district, 'Unknown')}")
        
        streak_days = player_data.get("streak_days", 0)
        if streak_days > 0:
            status_parts.append(f"🔥 {streak_days} day streak")
        
        heat_level = player_data.get("heat_level", 0)
        if heat_level >= 3:
            status_parts.append(f"⚠️ Wanted: {heat_level}/10")
        
        bounties_result = await self.bot.ctx.get_bounties(discord_id)
        active_bounties = bounties_result.get("data", [])
        if active_bounties:
            total = sum(b.get("amount", 0) for b in active_bounties)
            status_parts.append(f"💰 Bounty: {format_sc(total)}")
        
        if player_data.get("is_jailed"):
            jail_until = player_data.get("jail_until")
            if jail_until and isinstance(jail_until, datetime):
                remaining = (jail_until - datetime.now(timezone.utc)).seconds // 60
                status_parts.append(f"⛓️ Jailed ({remaining}m)")
        
        return " · ".join(status_parts)

    def _build_fallback_profile_embed(self, player_data: dict, target_user: discord.User) -> discord.Embed:
        """Fallback text embed if image generation fails"""
        
        district_names = {
            1: "🏚️ Slums",
            2: "🏢 Downtown",
            3: "💹 Financial District",
            4: "🌿 Underground",
            5: "🏭 Industrial Zone",
            6: "🎰 The Strip"
        }
        
        tier_icons = {
            "citizen": "👤",
            "resident": "🏠",
            "elite": "💎",
            "obsidian": "⚫"
        }
        
        role_icons = {
            "player": "",
            "beta_tester": "🧪 ",
            "mod": "🛡️ ",
            "dev": "🛠️ "
        }
        
        system_role = player_data.get("system_role", "player")
        premium_tier = player_data.get("premium_tier", "citizen")
        
        embed = discord.Embed(
            title=f"{role_icons.get(system_role, '')}{tier_icons.get(premium_tier, '👤')} {target_user.name}'s Profile",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        wallet = player_data.get("wallet", 0)
        bank = player_data.get("bank", 0)
        net_worth = wallet + bank
        
        embed.add_field(
            name="💰 Finances",
            value=f"Wallet: {format_sc(wallet)}\nBank: {format_sc(bank)}\nNet Worth: {format_sc(net_worth)}",
            inline=True
        )
        
        rep = player_data.get("reputation", 0)
        rep_rank = player_data.get("rep_rank", 1)
        rep_next = rep_rank * 1000
        rep_progress = min(100, int((rep % 1000) / 10))
        
        embed.add_field(
            name="⭐ Reputation",
            value=f"Rank {rep_rank}\n{rep}/{rep_next} XP\n{progress_bar(rep_progress)}",
            inline=True
        )
        
        embed.add_field(
            name="📍 Location",
            value=district_names.get(player_data.get("district", 1), "Unknown"),
            inline=True
        )
        
        if player_data.get("faction_name"):
            embed.add_field(
                name="⚔️ Faction",
                value=player_data.get("faction_name"),
                inline=True
            )
        
        embed.set_footer(text=f"Prestige {player_data.get('prestige', 0)} | Joined: {player_data.get('created_at', datetime.now()).strftime('%Y-%m-%d')}")
        
        return embed

    @app_commands.command(name="leaderboard", description="View top players")
    @app_commands.describe(
        type="Leaderboard type: wealth, reputation, businesses, or prestige",
        ephemeral="Hide the response from others (default: False)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="💰 Wealth", value="wealth"),
        app_commands.Choice(name="⭐ Reputation", value="reputation"),
        app_commands.Choice(name="🏢 Businesses", value="businesses"),
        app_commands.Choice(name="✨ Prestige", value="prestige")
    ])
    @requires_profile()
    async def leaderboard(self, interaction: discord.Interaction, type: str = "wealth", ephemeral: bool = False):
        """Display top 10 players with rank movement indicators"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        result = await self.bot.ctx.get_leaderboard(type, limit=10)
        
        if not result.get("success"):
            await interaction.followup.send("❌ No players found on the leaderboard yet.", ephemeral=ephemeral)
            return
        
        leaders = result.get("data", [])
        
        embed = discord.Embed(
            title=f"🏆 {type.title()} Leaderboard",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        medal_emojis = ["🥇", "🥈", "🥉"]
        
        description_lines = []
        
        for i, player in enumerate(leaders):
            rank = i + 1
            medal = medal_emojis[i] if i < 3 else f"{rank}."
            
            username = player.get("username", "Unknown")
            value = self._get_leaderboard_value(player, type)
            
            rank_delta = player.get("rank_delta", 0)
            movement = ""
            if rank_delta > 0:
                movement = f" ▲{rank_delta}"
            elif rank_delta < 0:
                movement = f" ▼{abs(rank_delta)}"
            elif rank_delta == 0:
                movement = " →"
            
            description_lines.append(f"{medal} **{username}** — {value}{movement}")
        
        embed.description = "\n".join(description_lines)
        
        rank_result = await self.bot.ctx.get_player_rank(interaction.user.id, type)
        player_rank = rank_result.get("data", {}).get("rank", 0) if rank_result.get("success") else 0
        
        if player_rank:
            embed.set_footer(text=f"Your rank: #{player_rank}")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    def _get_leaderboard_value(self, player: dict, type: str) -> str:
        """Format leaderboard value based on type"""
        if type == "wealth":
            return format_sc(player.get("value", 0))
        elif type == "reputation":
            return f"{player.get('value', 0)} XP"
        elif type == "businesses":
            return f"{player.get('value', 0)} businesses"
        elif type == "prestige":
            return f"Prestige {player.get('value', 0)}"
        return str(player.get("value", 0))

    @app_commands.command(name="prestige", description="Reset for prestige and exclusive rewards")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def prestige(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Cinematic prestige sequence - requires Rep Rank 8 + 1M total earned"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        result = await self.bot.ctx.get_player(interaction.user.id)
        
        if not result.get("success"):
            await interaction.followup.send("❌ Player not found.", ephemeral=ephemeral)
            return
        
        player_data = result.get("data", {})
        
        rep_rank = player_data.get("rep_rank", 1)
        total_earned = player_data.get("total_earned", 0)
        current_prestige = player_data.get("prestige", 0)
        
        if rep_rank < 8:
            await interaction.followup.send(
                f"❌ You need Reputation Rank 8 to prestige. Current rank: {rep_rank}",
                ephemeral=ephemeral
            )
            return
        
        if total_earned < 1000000:
            needed = 1000000 - total_earned
            await interaction.followup.send(
                f"❌ You need {format_sc(1000000)} total lifetime earnings to prestige. "
                f"Need {format_sc(needed)} more.",
                ephemeral=ephemeral
            )
            return
        
        confirm_embed = discord.Embed(
            title="⚠️ PRESTIGE CONFIRMATION",
            description=(
                f"**{interaction.user.name}**, are you sure?\n\n"
                f"This will reset:\n"
                f"• Wallet and bank to {format_sc(5000)}\n"
                f"• Reputation to 0\n"
                f"• All businesses and properties\n"
                f"• All investments\n\n"
                f"You will keep:\n"
                f"• Prestige badge (Prestige {current_prestige + 1})\n"
                f"• Premium tier status\n"
                f"• Inventory items\n\n"
                f"**Type `/prestige confirm` to proceed.**"
            ),
            color=discord.Color.red()
        )
        
        await interaction.followup.send(embed=confirm_embed, ephemeral=ephemeral)

    @app_commands.command(name="prestige_confirm", description="Confirm prestige reset")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def prestige_confirm(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Execute the cinematic prestige sequence"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        result = await self.bot.ctx.get_player(interaction.user.id)
        
        if not result.get("success"):
            await interaction.followup.send("❌ Player not found.", ephemeral=ephemeral)
            return
        
        player_data = result.get("data", {})
        
        rep_rank = player_data.get("rep_rank", 1)
        total_earned = player_data.get("total_earned", 0)
        
        if rep_rank < 8 or total_earned < 1000000:
            await interaction.followup.send(
                "❌ You don't meet the requirements for prestige.",
                ephemeral=ephemeral
            )
            return
        
        from utils.delayed_response import CinematicSequence
        
        steps = [
            {
                "embed": discord.Embed(description="*...*", color=0x2b2d31),
                "delay": 3.0,
                "ai_npc": "ghost",
                "ai_context": "Cinematic continuation after silence."
            },
            {
                "embed": discord.Embed(description="*The city holds its breath.*", color=0x2b2d31),
                "delay": 3.0
            }
        ]
        
        cinematic = CinematicSequence(interaction, self.bot.ctx, steps)
        
        await cinematic.start(
            "ghost",
            {"discord_id": interaction.user.id, "username": interaction.user.name, "reputation": rep_rank * 1000, "rep_rank": rep_rank, "district": player_data.get("district", 1), "premium_tier": player_data.get("premium_tier", "citizen")},
            "Prestige moment. Player is about to reset everything for prestige.",
            ephemeral=ephemeral
        )
        
        new_prestige = player_data.get("prestige", 0) + 1
        
        # Use player service directly for prestige reset (not in middleware yet)
        await self.bot.services.player.prestige_reset(interaction.user.id, new_prestige)
        
        await asyncio.sleep(2.0)
        
        # Get fresh player data after reset
        fresh_result = await self.bot.ctx.get_player(interaction.user.id)
        fresh_data = fresh_result.get("data", {}) if fresh_result.get("success") else {}
        
        profile_card = await self.bot.ctx.get_profile_card({
            "discord_id": interaction.user.id,
            "username": interaction.user.name,
            "wallet": fresh_data.get("wallet", 5000),
            "bank": fresh_data.get("bank", 0),
            "reputation": fresh_data.get("reputation", 0),
            "rep_rank": fresh_data.get("rep_rank", 1),
            "district": fresh_data.get("district", 1),
            "premium_tier": player_data.get("premium_tier", "citizen"),
            "prestige": new_prestige,
            "system_role": player_data.get("system_role", "player"),
            "is_jailed": fresh_data.get("is_jailed", False)
        })
        
        if profile_card:
            await interaction.followup.send(
                content=f"✨ **{interaction.user.name} has reached Prestige {new_prestige}!** ✨",
                file=profile_card,
                ephemeral=ephemeral
            )
        else:
            await interaction.followup.send(
                f"✨ **{interaction.user.name} has reached Prestige {new_prestige}!** ✨\n"
                f"A new chapter begins in Simora City.",
                ephemeral=ephemeral
            )
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.ctx)
        
        await npc_delayed.send_line(
            "ray",
            {"discord_id": interaction.user.id, "username": interaction.user.name, "reputation": 0, "rep_rank": 1, "district": 1, "premium_tier": player_data.get("premium_tier", "citizen")},
            "Player just prestiged. Acknowledge their achievement briefly.",
            delay=2.0,
            ephemeral=ephemeral
        )
        
        await self.bot.event_bus.fire("player.prestige", {
            "discord_id": interaction.user.id,
            "username": interaction.user.name,
            "prestige_level": new_prestige
        })
        
        self.logger.info(f"Player prestiged: {interaction.user.id} -> Prestige {new_prestige}")

    @app_commands.command(name="stats", description="View your lifetime statistics")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    async def stats(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Display Pillow-generated lifetime stats card"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        result = await self.bot.ctx.get_player_stats(interaction.user.id)
        
        if not result.get("success"):
            await interaction.followup.send(
                f"❌ {result.get('message', 'Failed to load stats.')}",
                ephemeral=ephemeral
            )
            return
        
        stats_data = result.get("data", {})
        
        # Image service generate_stats_card needs to be added to ImageService
        # For now, use fallback embed
        embed = self._build_fallback_stats_embed(stats_data)
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    def _build_fallback_stats_embed(self, stats_data: dict) -> discord.Embed:
        """Fallback text embed for stats if image generation fails"""
        
        embed = discord.Embed(
            title="📊 Lifetime Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        total_earned = stats_data.get("total_earned", 0)
        total_spent = stats_data.get("total_spent", 0)
        
        embed.add_field(
            name="💰 Economy",
            value=f"Earned: {format_sc(total_earned)}\nSpent: {format_sc(total_spent)}",
            inline=True
        )
        
        crimes = stats_data.get("crimes_total", 0)
        crimes_success = stats_data.get("crimes_successful", 0)
        success_rate = int((crimes_success / crimes * 100)) if crimes > 0 else 0
        
        embed.add_field(
            name="🔪 Crime",
            value=f"Attempted: {crimes}\nSuccessful: {crimes_success} ({success_rate}%)",
            inline=True
        )
        
        heists = stats_data.get("heists_participated", 0)
        heists_success = stats_data.get("heists_successful", 0)
        heist_rate = int((heists_success / heists * 100)) if heists > 0 else 0
        
        embed.add_field(
            name="💰 Heists",
            value=f"Participated: {heists}\nSuccessful: {heists_success} ({heist_rate}%)",
            inline=True
        )
        
        embed.add_field(
            name="🏢 Business",
            value=f"Owned: {stats_data.get('businesses_owned', 0)}",
            inline=True
        )
        
        embed.add_field(
            name="📈 Trading",
            value=f"Trades: {stats_data.get('stocks_traded', 0)}",
            inline=True
        )
        
        return embed


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))