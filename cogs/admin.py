import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from utils.checks import requires_dev
from utils.formatters import format_sc


class AdminCog(commands.Cog):
    """Admin commands - dev only, prefix commands + dev-help slash"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.cogs.admin")

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check if user is dev for all prefix commands"""
        result = await self.bot.ctx.get_player(ctx.author.id)
        if not result.get("success"):
            return False
        player = result.get("data", {})
        return player.get("system_role") == "dev"

    # ─────────────────────────────────────────────────────────────
    # DEV-HELP (Slash command)
    # ─────────────────────────────────────────────────────────────

    @app_commands.command(name="dev_help", description="[DEV] Show all admin commands")
    @requires_dev()
    async def dev_help(self, interaction: discord.Interaction):
        """Display all available admin commands"""
        
        embed = discord.Embed(
            title="🛠️ Developer Commands",
            description="All commands are prefix commands using `s!`\n",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="💰 Economy",
            value="`s!give <@user> <amount> [reason]` - Give SC\n"
                  "`s!take <@user> <amount> [reason]` - Take SC\n"
                  "`s!set_rep <@user> <amount>` - Set reputation",
            inline=False
        )
        
        embed.add_field(
            name="💎 Premium",
            value="`s!set_premium <@user> <tier> <days>` - Set premium tier\n"
                  "`s!remove_premium <@user>` - Remove premium",
            inline=False
        )
        
        embed.add_field(
            name="🏅 Role",
            value="`s!set_role <@user> <role>` - Set system role\n"
                  "`s!get_role <@user>` - Check user's role",
            inline=False
        )
        
        embed.add_field(
            name="🔒 Jail",
            value="`s!jail <@user> <hours> [reason]` - Jail player\n"
                  "`s!release <@user>` - Release from jail",
            inline=False
        )
        
        embed.add_field(
            name="🚫 Ban",
            value="`s!ban <@user> <reason>` - Ban player\n"
                  "`s!unban <@user>` - Unban player",
            inline=False
        )
        
        embed.add_field(
            name="📊 Info",
            value="`s!stats` - Bot statistics\n"
                  "`s!player <@user>` - View player data\n"
                  "`s!cooldowns <@user>` - View player cooldowns",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ System",
            value="`s!reset_cooldown <@user> <action>` - Reset specific cooldown\n"
                  "`s!reload <cog>` - Reload a cog\n"
                  "`s!announce <#channel> <title> | <message>` - Send announcement",
            inline=False
        )

        embed.add_field(
            name="👥 Developer Management",
            value="`s!add_dev <@user>` - Add user as developer\n"
                "`s!remove_dev <@user>` - Remove developer",
            inline=False
        )
        
        embed.set_footer(text="Use s! before each command | Dev only")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─────────────────────────────────────────────────────────────
    # ECONOMY COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="give")
    async def admin_give(self, ctx: commands.Context, user: discord.User, amount: int, *, reason: str = "Admin grant"):
        """Give SC to a player. Usage: s!give @user 1000 reason"""
        
        if amount <= 0:
            await ctx.send("❌ Amount must be positive.")
            return
        
        result = await self.bot.ctx.get_player(user.id)
        if not result.get("success"):
            await ctx.send(f"❌ Player {user.mention} not found.")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE players SET wallet = wallet + $2
                    WHERE discord_id = $1
                    RETURNING wallet
                """, user.id, amount)
                
                await conn.execute("""
                    INSERT INTO transactions (discord_id, amount, balance_after, tx_type, description, related_id)
                    VALUES ($1, $2, $3, 'admin_grant', $4, $5)
                """, user.id, amount, row["wallet"], reason, ctx.author.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="✅ Admin Grant",
            description=f"Gave {format_sc(amount)} to {user.mention}\nNew wallet: {format_sc(row['wallet'])}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} gave {amount} SC to {user.id}")

    @commands.command(name="take")
    async def admin_take(self, ctx: commands.Context, user: discord.User, amount: int, *, reason: str = "Admin deduction"):
        """Take SC from a player. Usage: s!take @user 1000 reason"""
        
        if amount <= 0:
            await ctx.send("❌ Amount must be positive.")
            return
        
        result = await self.bot.ctx.get_player(user.id)
        if not result.get("success"):
            await ctx.send(f"❌ Player {user.mention} not found.")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE players SET wallet = wallet - $2
                    WHERE discord_id = $1 AND wallet >= $2
                    RETURNING wallet
                """, user.id, amount)
                
                if not row:
                    await ctx.send(f"❌ Player {user.mention} doesn't have {format_sc(amount)}.")
                    return
                
                await conn.execute("""
                    INSERT INTO transactions (discord_id, amount, balance_after, tx_type, description, related_id)
                    VALUES ($1, $2, $3, 'admin_deduct', $4, $5)
                """, user.id, -amount, row["wallet"], reason, ctx.author.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="⚠️ Admin Deduction",
            description=f"Took {format_sc(amount)} from {user.mention}\nNew wallet: {format_sc(row['wallet'])}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} took {amount} SC from {user.id}")

    @commands.command(name="set_rep")
    async def admin_set_rep(self, ctx: commands.Context, user: discord.User, amount: int):
        """Set player reputation. Usage: s!set_rep @user 5000"""
        
        if amount < 0:
            await ctx.send("❌ Reputation cannot be negative.")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE players 
                    SET reputation = $2,
                        rep_rank = GREATEST(1, LEAST(10, FLOOR($2 / 1000) + 1))
                    WHERE discord_id = $1
                    RETURNING reputation, rep_rank
                """, user.id, amount)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="⭐ Reputation Set",
            description=f"{user.mention} now has **{row['reputation']}** reputation (Rank {row['rep_rank']})",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} set {user.id} rep to {amount}")

    # ─────────────────────────────────────────────────────────────
    # PREMIUM COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="set_premium")
    async def admin_set_premium(self, ctx: commands.Context, user: discord.User, tier: str, days: int):
        """Set premium tier. Usage: s!set_premium @user elite 30"""
        
        valid_tiers = ["citizen", "resident", "elite", "obsidian"]
        
        if tier.lower() not in valid_tiers:
            await ctx.send(f"❌ Invalid tier. Options: {', '.join(valid_tiers)}")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET premium_tier = $2, premium_expires = NOW() + ($3 || ' days')::INTERVAL
                WHERE discord_id = $1
            """, user.id, tier.lower(), days)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="💎 Premium Set",
            description=f"{user.mention} now has **{tier.title()}** tier for {days} days.",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} set {user.id} to {tier} for {days} days")

    @commands.command(name="remove_premium")
    async def admin_remove_premium(self, ctx: commands.Context, user: discord.User):
        """Remove premium from a player. Usage: s!remove_premium @user"""
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET premium_tier = 'citizen', premium_expires = NULL
                WHERE discord_id = $1
            """, user.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="💎 Premium Removed",
            description=f"{user.mention} is now **Citizen** tier.",
            color=discord.Color.grey(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} removed premium from {user.id}")

    # ─────────────────────────────────────────────────────────────
    # ROLE COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="set_role")
    async def admin_set_role(self, ctx: commands.Context, user: discord.User, role: str):
        """Set system role. Usage: s!set_role @user dev"""
        
        valid_roles = ["player", "beta_tester", "mod", "dev"]
        
        if role.lower() not in valid_roles:
            await ctx.send(f"❌ Invalid role. Options: {', '.join(valid_roles)}")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET system_role = $2 WHERE discord_id = $1
            """, user.id, role.lower())
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        role_icons = {
            "player": "👤",
            "beta_tester": "🧪",
            "mod": "🛡️",
            "dev": "🛠️"
        }
        
        embed = discord.Embed(
            title=f"{role_icons.get(role.lower(), '🏅')} Role Set",
            description=f"{user.mention} now has system role: **{role.lower()}**",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} set {user.id} to role {role}")

    @commands.command(name="get_role")
    async def admin_get_role(self, ctx: commands.Context, user: discord.User):
        """Check a player's system role. Usage: s!get_role @user"""
        
        result = await self.bot.ctx.get_player(user.id)
        
        if not result.get("success"):
            await ctx.send(f"❌ Player {user.mention} not found.")
            return
        
        player = result.get("data", {})
        
        role_icons = {
            "player": "👤",
            "beta_tester": "🧪",
            "mod": "🛡️",
            "dev": "🛠️"
        }
        
        role = player.get("system_role", "player")
        
        embed = discord.Embed(
            title=f"{role_icons.get(role, '🏅')} Player Role",
            description=f"{user.mention} has system role: **{role}**",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────
    # JAIL COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="jail")
    async def admin_jail(self, ctx: commands.Context, user: discord.User, hours: int, *, reason: str = "No reason"):
        """Jail a player. Usage: s!jail @user 24 reason"""
        
        if hours < 1 or hours > 168:
            await ctx.send("❌ Hours must be between 1 and 168.")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET is_jailed = TRUE,
                    jail_until = NOW() + ($2 || ' hours')::INTERVAL,
                    business_efficiency = 0.5
                WHERE discord_id = $1
            """, user.id, hours)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="🔒 Player Jailed",
            description=f"{user.mention} has been jailed for {hours} hours.\n**Reason:** {reason}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} jailed {user.id} for {hours}h")

    @commands.command(name="release")
    async def admin_release(self, ctx: commands.Context, user: discord.User):
        """Release a player from jail. Usage: s!release @user"""
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET is_jailed = FALSE, jail_until = NULL, business_efficiency = 1.0
                WHERE discord_id = $1
            """, user.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="🔓 Player Released",
            description=f"{user.mention} has been released from jail.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} released {user.id}")

    # ─────────────────────────────────────────────────────────────
    # BAN COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="ban")
    async def admin_ban(self, ctx: commands.Context, user: discord.User, *, reason: str):
        """Ban a player. Usage: s!ban @user reason"""
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET is_banned = TRUE, ban_reason = $2 WHERE discord_id = $1
            """, user.id, reason)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="🔨 Player Banned",
            description=f"{user.mention} has been banned.\n**Reason:** {reason}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} banned {user.id}")

    @commands.command(name="unban")
    async def admin_unban(self, ctx: commands.Context, user: discord.User):
        """Unban a player. Usage: s!unban @user"""
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET is_banned = FALSE, ban_reason = NULL WHERE discord_id = $1
            """, user.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="✅ Player Unbanned",
            description=f"{user.mention} has been unbanned.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} unbanned {user.id}")

    # ─────────────────────────────────────────────────────────────
    # INFO COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="stats")
    async def admin_stats(self, ctx: commands.Context):
        """Show bot statistics. Usage: s!stats"""
        
        async with self.bot.db.pool.acquire() as conn:
            total_players = await conn.fetchval("SELECT COUNT(*) FROM players")
            active_today = await conn.fetchval("""
                SELECT COUNT(DISTINCT discord_id) FROM interaction_log 
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            banned = await conn.fetchval("SELECT COUNT(*) FROM players WHERE is_banned = TRUE")
            premium = await conn.fetchval("SELECT COUNT(*) FROM players WHERE premium_tier != 'citizen'")
            total_sc = await conn.fetchval("SELECT COALESCE(SUM(wallet + bank), 0) FROM players")
            dev_count = await conn.fetchval("SELECT COUNT(*) FROM players WHERE system_role = 'dev'")
            mod_count = await conn.fetchval("SELECT COUNT(*) FROM players WHERE system_role = 'mod'")
            beta_count = await conn.fetchval("SELECT COUNT(*) FROM players WHERE system_role = 'beta_tester'")
            jailed = await conn.fetchval("SELECT COUNT(*) FROM players WHERE is_jailed = TRUE")
        
        embed = discord.Embed(
            title="📊 SimCoin Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="👥 Total Players", value=str(total_players), inline=True)
        embed.add_field(name="📈 Active Today", value=str(active_today), inline=True)
        embed.add_field(name="🚫 Banned", value=str(banned), inline=True)
        embed.add_field(name="🔒 Jailed", value=str(jailed), inline=True)
        embed.add_field(name="💎 Premium", value=str(premium), inline=True)
        embed.add_field(name="💰 SC in Circulation", value=f"{total_sc:,}", inline=True)
        embed.add_field(name="🌐 Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="⏱️ Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="🛠️ Devs", value=str(dev_count), inline=True)
        embed.add_field(name="🛡️ Mods", value=str(mod_count), inline=True)
        embed.add_field(name="🧪 Beta Testers", value=str(beta_count), inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name="player")
    async def admin_player(self, ctx: commands.Context, user: discord.User):
        """View detailed player data. Usage: s!player @user"""
        
        result = await self.bot.ctx.get_player(user.id)
        
        if not result.get("success"):
            await ctx.send(f"❌ Player {user.mention} not found.")
            return
        
        player = result.get("data", {})
        
        embed = discord.Embed(
            title=f"👤 Player Data: {player.get('username', 'Unknown')}",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="ID", value=player.get('discord_id'), inline=True)
        embed.add_field(name="Wallet", value=format_sc(player.get('wallet', 0)), inline=True)
        embed.add_field(name="Bank", value=format_sc(player.get('bank', 0)), inline=True)
        embed.add_field(name="Net Worth", value=format_sc(player.get('wallet', 0) + player.get('bank', 0)), inline=True)
        embed.add_field(name="Reputation", value=f"{player.get('reputation', 0)} (Rank {player.get('rep_rank', 1)})", inline=True)
        embed.add_field(name="District", value=player.get('district', 1), inline=True)
        embed.add_field(name="Prestige", value=player.get('prestige', 0), inline=True)
        embed.add_field(name="Premium Tier", value=player.get('premium_tier', 'citizen'), inline=True)
        embed.add_field(name="System Role", value=player.get('system_role', 'player'), inline=True)
        embed.add_field(name="Jailed", value="Yes" if player.get('is_jailed') else "No", inline=True)
        embed.add_field(name="Banned", value="Yes" if player.get('is_banned') else "No", inline=True)
        
        if player.get('premium_expires'):
            embed.add_field(name="Premium Expires", value=player['premium_expires'].strftime('%Y-%m-%d %H:%M UTC'), inline=True)
        
        if player.get('jail_until'):
            embed.add_field(name="Jail Until", value=player['jail_until'].strftime('%Y-%m-%d %H:%M UTC'), inline=True)
        
        embed.add_field(name="Created At", value=player.get('created_at', datetime.now()).strftime('%Y-%m-%d %H:%M UTC'), inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name="cooldowns")
    async def admin_cooldowns(self, ctx: commands.Context, user: discord.User):
        """View player's active cooldowns. Usage: s!cooldowns @user"""
        
        async with self.bot.db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT action, expires_at FROM cooldowns
                WHERE discord_id = $1 AND expires_at > NOW()
                ORDER BY expires_at ASC
            """, user.id)
        
        if not rows:
            await ctx.send(f"✅ {user.mention} has no active cooldowns.")
            return
        
        embed = discord.Embed(
            title=f"⏰ Cooldowns for {user.name}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        for row in rows:
            remaining = (row["expires_at"] - datetime.now(timezone.utc)).total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            embed.add_field(
                name=row["action"],
                value=f"Expires in {hours}h {minutes}m",
                inline=True
            )
        
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────
    # SYSTEM COMMANDS (Prefix)
    # ─────────────────────────────────────────────────────────────

    @commands.command(name="reset_cooldown")
    async def admin_reset_cooldown(self, ctx: commands.Context, user: discord.User, action: str):
        """Reset a player's cooldown. Usage: s!reset_cooldown @user work"""
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM cooldowns WHERE discord_id = $1 AND action = $2
            """, user.id, action)
        
        await self.bot.cache.delete_pattern(f"cooldown:{user.id}:*")
        
        embed = discord.Embed(
            title="✅ Cooldown Reset",
            description=f"Reset `{action}` cooldown for {user.mention}.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Admin {ctx.author.id} reset {action} cooldown for {user.id}")

    @commands.command(name="reload")
    async def admin_reload(self, ctx: commands.Context, cog_name: str = None):
        """Reload a cog. Usage: s!reload admin or s!reload all"""
        
        if cog_name == "all":
            loaded = 0
            failed = []
            for cog in list(self.bot.extensions.keys()):
                try:
                    await self.bot.reload_extension(cog)
                    loaded += 1
                except Exception as e:
                    failed.append(f"{cog}: {e}")
            
            await ctx.send(f"✅ Reloaded {loaded} cogs." + (f"\n❌ Failed: {', '.join(failed)}" if failed else ""))
        
        else:
            try:
                await self.bot.reload_extension(f"cogs.{cog_name}")
                await ctx.send(f"✅ Reloaded cog: `{cog_name}`")
            except Exception as e:
                await ctx.send(f"❌ Failed to reload `{cog_name}`: {e}")

    @commands.command(name="announce")
    async def admin_announce(self, ctx: commands.Context, channel: discord.TextChannel, *, title_and_message: str):
        """Send announcement embed. Usage: s!announce #channel Title | Message"""
        
        if " | " not in title_and_message:
            await ctx.send("❌ Use format: `Title | Message`")
            return
        
        title, message = title_and_message.split(" | ", 1)
        
        embed = discord.Embed(
            title=f"📢 {title}",
            description=message,
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Simora City • {ctx.author.name}")
        
        await channel.send(embed=embed)
        await ctx.send(f"✅ Announcement sent to {channel.mention}")

    @commands.command(name="add_dev")
    async def admin_add_dev(self, ctx: commands.Context, user: discord.User):
        """Add a user as developer. Usage: s!add_dev @user"""
        
        current_result = await self.bot.ctx.get_player(ctx.author.id)
        if not current_result.get("success"):
            await ctx.send("❌ You are not registered.")
            return
        
        current_player = current_result.get("data", {})
        if current_player.get("system_role") != "dev":
            await ctx.send("❌ Only existing developers can add new developers.")
            return
        
        target_result = await self.bot.ctx.get_player(user.id)
        if not target_result.get("success"):
            await ctx.send(f"❌ Player {user.mention} not found. They need to run `/start` first.")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET system_role = 'dev' WHERE discord_id = $1
            """, user.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="🛠️ Developer Added",
            description=f"{user.mention} is now a developer.\nThey can now use all `s!` admin commands.",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Dev {ctx.author.id} added {user.id} as dev")

    @commands.command(name="remove_dev")
    async def admin_remove_dev(self, ctx: commands.Context, user: discord.User):
        """Remove a user from developer role. Usage: s!remove_dev @user"""
        
        current_result = await self.bot.ctx.get_player(ctx.author.id)
        if not current_result.get("success"):
            await ctx.send("❌ You are not registered.")
            return
        
        current_player = current_result.get("data", {})
        if current_player.get("system_role") != "dev":
            await ctx.send("❌ Only existing developers can remove developers.")
            return
        
        if user.id == ctx.author.id:
            await ctx.send("❌ You cannot remove yourself as developer.")
            return
        
        target_result = await self.bot.ctx.get_player(user.id)
        if not target_result.get("success"):
            await ctx.send(f"❌ Player {user.mention} not found.")
            return
        
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET system_role = 'player' WHERE discord_id = $1
            """, user.id)
        
        await self.bot.cache.delete(self.bot.cache.generate_key("player", user.id))
        
        embed = discord.Embed(
            title="🛠️ Developer Removed",
            description=f"{user.mention} is no longer a developer.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await ctx.send(embed=embed)
        self.logger.info(f"Dev {ctx.author.id} removed {user.id} as dev")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))