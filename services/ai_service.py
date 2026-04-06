import logging
import json
import asyncio
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import random

import aiohttp
from groq import AsyncGroq
import google.generativeai as genai

from core.cache import CacheManager
from config.settings import Config


class AIService:
    
    def __init__(self, groq_key: str, gemini_key: str, cache_manager: CacheManager):
        self.groq_key = groq_key
        self.gemini_key = gemini_key
        self.cache = cache_manager
        self.logger = logging.getLogger("simcoin.services.ai")
        
        # Initialize Groq
        if groq_key:
            try:
                import httpx
                http_client = httpx.AsyncClient(timeout=30.0)
                self.groq_client = AsyncGroq(api_key=groq_key, http_client=http_client)
            except Exception as e:
                self.logger.warning(f"Groq init with custom client failed: {e}")
                self.groq_client = AsyncGroq(api_key=groq_key) if groq_key else None
        else:
            self.groq_client = None
        
        # Initialize Gemini
        self.gemini_client = None
        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_client = genai.GenerativeModel('gemini-1.5-flash')
            except Exception as e:
                self.logger.error(f"Gemini init failed: {e}")
        
        self._rate_limit_counter = 0
        self._rate_limit_reset = datetime.now(timezone.utc)
        
        self.npc_profiles = self._load_npc_profiles()
    
    def _load_npc_profiles(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(f"{Config.DATA_DIR}/npcs.json", "r") as f:
                data = json.load(f)
                return {npc["id"]: npc for npc in data.get("npcs", [])}
        except Exception as e:
            self.logger.error(f"Failed to load NPC profiles: {e}")
            return {}
    
    def _get_fallback_response(self, npc_id: str, context: str = "") -> str:
        npc = self.npc_profiles.get(npc_id, {})
        fallback_bank = npc.get("fallback_bank", [])
        
        if fallback_bank:
            return random.choice(fallback_bank)
        
        return "The city speaks, but words fade before they reach you."
    
    def _build_npc_prompt(self, npc_id: str, player_data: Dict[str, Any], context: str, memory: List[Dict[str, Any]]) -> str:
        npc = self.npc_profiles.get(npc_id, {})
        
        personality = npc.get("personality", "neutral")
        voice = npc.get("voice", "Speak naturally.")
        never_says = npc.get('never_says', 'Nothing')
        
        prompt = f"""You are {npc.get('name', npc_id)}, an NPC in Simora City.
Personality: {personality}
Voice: {voice}
Never say: {never_says}

Player Info:
- Name: {player_data.get('username', 'Unknown')}
- Reputation: {player_data.get('reputation', 0)} (Rank {player_data.get('rep_rank', 1)})
- District: {player_data.get('district', 1)}
- Premium Tier: {player_data.get('premium_tier', 'citizen')}

Recent Interactions:
"""
        
        for mem in memory[:5]:
            prompt += f"- {mem.get('context_summary', '')} -> You said: {mem.get('ai_response', '')}\n"
        
        prompt += f"\nCurrent Situation: {context}\n\nRespond in character. Keep response to 1-2 sentences. Be concise and immersive."
        
        return prompt
    
    async def _call_groq(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7) -> Optional[str]:
        if not self.groq_client:
            return None
        
        try:
            response = await asyncio.wait_for(
                self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature
                ),
                timeout=Config.AI_TIMEOUT_SECONDS
            )
            
            return response.choices[0].message.content.strip()
            
        except asyncio.TimeoutError:
            self.logger.warning("Groq request timed out")
            return None
        except Exception as e:
            self.logger.error(f"Groq request failed: {e}")
            return None
    
    async def _call_gemini(self, prompt: str, max_tokens: int = 100) -> Optional[str]:
        if not self.gemini_client:
            return None
        
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.gemini_client.generate_content,
                    prompt,
                    generation_config={"max_output_tokens": max_tokens}
                ),
                timeout=Config.AI_TIMEOUT_SECONDS
            )
            
            return response.text.strip()
            
        except asyncio.TimeoutError:
            self.logger.warning("Gemini request timed out")
            return None
        except Exception as e:
            self.logger.error(f"Gemini request failed: {e}")
            return None
    
    async def generate_npc_line(
        self,
        npc_id: str,
        player_data: Dict[str, Any],
        context: str,
        memory: List[Dict[str, Any]] = None
    ) -> str:
        try:
            # CACHE COMPLETELY DISABLED - Every call is fresh
            
            memory = memory or []
            
            prompt = self._build_npc_prompt(npc_id, player_data, context, memory)
            
            # Add random temperature for variety (0.5 to 1.0)
            temperature = random.uniform(0.5, 1.0)
            
            # Add random seed to prompt for more variety
            random_seed = random.randint(1, 100)
            prompt = f"[Seed: {random_seed}]\n{prompt}"
            
            response = await self._call_groq(prompt, temperature=temperature)
            
            if not response:
                response = await self._call_gemini(prompt)
            
            if not response:
                response = self._get_fallback_response(npc_id, context)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Generate NPC line failed: {e}")
            return self._get_fallback_response(npc_id, context)
    
    async def generate_market_headlines(self) -> List[Dict[str, Any]]:
        try:
            # CACHE DISABLED - Always fresh
            
            prompt = """Generate 3 fictional market headlines for a cyberpunk city economy.
Each headline should have:
- headline: short catchy title
- sector: one of [retail, manufacturing, entertainment, black_market, finance, technology, real_estate, transport]
- modifier: a number between 0.9 and 1.1
- direction: one of [positive, negative, neutral]

Return as JSON array.

Example: [{"headline": "Tech Core Surges on AI Breakthrough", "sector": "technology", "modifier": 1.08, "direction": "positive"}]
"""
            
            response = await self._call_groq(prompt, max_tokens=300, temperature=0.8)
            
            if not response:
                response = await self._call_gemini(prompt, max_tokens=300)
            
            if response:
                try:
                    # Clean response - remove markdown code blocks if present
                    response = response.strip()
                    if response.startswith("```json"):
                        response = response[7:]
                    if response.startswith("```"):
                        response = response[3:]
                    if response.endswith("```"):
                        response = response[:-3]
                    
                    headlines = json.loads(response.strip())
                    
                    if isinstance(headlines, list):
                        return headlines
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse market headlines: {e}\nResponse: {response}")
            
            return self._get_fallback_headlines()
            
        except Exception as e:
            self.logger.error(f"Generate market headlines failed: {e}")
            return self._get_fallback_headlines()
    
    def _get_fallback_headlines(self) -> List[Dict[str, Any]]:
        return [
            {"headline": "Markets Steady as City Watches", "sector": "finance", "modifier": 1.0, "direction": "neutral"},
            {"headline": "Underground Trades Surge", "sector": "black_market", "modifier": 1.05, "direction": "positive"},
            {"headline": "Industrial Output Slows", "sector": "manufacturing", "modifier": 0.97, "direction": "negative"}
        ]
    
    async def generate_event_description(self, event_type: str) -> str:
        try:
            prompt = f"""Describe a {event_type} event happening in Simora City, a cyberpunk city.
Make it immersive, 1-2 sentences."""
            
            response = await self._call_groq(prompt, max_tokens=50, temperature=0.8)
            
            if not response:
                response = await self._call_gemini(prompt, max_tokens=50)
            
            if response:
                return response
            
            fallbacks = {
                "market_boom": "The markets surge as investors pour in!",
                "crime_wave": "Shadows grow longer. The underground stirs.",
                "festival": "Neon lights paint the streets. The city celebrates!",
                "power_outage": "Darkness falls across the district."
            }
            
            return fallbacks.get(event_type, "Something stirs in Simora City.")
            
        except Exception as e:
            self.logger.error(f"Generate event description failed: {e}")
            return "Something stirs in Simora City."
    
    async def generate_gazette_summary(self, data: Dict[str, Any]) -> str:
        try:
            prompt = f"""Write a 2-3 sentence newspaper summary for Simora City's weekly gazette.
Data: {json.dumps(data, default=str)}
Make it immersive and exciting."""
            
            response = await self._call_groq(prompt, max_tokens=150, temperature=0.7)
            
            if not response:
                response = await self._call_gemini(prompt, max_tokens=150)
            
            if response:
                return response
            
            return "Another week passes in Simora City. The streets remember."
            
        except Exception as e:
            self.logger.error(f"Generate gazette summary failed: {e}")
            return "The Weekly Gazette: Another week in Simora City."
    
    async def generate_analyst_report(self, player_data: Dict[str, Any], portfolio: List[Dict[str, Any]], market_data: Dict[str, Any]) -> str:
        try:
            prompt = f"""You are The Analyst, a cold, precise AI investment advisor.
Your personality: Cold. Precise. Numbers only. Never show emotion.
Response format: 3 bullet points, max 80 words total.

Player Data:
- Net Worth: {player_data.get('wallet', 0) + player_data.get('bank', 0)} SC
- Reputation: {player_data.get('reputation', 0)}
- Premium Tier: {player_data.get('premium_tier', 'citizen')}

Portfolio:
{json.dumps(portfolio[:5], default=str)}

Market Data:
{json.dumps(market_data, default=str)}

Provide investment advice. Be concise."""
            
            response = await self._call_groq(prompt, max_tokens=150, temperature=0.5)
            
            if not response:
                response = await self._call_gemini(prompt, max_tokens=150)
            
            if response:
                return response
            
            return "• Markets fluctuate. • Diversify holdings. • Monitor sentiment indicators."
            
        except Exception as e:
            self.logger.error(f"Generate analyst report failed: {e}")
            return "• Data insufficient for analysis. • Recalibrating. • Await further market movement."
    
    async def generate_billboard_ad(self, brief: str, player_name: str) -> str:
        try:
            prompt = f"""Create a short, immersive billboard ad for Simora City based on:
Brief: {brief}
Player: {player_name}
Make it cyberpunk style, 1-2 sentences. Max 100 characters."""
            
            response = await self._call_groq(prompt, max_tokens=60, temperature=0.9)
            
            if not response:
                response = await self._call_gemini(prompt, max_tokens=60)
            
            if response and len(response) <= 200:
                return response
            
            return f"{player_name} says: {brief[:80]}"
            
        except Exception as e:
            self.logger.error(f"Generate billboard ad failed: {e}")
            return f"{player_name}: {brief[:80]}"
    
    async def moderate_content(self, content: str) -> Tuple[bool, str]:
        try:
            prompt = f"""Analyze this content for inappropriate material (hate speech, harassment, explicit content):
Content: {content}
Return JSON: {{"approved": true/false, "reason": "if not approved"}}"""
            
            response = await self._call_groq(prompt, max_tokens=80, temperature=0.2)
            
            if not response:
                response = await self._call_gemini(prompt, max_tokens=80)
            
            if response:
                try:
                    # Clean response
                    response = response.strip()
                    if response.startswith("```json"):
                        response = response[7:]
                    if response.startswith("```"):
                        response = response[3:]
                    if response.endswith("```"):
                        response = response[:-3]
                    
                    result = json.loads(response.strip())
                    return result.get("approved", True), result.get("reason", "")
                except json.JSONDecodeError:
                    pass
            
            return True, ""
            
        except Exception as e:
            self.logger.error(f"Moderate content failed: {e}")
            return True, ""
    
    async def close(self) -> None:
        self.logger.info("AI Service closed")