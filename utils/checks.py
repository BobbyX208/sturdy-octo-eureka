import discord
from discord.ext import commands
from typing import Optional, Callable, Any
import functools
from datetime import datetime, timezone

from utils.formatters import format_time


def requires_profile():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            await interaction.response.send_message("Bot not ready. Try again.", ephemeral=True)
            return False
        
        player = await bot.services.player.get(user_id)
        
        if not player:
            await interaction.response.send_message(
                "You need to register first! Use `/start` to begin your journey in Simora City.",
                ephemeral=True
            )
            return False
        
        if player.get("is_banned", False):
            await interaction.response.send_message(
                "Your account is banned from SimCoin. Appeal via mod ticket.",
                ephemeral=True
            )
            return False
        
        if player.get("is_jailed", False):
            from utils.formatters import format_relative_time
            jail_until = player.get("jail_until")
            if jail_until:
                remaining = (jail_until - datetime.now(timezone.utc)).total_seconds()
                if remaining > 0:
                    await interaction.response.send_message(
                        f"You are in jail for another {format_time(int(remaining))}. Come back then.",
                        ephemeral=True
                    )
                    return False
            
            await interaction.response.send_message(
                "You are in jail and cannot use commands. Wait for release.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)


def requires_premium(tier: str = "resident"):
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            await interaction.response.send_message("Bot not ready. Try again.", ephemeral=True)
            return False
        
        player = await bot.services.player.get(user_id)
        
        if not player:
            await interaction.response.send_message(
                "You need to register first! Use `/start` to begin.",
                ephemeral=True
            )
            return False
        
        current_tier = player.get("premium_tier", "citizen")
        expires = player.get("premium_expires")
        
        if current_tier == "citizen":
            await interaction.response.send_message(
                f"This command requires {tier.title()} tier or higher. Upgrade with `/premium`.",
                ephemeral=True
            )
            return False
        
        if expires and expires < datetime.now(timezone.utc):
            await interaction.response.send_message(
                f"Your premium subscription has expired. Renew with `/premium` to use this command.",
                ephemeral=True
            )
            return False
        
        tier_order = {"citizen": 0, "resident": 1, "elite": 2, "obsidian": 3}
        required_level = tier_order.get(tier, 1)
        current_level = tier_order.get(current_tier, 0)
        
        if current_level < required_level:
            await interaction.response.send_message(
                f"This command requires {tier.title()} tier. You have {current_tier.title()}.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)


def requires_rep(min_rep: int):
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            await interaction.response.send_message("Bot not ready. Try again.", ephemeral=True)
            return False
        
        player = await bot.services.player.get(user_id)
        
        if not player:
            await interaction.response.send_message(
                "You need to register first! Use `/start` to begin.",
                ephemeral=True
            )
            return False
        
        reputation = player.get("reputation", 0)
        
        if reputation < min_rep:
            await interaction.response.send_message(
                f"This command requires {min_rep} reputation. You have {reputation}.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)


def requires_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            await interaction.response.send_message("Bot not ready. Try again.", ephemeral=True)
            return False
        
        player = await bot.services.player.get(user_id)
        
        if not player:
            await interaction.response.send_message("Player not found.", ephemeral=True)
            return False
        
        system_role = player.get("system_role", "player")
        
        if system_role not in ["mod", "dev"]:
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)


def requires_dev():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            await interaction.response.send_message("Bot not ready. Try again.", ephemeral=True)
            return False
        
        player = await bot.services.player.get(user_id)
        
        if not player:
            await interaction.response.send_message("Player not found.", ephemeral=True)
            return False
        
        system_role = player.get("system_role", "player")
        
        if system_role != "dev":
            await interaction.response.send_message(
                "Developer only command.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)


def not_jailed():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            return True
        
        player = await bot.services.player.get(user_id)
        
        if player and player.get("is_jailed", False):
            await interaction.response.send_message(
                "You are in jail and cannot use this command.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)


def has_cooldown(action: str, cooldown_seconds: int):
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        user_id = interaction.user.id
        
        if not hasattr(bot, "services") or not bot.services:
            return True
        
        is_active = await bot.services.cooldowns.is_active(user_id, action)
        
        if is_active:
            remaining = await bot.services.cooldowns.get_remaining(user_id, action)
            from utils.formatters import format_time
            await interaction.response.send_message(
                f"Command on cooldown. Try again in {format_time(remaining)}.",
                ephemeral=True
            )
            return False
        
        return True
    
    return discord.app_commands.check(predicate)