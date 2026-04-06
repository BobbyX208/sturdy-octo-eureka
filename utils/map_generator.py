import io
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import discord

from core.cache import CacheManager
from config.constants import GameConstants


_executor = ThreadPoolExecutor(max_workers=4)


CANVAS_W = 1200
CANVAS_H = 800
BG_COLOR = (10, 14, 23)
GRID_COLOR = (30, 40, 60)
CURRENT_GLOW = (255, 215, 0)
EVENT_GLOW = (255, 100, 50)
FACTION_GLOW = (255, 215, 0)


DISTRICTS = {
    1: {
        "name": "The Slums",
        "emoji": "🏚️",
        "polygon": [(0, 560), (380, 500), (420, 600), (350, 800), (0, 800)],
        "color": (70, 55, 45),
        "text_color": (220, 220, 200),
        "label_pos": (80, 670),
        "entry_requirement": "None",
        "bonus": "Crime bonus"
    },
    2: {
        "name": "Industrial Zone",
        "emoji": "🏗️",
        "polygon": [(380, 500), (700, 350), (780, 550), (420, 600)],
        "color": (40, 85, 55),
        "text_color": (200, 255, 200),
        "label_pos": (520, 470),
        "entry_requirement": "Rep 2",
        "bonus": "Job bonus"
    },
    3: {
        "name": "Downtown",
        "emoji": "🏪",
        "polygon": [(420, 600), (780, 550), (820, 750), (350, 800)],
        "color": (45, 85, 180),
        "text_color": (255, 255, 255),
        "label_pos": (560, 700),
        "entry_requirement": "Rep 4",
        "bonus": "Business bonus"
    },
    4: {
        "name": "Financial District",
        "emoji": "🌆",
        "polygon": [(700, 350), (1100, 150), (1150, 500), (780, 550)],
        "color": (180, 120, 20),
        "text_color": (255, 245, 200),
        "label_pos": (880, 350),
        "entry_requirement": "Rep 6",
        "bonus": "Investment bonus"
    },
    5: {
        "name": "The Strip",
        "emoji": "🎭",
        "polygon": [(780, 550), (1150, 500), (1150, 800), (820, 750)],
        "color": (160, 45, 45),
        "text_color": (255, 220, 220),
        "label_pos": (950, 680),
        "entry_requirement": "Rep 8",
        "bonus": "Gambling bonus"
    },
    6: {
        "name": "Underground",
        "emoji": "🌿",
        "polygon": [(0, 0), (550, 0), (380, 500), (0, 560)],
        "color": (90, 50, 150),
        "text_color": (230, 220, 255),
        "label_pos": (150, 220),
        "entry_requirement": "Rep 10",
        "bonus": "Heist bonus"
    }
}


