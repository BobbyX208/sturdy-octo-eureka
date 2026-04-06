import io
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import os

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import discord

from core.cache import CacheManager
from config.settings import Config
from config.constants import GameConstants


_executor = ThreadPoolExecutor(max_workers=Config.IMAGE_THREAD_POOL_SIZE)


class ImageService:
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.logger = logging.getLogger("simcoin.services.image")
        self._font_cache = {}
    
    def _get_font(self, size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
        cache_key = f"{size}_{bold}_{italic}"
        
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        try:
            if bold and italic:
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"
            elif bold:
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            elif italic:
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"
            else:
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            
            font = ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
            except (OSError, IOError):
                font = ImageFont.load_default()
        
        self._font_cache[cache_key] = font
        return font
    
    async def generate_profile_card(self, player_data: Dict[str, Any]) -> discord.File:
        try:
            cache_key = self.cache.generate_key(
                "profile",
                player_data.get("discord_id"),
                player_data.get("wallet", 0),
                player_data.get("bank", 0),
                player_data.get("reputation", 0),
                player_data.get("district", 1),
                player_data.get("premium_tier", "citizen"),
                player_data.get("prestige", 0)
            )
            
            cached = await self.cache.get(cache_key)
            if cached:
                return discord.File(io.BytesIO(cached), filename="profile.png")
            
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                _executor,
                self._render_profile_card,
                player_data
            )
            
            await self.cache.set(cache_key, png_bytes, ttl=GameConstants.IMAGE_CACHE_TTL_HOURS * 3600)
            
            return discord.File(io.BytesIO(png_bytes), filename="profile.png")
            
        except Exception as e:
            self.logger.error(f"Generate profile card failed: {e}")
            raise
    
    def _render_profile_card(self, player_data: Dict[str, Any]) -> bytes:
        width = GameConstants.PROFILE_CARD_WIDTH
        height = GameConstants.PROFILE_CARD_HEIGHT
        
        img = Image.new("RGBA", (width, height), (15, 20, 35, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        
        self._draw_gradient_background(draw, width, height)
        
        self._draw_card_border(draw, width, height)
        
        username = player_data.get("username", "Unknown")[:20]
        font_title = self._get_font(28, bold=True)
        draw.text((30, 30), username, font=font_title, fill=(255, 215, 0))
        
        premium_tier = player_data.get("premium_tier", "citizen")
        tier_colors = {
            "citizen": (128, 128, 128),
            "resident": (0, 128, 255),
            "elite": (255, 215, 0),
            "obsidian": (128, 0, 128)
        }
        tier_color = tier_colors.get(premium_tier, (128, 128, 128))
        
        font_tier = self._get_font(14, bold=True)
        draw.text((width - 120, 35), premium_tier.upper(), font=font_tier, fill=tier_color)
        
        font_small = self._get_font(12)
        font_value = self._get_font(18, bold=True)
        
        y = 100
        stats = [
            ("💰 Wallet", self._format_sc(player_data.get("wallet", 0))),
            ("🏦 Bank", self._format_sc(player_data.get("bank", 0))),
            ("📊 Net Worth", self._format_sc(player_data.get("wallet", 0) + player_data.get("bank", 0))),
            ("⭐ Reputation", str(player_data.get("reputation", 0))),
            ("🏆 Rank", self._get_rank_name(player_data.get("rep_rank", 1))),
            ("🏙️ District", self._get_district_name(player_data.get("district", 1))),
            ("💎 Prestige", str(player_data.get("prestige", 0))),
        ]
        
        x = 30
        col_width = (width - 60) // 2
        
        for i, (label, value) in enumerate(stats):
            row = i // 2
            col = i % 2
            pos_x = x + (col * col_width)
            pos_y = y + (row * 45)
            
            draw.text((pos_x, pos_y), label, font=font_small, fill=(180, 180, 200))
            draw.text((pos_x, pos_y + 20), value, font=font_value, fill=(255, 255, 255))
        
        if player_data.get("system_role", "player") not in ["player", "citizen"]:
            badge_x = width - 100
            badge_y = height - 60
            role = player_data.get("system_role", "").replace("_", " ").title()
            
            draw.rounded_rectangle([badge_x - 5, badge_y - 5, badge_x + 80, badge_y + 25], radius=8, fill=(0, 0, 0, 180))
            draw.text((badge_x, badge_y), role, font=font_small, fill=(255, 215, 0))
        
        if player_data.get("is_jailed", False):
            draw.rounded_rectangle([width - 150, height - 60, width - 20, height - 25], radius=8, fill=(200, 50, 50, 200))
            draw.text((width - 140, height - 55), "🔒 JAILED", font=font_small, fill=(255, 255, 255))
        
        font_footer = self._get_font(9)
        draw.text((width - 150, height - 20), "simora.city", font=font_footer, fill=(80, 90, 110))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        
        return buf.read()
    
    async def generate_leaderboard_card(self, title: str, entries: List[Dict[str, Any]], current_user_id: int = None) -> discord.File:
        try:
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                _executor,
                self._render_leaderboard_card,
                title,
                entries,
                current_user_id
            )
            
            return discord.File(io.BytesIO(png_bytes), filename="leaderboard.png")
            
        except Exception as e:
            self.logger.error(f"Generate leaderboard card failed: {e}")
            raise
    
    def _render_leaderboard_card(self, title: str, entries: List[Dict[str, Any]], current_user_id: int = None) -> bytes:
        width = GameConstants.LEADERBOARD_CARD_WIDTH
        height = GameConstants.LEADERBOARD_CARD_HEIGHT
        
        img = Image.new("RGBA", (width, height), (15, 20, 35, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        
        self._draw_gradient_background(draw, width, height)
        
        font_title = self._get_font(24, bold=True)
        draw.text((width // 2 - 100, 20), f"🏆 {title}", font=font_title, fill=(255, 215, 0))
        
        font_header = self._get_font(12, bold=True)
        font_entry = self._get_font(11)
        
        y = 70
        draw.text((30, y), "#", font=font_header, fill=(180, 180, 200))
        draw.text((70, y), "Player", font=font_header, fill=(180, 180, 200))
        draw.text((width - 100, y), "Value", font=font_header, fill=(180, 180, 200))
        
        y += 25
        
        for i, entry in enumerate(entries[:10]):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            
            username = entry.get("username", "Unknown")[:15]
            value = entry.get("value", entry.get("wallet", 0))
            
            if isinstance(value, int):
                if "SC" in title or "wealth" in title.lower():
                    value_str = self._format_sc(value)
                else:
                    value_str = str(value)
            else:
                value_str = str(value)
            
            is_current = current_user_id and entry.get("discord_id") == current_user_id
            font = self._get_font(12, bold=is_current)
            color = (255, 215, 0) if is_current else (255, 255, 255)
            
            draw.text((30, y), medal, font=font, fill=color)
            draw.text((70, y), username, font=font, fill=color)
            draw.text((width - 100, y), value_str, font=font, fill=color)
            
            y += 30
            
            if y > height - 60:
                break
        
        font_footer = self._get_font(9)
        draw.text((width - 150, height - 20), "simora.city | Leaderboard", font=font_footer, fill=(80, 90, 110))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        
        return buf.read()
    
    async def generate_rank_up_card(self, user_id: int, new_rank: int, title: str) -> discord.File:
        try:
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                _executor,
                self._render_rank_up_card,
                user_id,
                new_rank,
                title
            )
            
            return discord.File(io.BytesIO(png_bytes), filename="rank_up.png")
            
        except Exception as e:
            self.logger.error(f"Generate rank up card failed: {e}")
            raise
    
    def _render_rank_up_card(self, user_id: int, new_rank: int, title: str) -> bytes:
        width = 600
        height = 300
        
        img = Image.new("RGBA", (width, height), (15, 20, 35, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        
        self._draw_gradient_background(draw, width, height)
        
        font_large = self._get_font(32, bold=True)
        draw.text((width // 2 - 80, 80), "RANK UP!", font=font_large, fill=(255, 215, 0))
        
        font_rank = self._get_font(24, bold=True)
        draw.text((width // 2 - 50, 150), f"Rank {new_rank}", font=font_rank, fill=(255, 255, 255))
        
        font_title = self._get_font(18)
        draw.text((width // 2 - 60, 190), title, font=font_title, fill=(180, 180, 200))
        
        font_footer = self._get_font(9)
        draw.text((width - 150, height - 20), "simora.city", font=font_footer, fill=(80, 90, 110))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        
        return buf.read()
    
    async def generate_prestige_card(self, user_id: int, prestige_level: int) -> discord.File:
        try:
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                _executor,
                self._render_prestige_card,
                user_id,
                prestige_level
            )
            
            return discord.File(io.BytesIO(png_bytes), filename="prestige.png")
            
        except Exception as e:
            self.logger.error(f"Generate prestige card failed: {e}")
            raise
    
    def _render_prestige_card(self, user_id: int, prestige_level: int) -> bytes:
        width = 600
        height = 400
        
        img = Image.new("RGBA", (width, height), (15, 20, 35, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        
        self._draw_gradient_background(draw, width, height)
        
        font_large = self._get_font(36, bold=True)
        draw.text((width // 2 - 120, 100), "✨ PRESTIGE ✨", font=font_large, fill=(255, 215, 0))
        
        font_level = self._get_font(48, bold=True)
        draw.text((width // 2 - 30, 180), str(prestige_level), font=font_level, fill=(255, 255, 255))
        
        font_text = self._get_font(14)
        draw.text((width // 2 - 150, 250), "You have been reborn. The city remembers.", font=font_text, fill=(180, 180, 200))
        
        font_footer = self._get_font(9)
        draw.text((width - 150, height - 20), "simora.city", font=font_footer, fill=(80, 90, 110))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        
        return buf.read()
    
    async def generate_heist_card(self, heist_data: Dict[str, Any]) -> discord.File:
        try:
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                _executor,
                self._render_heist_card,
                heist_data
            )
            
            return discord.File(io.BytesIO(png_bytes), filename="heist.png")
            
        except Exception as e:
            self.logger.error(f"Generate heist card failed: {e}")
            raise
    
    def _render_heist_card(self, heist_data: Dict[str, Any]) -> bytes:
        width = 800
        height = 500
        
        img = Image.new("RGBA", (width, height), (15, 20, 35, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        
        self._draw_gradient_background(draw, width, height)
        
        success = heist_data.get("success", False)
        color = (100, 200, 100) if success else (200, 100, 100)
        
        title = "HEIST SUCCESSFUL!" if success else "HEIST FAILED"
        font_title = self._get_font(32, bold=True)
        draw.text((width // 2 - 120, 50), title, font=font_title, fill=color)
        
        font_stats = self._get_font(18)
        
        y = 150
        draw.text((50, y), f"District: {heist_data.get('district', 'Unknown')}", font=font_stats, fill=(255, 255, 255))
        draw.text((50, y + 40), f"Participants: {len(heist_data.get('participants', []))}", font=font_stats, fill=(255, 255, 255))
        
        if success:
            draw.text((50, y + 80), f"Loot: {self._format_sc(heist_data.get('loot', 0))}", font=font_stats, fill=(255, 215, 0))
            
            per_player = heist_data.get('loot', 0) // max(len(heist_data.get('participants', [])), 1)
            draw.text((50, y + 120), f"Per Player: {self._format_sc(per_player)}", font=font_stats, fill=(180, 180, 200))
        else:
            draw.text((50, y + 80), "All participants jailed.", font=font_stats, fill=(200, 100, 100))
        
        font_footer = self._get_font(9)
        draw.text((width - 150, height - 20), "simora.city | Heist Report", font=font_footer, fill=(80, 90, 110))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        
        return buf.read()
    
    def _draw_gradient_background(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        for y in range(height):
            ratio = y / height
            r = int(15 + (10 * ratio))
            g = int(20 + (15 * ratio))
            b = int(35 + (20 * ratio))
            draw.line([(0, y), (width, y)], fill=(r, g, b), width=1)
    
    def _draw_card_border(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        draw.rectangle([0, 0, width, height], outline=(255, 215, 0), width=2)
        draw.rectangle([5, 5, width - 5, height - 5], outline=(100, 100, 150), width=1)
    
    def _format_sc(self, amount: int) -> str:
        if amount >= 1000000:
            return f"{amount/1000000:.1f}M"
        elif amount >= 1000:
            return f"{amount/1000:.1f}K"
        else:
            return str(amount)
    
    def _get_rank_name(self, rank: int) -> str:
        ranks = {
            1: "Newcomer", 2: "Recognized", 3: "Known", 4: "Respected",
            5: "Prominent", 6: "Influential", 7: "City Icon", 8: "Legend",
            9: "Mythic", 10: "Simora Royalty"
        }
        return ranks.get(rank, "Unknown")
    
    def _get_district_name(self, district_id: int) -> str:
        districts = {
            1: "Slums", 2: "Industrial", 3: "Downtown",
            4: "Financial", 5: "The Strip", 6: "Underground"
        }
        return districts.get(district_id, "Unknown")
    
    async def close(self) -> None:
        self.logger.info("Image Service closed")