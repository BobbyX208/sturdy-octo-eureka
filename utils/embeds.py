import discord
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from config.constants import GameConstants


class EmbedBuilder:
    
    @staticmethod
    def success(title: str, description: str, footer: str = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=GameConstants.COLOR_SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def error(title: str, description: str, footer: str = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=GameConstants.COLOR_ERROR,
            timestamp=datetime.now(timezone.utc)
        )
         
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def warning(title: str, description: str, footer: str = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=GameConstants.COLOR_WARNING,
            timestamp=datetime.now(timezone.utc)
        )
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def info(title: str, description: str, footer: str = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=GameConstants.COLOR_INFO,
            timestamp=datetime.now(timezone.utc)
        )
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def economy(title: str, description: str, wallet: int = None, bank: int = None, footer: str = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"💰 {title}",
            description=description,
            color=GameConstants.COLOR_PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )
        
        if wallet is not None or bank is not None:
            field_value = ""
            if wallet is not None:
                field_value += f"**Wallet:** {EmbedBuilder.format_sc(wallet)}\n"
            if bank is not None:
                field_value += f"**Bank:** {EmbedBuilder.format_sc(bank)}"
            embed.add_field(name="Balance", value=field_value, inline=False)
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def crime(title: str, description: str, success: bool = None, loot: int = None, fine: int = None, jail: int = None) -> discord.Embed:
        if success:
            color = GameConstants.COLOR_WARNING
            emoji = "🔪"
        else:
            color = GameConstants.COLOR_ERROR
            emoji = "🚨"
        
        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        
        if loot is not None:
            embed.add_field(name="Loot", value=EmbedBuilder.format_sc(loot), inline=True)
        if fine is not None:
            embed.add_field(name="Fine", value=EmbedBuilder.format_sc(fine), inline=True)
        if jail is not None and jail > 0:
            embed.add_field(name="Jail Time", value=f"{jail} hours", inline=True)
        
        return embed
    
    @staticmethod
    def format_sc(amount: int) -> str:
        if amount >= 1000000:
            return f"{amount/1000000:.1f}M {GameConstants.EMOJI_SC}"
        elif amount >= 1000:
            return f"{amount/1000:.1f}K {GameConstants.EMOJI_SC}"
        else:
            return f"{amount} {GameConstants.EMOJI_SC}"
    
    @staticmethod
    def progress_bar(current: int, max_value: int, length: int = 10, filled_char: str = "█", empty_char: str = "░") -> str:
        if max_value <= 0:
            return empty_char * length
        
        ratio = min(current / max_value, 1.0)
        filled = int(length * ratio)
        
        return filled_char * filled + empty_char * (length - filled)
    
    @staticmethod
    def add_field_if(embed: discord.Embed, condition: bool, name: str, value: str, inline: bool = False) -> None:
        if condition:
            embed.add_field(name=name, value=value, inline=inline)
    
    @staticmethod
    def build_profile_embed(player_data: Dict[str, Any]) -> discord.Embed:
        embed = discord.Embed(
            title=f"📛 {player_data.get('username', 'Unknown')}",
            color=GameConstants.COLOR_PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )
        
        rep_rank = player_data.get("rep_rank", 1)
        rep_titles = {1: "Newcomer", 2: "Recognized", 3: "Known", 4: "Respected", 
                      5: "Prominent", 6: "Influential", 7: "City Icon", 8: "Legend", 
                      9: "Mythic", 10: "Simora Royalty"}
        rep_title = rep_titles.get(rep_rank, "Newcomer")
        
        embed.add_field(name="⭐ Reputation", value=f"{player_data.get('reputation', 0)} ({rep_title})", inline=True)
        embed.add_field(name="🏙️ District", value=EmbedBuilder._get_district_name(player_data.get("district", 1)), inline=True)
        embed.add_field(name="💎 Prestige", value=str(player_data.get("prestige", 0)), inline=True)
        
        embed.add_field(name="👛 Wallet", value=EmbedBuilder.format_sc(player_data.get("wallet", 0)), inline=True)
        embed.add_field(name="🏦 Bank", value=EmbedBuilder.format_sc(player_data.get("bank", 0)), inline=True)
        embed.add_field(name="📊 Net Worth", value=EmbedBuilder.format_sc(player_data.get("wallet", 0) + player_data.get("bank", 0)), inline=True)
        
        if player_data.get("premium_tier", "citizen") != "citizen":
            tier = player_data.get("premium_tier", "citizen").title()
            embed.add_field(name="💎 Premium", value=tier, inline=True)
        
        if player_data.get("system_role", "player") not in ["player", "citizen"]:
            role = player_data.get("system_role", "").replace("_", " ").title()
            embed.add_field(name="🏅 Badge", value=role, inline=True)
        
        if player_data.get("is_jailed", False):
            embed.add_field(name="🔒 Status", value="In Jail", inline=False)
        
        embed.set_footer(text=f"ID: {player_data.get('discord_id')}")
        
        return embed
    
    @staticmethod
    def _get_district_name(district_id: int) -> str:
        districts = {
            1: "Slums",
            2: "Industrial",
            3: "Downtown",
            4: "Financial District",
            5: "The Strip",
            6: "Underground"
        }
        return districts.get(district_id, "Unknown")
    
    @staticmethod
    def build_leaderboard_embed(title: str, entries: List[Dict[str, Any]], current_user_id: int = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"🏆 {title}",
            color=GameConstants.COLOR_PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )
        
        description = ""
        for i, entry in enumerate(entries[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            username = entry.get("username", "Unknown")
            value = entry.get("value", 0)
            
            if isinstance(value, int):
                if "SC" in title or "wealth" in title.lower():
                    value_str = EmbedBuilder.format_sc(value)
                else:
                    value_str = str(value)
            else:
                value_str = str(value)
            
            if current_user_id and entry.get("discord_id") == current_user_id:
                username = f"**{username}** (You)"
            
            description += f"{medal} {username} - {value_str}\n"
        
        embed.description = description
        
        return embed