class MapGenerator:
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.logger = logging.getLogger("simcoin.map_generator")
        self.cache = cache_manager
        self._font_cache = {}
    
    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        cache_key = f"{size}_{bold}"
        
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        try:
            if bold:
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
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
    
    def _draw_background_grid(self, draw: ImageDraw.ImageDraw) -> None:
        for x in range(0, CANVAS_W, 50):
            draw.line([(x, 0), (x, CANVAS_H)], fill=GRID_COLOR, width=1)
        
        for y in range(0, CANVAS_H, 50):
            draw.line([(0, y), (CANVAS_W, y)], fill=GRID_COLOR, width=1)
        
        glow_color = (20, 30, 50)
        for x in range(0, CANVAS_W, 100):
            draw.line([(x, 0), (x, CANVAS_H)], fill=glow_color, width=1)
        for y in range(0, CANVAS_H, 100):
            draw.line([(0, y), (CANVAS_W, y)], fill=glow_color, width=1)
    
    def _draw_district(
        self,
        draw: ImageDraw.ImageDraw,
        district_id: int,
        info: Dict[str, Any],
        current_district: Optional[int],
        active_event_district: Optional[int],
        faction_control: Dict[int, str]
    ) -> None:
        polygon = info["polygon"]
        base_color = info["color"]
        
        if current_district and district_id != current_district:
            base_color = tuple(int(c * 0.45) for c in base_color)
        
        faction = faction_control.get(district_id)
        if faction:
            faction_colors = {
                "Crimson": (180, 40, 40),
                "Phantom": (100, 70, 140),
                "Syndicate": (40, 100, 70),
                "Vanguard": (40, 70, 140)
            }
            overlay_color = faction_colors.get(faction, (80, 80, 100))
            fill_color = tuple(
                int((base_color[i] * 0.6 + overlay_color[i] * 0.4))
                for i in range(3)
            )
        else:
            fill_color = base_color
        
        if district_id == current_district:
            outline_color = CURRENT_GLOW
            outline_width = 5
        elif district_id == active_event_district:
            outline_color = EVENT_GLOW
            outline_width = 5
        else:
            outline_color = (80, 85, 100)
            outline_width = 2
        
        draw.polygon(polygon, fill=fill_color + (220,))
        draw.polygon(polygon, outline=outline_color, width=outline_width)
        
        if faction:
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            bx = max(xs) - 90
            by = max(ys) - 35
            
            draw.rounded_rectangle(
                [bx - 3, by - 3, bx + 85, by + 22],
                radius=6,
                fill=(0, 0, 0, 200)
            )
            
            font = self._get_font(12, bold=True)
            draw.text(
                (bx, by),
                f"⚔️ {faction}",
                font=font,
                fill=FACTION_GLOW
            )
        
        label_x, label_y = info["label_pos"]
        
        font_large = self._get_font(16, bold=True)
        font_small = self._get_font(11, bold=False)
        font_tiny = self._get_font(9, bold=False)
        
        draw.text(
            (label_x, label_y),
            f"{info['emoji']} {info['name']}",
            font=font_large,
            fill=info["text_color"]
        )
        
        draw.text(
            (label_x, label_y + 22),
            f"Requires: {info['entry_requirement']}",
            font=font_tiny,
            fill=tuple(int(c * 0.7) for c in info["text_color"])
        )
        
        draw.text(
            (label_x, label_y + 36),
            f"Bonus: {info['bonus']}",
            font=font_tiny,
            fill=tuple(int(c * 0.7) for c in info["text_color"])
        )
    
    def _draw_player_marker(
        self,
        draw: ImageDraw.ImageDraw,
        district_id: int,
        current_district: Optional[int],
        player_name: str
    ) -> None:
        if district_id != current_district:
            return
        
        info = DISTRICTS.get(district_id)
        if not info:
            return
        
        polygon = info["polygon"]
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        
        cx = sum(xs) // len(xs)
        cy = sum(ys) // len(ys)
        
        draw.ellipse(
            [cx - 14, cy - 14, cx + 14, cy + 14],
            fill=(0, 0, 0, 180),
            outline=CURRENT_GLOW,
            width=3
        )
        
        draw.ellipse(
            [cx - 6, cy - 6, cx + 6, cy + 6],
            fill=CURRENT_GLOW,
            outline=(0, 0, 0)
        )
        
        font = self._get_font(11, bold=False)
        
        name_display = player_name[:14] if player_name else "You"
        name_width = font.getlength(name_display)
        
        draw.rounded_rectangle(
            [cx - name_width // 2 - 5, cy + 12, cx + name_width // 2 + 5, cy + 28],
            radius=8,
            fill=(0, 0, 0, 200)
        )
        
        draw.text(
            (cx - name_width // 2, cy + 14),
            name_display,
            font=font,
            fill=CURRENT_GLOW
        )
    
    def _draw_legend(self, draw: ImageDraw.ImageDraw) -> None:
        legend_x = CANVAS_W - 180
        legend_y = CANVAS_H - 110
        
        draw.rounded_rectangle(
            [legend_x - 10, legend_y - 10, legend_x + 170, legend_y + 100],
            radius=8,
            fill=(0, 0, 0, 180),
            outline=(80, 85, 100),
            width=1
        )
        
        font = self._get_font(12, bold=True)
        draw.text((legend_x, legend_y), "Legend", font=font, fill=(220, 220, 220))
        
        font_small = self._get_font(10, bold=False)
        
        y_offset = legend_y + 22
        draw.rectangle([legend_x, y_offset, legend_x + 12, y_offset + 12], fill=CURRENT_GLOW)
        draw.text((legend_x + 18, y_offset - 1), "Your Location", font=font_small, fill=(180, 180, 200))
        
        y_offset += 22
        draw.rectangle([legend_x, y_offset, legend_x + 12, y_offset + 12], fill=EVENT_GLOW)
        draw.text((legend_x + 18, y_offset - 1), "Active Event", font=font_small, fill=(180, 180, 200))
        
        y_offset += 22
        draw.rectangle([legend_x, y_offset, legend_x + 12, y_offset + 12], fill=FACTION_GLOW)
        draw.text((legend_x + 18, y_offset - 1), "Faction Control", font=font_small, fill=(180, 180, 200))
    
    def _draw_compass(self, draw: ImageDraw.ImageDraw) -> None:
        compass_x = CANVAS_W - 70
        compass_y = 40
        
        draw.ellipse(
            [compass_x - 18, compass_y - 18, compass_x + 18, compass_y + 18],
            fill=(0, 0, 0, 150),
            outline=(100, 110, 130),
            width=1
        )
        
        font = self._get_font(12, bold=True)
        draw.text((compass_x - 5, compass_y - 8), "N", font=font, fill=(255, 100, 100))
        draw.text((compass_x - 5, compass_y + 4), "S", font=font, fill=(100, 100, 255))
        draw.text((compass_x - 18, compass_y - 2), "W", font=font, fill=(150, 150, 150))
        draw.text((compass_x + 12, compass_y - 2), "E", font=font, fill=(150, 150, 150))
    
    def _draw_title(self, draw: ImageDraw.ImageDraw) -> None:
        font = self._get_font(24, bold=True)
        
        draw.text(
            (25, 25),
            "🏙️  SIMORA CITY",
            font=font,
            fill=(200, 210, 230)
        )
        
        font_small = self._get_font(10, bold=False)
        draw.text(
            (25, 55),
            "District Control Map",
            font=font_small,
            fill=(120, 130, 160)
        )
    
    def _render_map(
        self,
        current_district: Optional[int] = None,
        faction_control: Optional[Dict[int, str]] = None,
        active_event_district: Optional[int] = None,
        player_name: str = ""
    ) -> bytes:
        img = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_COLOR + (255,))
        draw = ImageDraw.Draw(img, "RGBA")
        
        faction_control = faction_control or {}
        
        self._draw_background_grid(draw)
        
        for district_id, info in DISTRICTS.items():
            self._draw_district(
                draw,
                district_id,
                info,
                current_district,
                active_event_district,
                faction_control
            )
        
        if current_district:
            self._draw_player_marker(draw, current_district, current_district, player_name)
        
        self._draw_legend(draw)
        self._draw_compass(draw)
        self._draw_title(draw)
        
        font_tiny = self._get_font(8, bold=False)
        draw.text(
            (CANVAS_W - 150, CANVAS_H - 20),
            "simora.city | v3",
            font=font_tiny,
            fill=(80, 90, 110)
        )
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        
        return buf.read()
    
    async def render(
        self,
        current_district: Optional[int] = None,
        faction_control: Optional[Dict[int, str]] = None,
        active_event_district: Optional[int] = None,
        player_name: str = "",
        force_refresh: bool = False
    ) -> discord.File:
        cache_key = None
        cached_data = None
        
        if self.cache and not force_refresh:
            cache_key = self.cache.generate_key(
                "map",
                current_district or 0,
                hash(frozenset(faction_control.items())) if faction_control else 0,
                active_event_district or 0,
                player_name[:20]
            )
            cached_data = await self.cache.get(cache_key)
            
            if cached_data:
                self.logger.debug("Map served from cache")
                return discord.File(
                    io.BytesIO(cached_data),
                    filename="simora_map.png"
                )
        
        try:
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                _executor,
                self._render_map,
                current_district,
                faction_control,
                active_event_district,
                player_name
            )
        except Exception as e:
            self.logger.error(f"Map generation failed: {e}")
            raise
        
        if self.cache and cache_key:
            await self.cache.set(cache_key, png_bytes, ttl=GameConstants.IMAGE_CACHE_TTL_HOURS * 3600)
        
        return discord.File(
            io.BytesIO(png_bytes),
            filename="simora_map.png"
        )
    
    async def render_district_preview(
        self,
        district_id: int,
        player_rep: int = 0
    ) -> discord.File:
        info = DISTRICTS.get(district_id)
        
        if not info:
            raise ValueError(f"Invalid district: {district_id}")
        
        faction_control = {}
        
        return await self.render(
            current_district=district_id,
            faction_control=faction_control,
            player_name=f"{info['name']} Preview"
        )


map_generator = MapGenerator()