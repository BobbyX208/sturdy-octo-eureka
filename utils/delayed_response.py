import asyncio
import random
from typing import Optional, Callable, Any, Tuple, Dict, List
from datetime import datetime
import discord
from discord import Interaction, Embed

class DelayedResponse:
    """Utility for cinematic delayed responses with AI-generated tension building"""
    
    def __init__(self, interaction: Interaction, ai_service, min_delay: float = 2.0, max_delay: float = 4.0):
        self.interaction = interaction
        self.ai_service = ai_service
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._tension_message: Optional[discord.Message] = None
        self._start_time: Optional[datetime] = None
        self._npc_id: Optional[str] = None
        self._player_data: Optional[Dict[str, Any]] = None
        self._context: Optional[str] = None
    
    async def send_tension(
        self, 
        npc_id: str, 
        player_data: Dict[str, Any], 
        context: str,
        ephemeral: bool = False
    ) -> None:
        """Send AI-generated tension-building message"""
        if not self.interaction.response.is_done():
            await self.interaction.response.defer(ephemeral=ephemeral)
        
        self._start_time = datetime.now()
        self._npc_id = npc_id
        self._player_data = player_data
        self._context = context
        
        tension_line = await self.ai_service.generate_npc_line(
            npc_id,
            player_data,
            f"Tension building moment. {context}. Speak mysteriously, build suspense. 1 sentence."
        )
        
        embed = discord.Embed(
            description=f"*{tension_line}*",
            color=0x2b2d31
        )
        embed.set_footer(text="Simora City")
        
        if self.interaction.response.is_done():
            self._tension_message = await self.interaction.followup.send(
                embed=embed,
                wait=True,
                ephemeral=ephemeral
            )
        else:
            await self.interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            self._tension_message = await self.interaction.original_response()
    
    async def send_tension_custom(self, embed: Embed, ephemeral: bool = False) -> None:
        """Send custom tension embed without AI"""
        if not self.interaction.response.is_done():
            await self.interaction.response.defer(ephemeral=ephemeral)
        
        self._start_time = datetime.now()
        
        if self.interaction.response.is_done():
            self._tension_message = await self.interaction.followup.send(
                embed=embed,
                wait=True,
                ephemeral=ephemeral
            )
        else:
            await self.interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            self._tension_message = await self.interaction.original_response()
    
    async def resolve(
        self, 
        result_embed: Embed, 
        logic_coro: Optional[Callable] = None,
        *args, 
        **kwargs
    ) -> Tuple[Any, float]:
        """Run logic while maintaining minimum delay"""
        if self._start_time is None:
            raise RuntimeError("Must call send_tension before resolve")
        
        elapsed = (datetime.now() - self._start_time).total_seconds()
        remaining_delay = max(0, self.min_delay - elapsed)
        
        if logic_coro:
            result = await asyncio.gather(
                logic_coro(*args, **kwargs),
                asyncio.sleep(remaining_delay)
            )
            actual_result = result[0]
        else:
            await asyncio.sleep(remaining_delay)
            actual_result = None
        
        await self._tension_message.edit(embed=result_embed)
        
        final_elapsed = (datetime.now() - self._start_time).total_seconds()
        return actual_result, final_elapsed
    
    async def resolve_with_range(
        self,
        result_embed: Embed,
        logic_coro: Optional[Callable] = None,
        *args,
        **kwargs
    ) -> Tuple[Any, float]:
        """Resolve with random delay between min and max"""
        if self._start_time is None:
            raise RuntimeError("Must call send_tension before resolve_with_range")
        
        elapsed = (datetime.now() - self._start_time).total_seconds()
        target_delay = self.min_delay + random.random() * (self.max_delay - self.min_delay)
        remaining_delay = max(0, target_delay - elapsed)
        
        if logic_coro:
            result = await asyncio.gather(
                logic_coro(*args, **kwargs),
                asyncio.sleep(remaining_delay)
            )
            actual_result = result[0]
        else:
            await asyncio.sleep(remaining_delay)
            actual_result = None
        
        await self._tension_message.edit(embed=result_embed)
        
        final_elapsed = (datetime.now() - self._start_time).total_seconds()
        return actual_result, final_elapsed

class CinematicSequence:
    """Multi-step cinematic sequence for prestige and major events"""
    
    def __init__(self, interaction: Interaction, ai_service, steps: List[Dict[str, Any]] = None):
        self.interaction = interaction
        self.ai_service = ai_service
        self.steps = steps or []
        self._current_step = 0
        self._message: Optional[discord.Message] = None
        self._player_data: Optional[Dict[str, Any]] = None
    
    async def start(self, npc_id: str, player_data: Dict[str, Any], context: str, ephemeral: bool = False) -> None:
        """Begin the cinematic sequence with AI-generated first step"""
        self._player_data = player_data
        
        if not self.interaction.response.is_done():
            await self.interaction.response.defer(ephemeral=ephemeral)
        
        first_line = await self.ai_service.generate_npc_line(
            npc_id,
            player_data,
            f"Cinematic moment. {context}. Speak with weight and gravity. 1 sentence."
        )
        
        first_embed = discord.Embed(
            description=f"*{first_line}*",
            color=0x2b2d31
        )
        first_embed.set_footer(text="Simora City")
        
        if self.interaction.response.is_done():
            self._message = await self.interaction.followup.send(
                embed=first_embed,
                wait=True,
                ephemeral=ephemeral
            )
        else:
            await self.interaction.response.send_message(embed=first_embed, ephemeral=ephemeral)
            self._message = await self.interaction.original_response()
        
        self._current_step = 1
        
        if self.steps:
            await self._process_step(0)
    
    async def _process_step(self, step_index: int) -> None:
        """Process a single step of the sequence"""
        if step_index >= len(self.steps):
            return
        
        step = self.steps[step_index]
        await asyncio.sleep(step.get("delay", 2.0))
        
        if step.get("ai_npc"):
            line = await self.ai_service.generate_npc_line(
                step["ai_npc"],
                self._player_data,
                step.get("ai_context", "Cinematic continuation.")
            )
            step["embed"].description = f"*{line}*"
        
        await self._message.edit(embed=step["embed"])
        self._current_step = step_index + 1
        
        if step.get("followup"):
            followup_embed = step.get("followup_embed")
            if followup_embed:
                await self.interaction.followup.send(embed=followup_embed, ephemeral=False)
        
        if step.get("callback"):
            await step["callback"](self.interaction)
        
        if self._current_step < len(self.steps):
            await self._process_step(self._current_step)
    
    async def add_step(self, embed: Embed, delay: float = 2.0, followup: bool = False, ai_npc: str = None, ai_context: str = None) -> None:
        """Dynamically add a step during sequence"""
        self.steps.append({
            "embed": embed,
            "delay": delay,
            "followup": followup,
            "ai_npc": ai_npc,
            "ai_context": ai_context
        })

class NPCDelayedResponse:
    """Handle NPC responses that arrive after main outcome"""
    
    def __init__(self, interaction: Interaction, ai_service):
        self.interaction = interaction
        self.ai_service = ai_service
        self._sent_lines = []
    
    async def send_line(
        self, 
        npc_id: str, 
        player_data: Dict[str, Any], 
        context: str, 
        delay: float = 1.5,
        ephemeral: bool = False
    ) -> None:
        """Generate and send AI NPC line after delay"""
        await asyncio.sleep(delay)
        
        line = await self.ai_service.generate_npc_line(
            npc_id,
            player_data,
            context
        )
        
        embed = discord.Embed(
            description=f"*{line}*",
            color=0x2b2d31
        )
        embed.set_footer(text=f"— {npc_id.title()}")
        
        message = await self.interaction.followup.send(
            embed=embed,
            ephemeral=ephemeral
        )
        
        self._sent_lines.append({
            "npc_id": npc_id,
            "embed": embed,
            "message": message,
            "timestamp": datetime.now()
        })
    
    async def send_multiple(
        self, 
        lines: List[Tuple[str, Dict[str, Any], str]], 
        delays: List[float] = None,
        ephemeral: bool = False
    ) -> None:
        """Send multiple AI NPC lines with individual delays"""
        if delays is None:
            delays = [1.5] * len(lines)
        
        for i, (npc_id, player_data, context) in enumerate(lines):
            await asyncio.sleep(delays[i])
            
            line = await self.ai_service.generate_npc_line(
                npc_id,
                player_data,
                context
            )
            
            embed = discord.Embed(
                description=f"*{line}*",
                color=0x2b2d31
            )
            embed.set_footer(text=f"— {npc_id.title()}")
            
            message = await self.interaction.followup.send(
                embed=embed,
                ephemeral=ephemeral
            )
            
            self._sent_lines.append({
                "npc_id": npc_id,
                "embed": embed,
                "message": message,
                "timestamp": datetime.now()
            })
    
    async def replace_last(self, npc_id: str, player_data: Dict[str, Any], context: str) -> None:
        """Replace the last sent NPC message with a new AI-generated one"""
        if self._sent_lines:
            new_line = await self.ai_service.generate_npc_line(
                npc_id,
                player_data,
                context
            )
            
            embed = discord.Embed(
                description=f"*{new_line}*",
                color=0x2b2d31
            )
            embed.set_footer(text=f"— {npc_id.title()}")
            
            await self._sent_lines[-1]["message"].edit(embed=embed)
            self._sent_lines[-1]["embed"] = embed
            self._sent_lines[-1]["npc_id"] = npc_id

class TensionBuilder:
    """Build AI-generated tension messages for different command types"""
    
    def __init__(self, ai_service):
        self.ai_service = ai_service
        self._tension_cache = {}
    
    async def get_tension(
        self, 
        npc_id: str, 
        player_data: Dict[str, Any], 
        command_type: str,
        context: str
    ) -> str:
        """Generate AI tension message"""
        cache_key = f"tension:{npc_id}:{command_type}:{player_data.get('discord_id')}"
        
        if cache_key in self._tension_cache:
            return self._tension_cache[cache_key]
        
        tension_prompt = f"Tension building moment for {command_type}. {context}. Speak mysteriously, build suspense, be in character. 1 sentence only."
        
        tension_line = await self.ai_service.generate_npc_line(
            npc_id,
            player_data,
            tension_prompt
        )
        
        if len(self._tension_cache) > 100:
            self._tension_cache.clear()
        
        self._tension_cache[cache_key] = tension_line
        
        return tension_line
    
    async def get_tension_embed(
        self, 
        npc_id: str, 
        player_data: Dict[str, Any], 
        command_type: str,
        context: str
    ) -> Embed:
        """Generate and return tension embed"""
        line = await self.get_tension(npc_id, player_data, command_type, context)
        
        embed = discord.Embed(
            description=f"*{line}*",
            color=0x2b2d31
        )
        embed.set_footer(text="Simora City")
        
        return embed