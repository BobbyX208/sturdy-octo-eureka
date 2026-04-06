import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
import asyncio
from typing import Optional, List, Dict, Any
import random

from utils.checks import requires_profile, not_jailed, requires_premium
from utils.embeds import EmbedBuilder
from utils.formatters import format_sc, format_time, progress_bar, ordinal
from utils.delayed_response import DelayedResponse, NPCDelayedResponse, CinematicSequence
from utils.luck import Luck


class WorkCog(commands.Cog):
    """Work commands - jobs, apply, work, collect, myjobs, quit"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.cogs.work")
        self.luck = Luck()
        
        self.outcome_tiers = {
            "grinded": {"name": "Grinded", "min_mult": 0.5, "max_mult": 0.8, "color": 0x95a5a6},
            "solid": {"name": "Solid Shift", "min_mult": 0.9, "max_mult": 1.1, "color": 0x3498db},
            "exceptional": {"name": "Exceptional", "min_mult": 1.2, "max_mult": 1.5, "color": 0x9b59b6},
            "legendary": {"name": "Legendary Run", "min_mult": 1.6, "max_mult": 2.0, "color": 0xf1c40f}
        }
        
        self.random_events = [
            {"name": "💰 Found a bonus!", "effect": "bonus", "min_mult": 1.1, "max_mult": 1.3},
            {"name": "⚠️ Equipment malfunction", "effect": "penalty", "min_mult": 0.7, "max_mult": 0.9},
            {"name": "🎁 Client gave a tip!", "effect": "bonus", "min_mult": 1.2, "max_mult": 1.4},
            {"name": "📦 Found a package", "effect": "item", "item": "mystery_box"},
            {"name": "👥 Helped a colleague", "effect": "reputation", "rep_gain": 5},
            {"name": "💼 Got promoted temporarily", "effect": "bonus", "min_mult": 1.3, "max_mult": 1.5}
        ]

    @app_commands.command(name="jobs", description="Browse available jobs in your district")
    @app_commands.describe(
        district="Optional: View jobs in specific district",
        ephemeral="Hide the response from others (default: False)"
    )
    @app_commands.choices(district=[
        app_commands.Choice(name="🏚️ Slums", value="1"),
        app_commands.Choice(name="🏢 Downtown", value="2"),
        app_commands.Choice(name="💹 Financial District", value="3"),
        app_commands.Choice(name="🌿 Underground", value="4"),
        app_commands.Choice(name="🏭 Industrial Zone", value="5"),
        app_commands.Choice(name="🎰 The Strip", value="6")
    ])
    @requires_profile()
    @not_jailed()
    async def jobs(self, interaction: discord.Interaction, district: Optional[str] = None, ephemeral: bool = False):
        """Browse jobs with competition data and hire chance"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        if district:
            target_district = int(district)
        else:
            target_district = player_data.get("district", 1)
        
        jobs_data = await self.bot.services.work.get_jobs_by_district(target_district)
        
        if not jobs_data:
            await interaction.followup.send(
                f"❌ No jobs available in {self._get_district_name(target_district)}.",
                ephemeral=ephemeral
            )
            return
        
        competition_data = await self.bot.services.work.get_job_competition(target_district)
        
        embed = discord.Embed(
            title=f"💼 Jobs in {self._get_district_name(target_district)}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        rep_rank = player_data.get("rep_rank", 1)
        wallet = player_data.get("wallet", 0)
        
        for job in jobs_data[:8]:
            job_id = job.get("id")
            job_name = job.get("name", "Unknown")
            base_pay = job.get("base_pay", 100)
            rep_required = job.get("rep_required", 1)
            sc_required = job.get("sc_required", 0)
            cooldown = job.get("cooldown_minutes", 30)
            
            is_locked = False
            lock_reason = None
            
            if rep_rank < rep_required:
                is_locked = True
                lock_reason = f"Rep Rank {rep_required} required"
            elif wallet < sc_required:
                is_locked = True
                lock_reason = f"{format_sc(sc_required)} required"
            
            players_today = competition_data.get(job_id, {}).get("players_today", 0)
            hire_chance = self._calculate_hire_chance(rep_rank, rep_required, players_today)
            
            chance_text = self._chance_to_text(hire_chance)
            
            status = ""
            if is_locked:
                status = f"🔒 **LOCKED** - {lock_reason}\n"
            
            embed.add_field(
                name=f"{'🔒 ' if is_locked else '✅ '}{job_name}",
                value=(
                    f"{status}"
                    f"💰 {format_sc(base_pay)}/work\n"
                    f"⏰ {cooldown} min cooldown\n"
                    f"👥 {players_today} players today\n"
                    f"🎲 Hire chance: {chance_text}"
                ),
                inline=True
            )
        
        embed.set_footer(text="Use /apply [job_id] to apply | Higher rep = better jobs")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="apply", description="Apply for a job")
    @app_commands.describe(
        job_id="Job ID from /jobs",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    async def apply(self, interaction: discord.Interaction, job_id: str, ephemeral: bool = False):
        """Apply for a job with NPC interview scene"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        job_data = await self.bot.services.work.get_job(job_id)
        
        if not job_data:
            await interaction.followup.send(
                f"❌ Job '{job_id}' not found. Use `/jobs` to see available jobs.",
                ephemeral=ephemeral
            )
            return
        
        rep_rank = player_data.get("rep_rank", 1)
        wallet = player_data.get("wallet", 0)
        rep_required = job_data.get("rep_required", 1)
        sc_required = job_data.get("sc_required", 0)
        
        if rep_rank < rep_required:
            await interaction.followup.send(
                f"❌ You need Reputation Rank {rep_required} to apply for {job_data.get('name')}.",
                ephemeral=ephemeral
            )
            return
        
        if wallet < sc_required:
            await interaction.followup.send(
                f"❌ You need {format_sc(sc_required)} to apply for {job_data.get('name')}.",
                ephemeral=ephemeral
            )
            return
        
        currently_employed = await self.bot.services.work.get_active_jobs_count(interaction.user.id)
        max_jobs = self._get_max_jobs(player_data.get("premium_tier", "citizen"))
        
        if currently_employed >= max_jobs:
            await interaction.followup.send(
                f"❌ You already have {currently_employed}/{max_jobs} jobs. Use `/quit` to leave one first.",
                ephemeral=ephemeral
            )
            return
        
        district = job_data.get("district", 1)
        npc_id = self._get_district_npc(district)
        job_name = job_data.get("name", "this position")
        
        interview_embed = discord.Embed(
            title="📋 Job Interview",
            description=f"You approach {self._get_npc_name(npc_id)} about the {job_name} position.",
            color=discord.Color.purple()
        )
        
        await interaction.followup.send(embed=interview_embed, ephemeral=ephemeral)
        
        await asyncio.sleep(1.5)
        
        question = await self.bot.services.ai.generate_npc_line(
            npc_id,
            {"username": interaction.user.name, "reputation": rep_rank, "rep_rank": rep_rank, "district": district, "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Interview question for {job_name} position. Ask one question to test if they're qualified."
        )
        
        question_embed = discord.Embed(
            title=f"💬 {self._get_npc_name(npc_id)} asks",
            description=f"*{question}*",
            color=discord.Color.blue()
        )
        
        await interaction.followup.send(embed=question_embed, ephemeral=ephemeral)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id
        
        try:
            response_msg = await self.bot.wait_for("message", timeout=60.0, check=check)
            user_response = response_msg.content
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "❌ Interview timed out. You didn't respond in time.",
                ephemeral=ephemeral
            )
            return
        
        await response_msg.delete()
        
        evaluation = await self.bot.services.ai.generate_npc_line(
            npc_id,
            {"username": interaction.user.name, "reputation": rep_rank, "rep_rank": rep_rank, "district": district, "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Interview response: '{user_response}'. Evaluate if they're hired. Respond with hiring decision (hired/rejected) and reason. Be in character."
        )
        
        if "hired" in evaluation.lower() or "welcome" in evaluation.lower() or "start" in evaluation.lower():
            await self.bot.services.work.hire_player(interaction.user.id, job_id)
            
            success_embed = discord.Embed(
                title="✅ You're Hired!",
                description=f"*{evaluation}*",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=success_embed, ephemeral=ephemeral)
            
            await self.bot.event_bus.fire("player.hired", {
                "discord_id": interaction.user.id,
                "username": interaction.user.name,
                "job_id": job_id,
                "job_name": job_name
            })
        else:
            reject_embed = discord.Embed(
                title="❌ Application Rejected",
                description=f"*{evaluation}*",
                color=discord.Color.red()
            )
            
            await interaction.followup.send(embed=reject_embed, ephemeral=ephemeral)

    @app_commands.command(name="work", description="Work your job")
    @app_commands.describe(
        job_id="Job ID to work",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    async def work(self, interaction: discord.Interaction, job_id: str, ephemeral: bool = False):
        """Work a job with outcome tiers and random events"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        job_contract = await self.bot.services.work.get_active_job(interaction.user.id, job_id)
        
        if not job_contract:
            await interaction.followup.send(
                f"❌ You're not employed at '{job_id}'. Use `/jobs` to find work.",
                ephemeral=ephemeral
            )
            return
        
        job_data = await self.bot.services.work.get_job(job_id)
        
        cooldown_remaining = await self.bot.services.player.check_cooldown(
            interaction.user.id, f"work_{job_id}"
        )
        
        if cooldown_remaining > 0:
            await interaction.followup.send(
                f"⏰ You're still recovering from your last shift. Try again in {format_time(cooldown_remaining)}.",
                ephemeral=ephemeral
            )
            return
        
        daily_count = job_contract.get("daily_work_count", 0)
        if daily_count >= job_data.get("daily_limit", 5):
            await interaction.followup.send(
                f"❌ You've reached your daily limit for this job ({daily_count}/5 shifts).",
                ephemeral=ephemeral
            )
            return
        
        tension = DelayedResponse(interaction, self.bot.services.ai, min_delay=2.0, max_delay=3.0)
        
        district = job_data.get("district", 1)
        npc_id = self._get_district_npc(district)
        
        await tension.send_tension(
            npc_id,
            {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": district, "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Player is about to work at {job_data.get('name')}. Build tension for the shift.",
            ephemeral=ephemeral
        )
        
        outcome = self._calculate_outcome(player_data, job_data)
        
        random_event = None
        if self.luck.roll(15):
            random_event = random.choice(self.random_events)
        
        base_pay = job_data.get("base_pay", 100)
        tier_mult = outcome["multiplier"]
        
        event_mult = 1.0
        event_effect_text = ""
        
        if random_event:
            if random_event["effect"] == "bonus":
                event_mult = random.uniform(random_event["min_mult"], random_event["max_mult"])
                event_effect_text = f"\n✨ {random_event['name']} (+{int((event_mult-1)*100)}%)"
            elif random_event["effect"] == "penalty":
                event_mult = random.uniform(random_event["min_mult"], random_event["max_mult"])
                event_effect_text = f"\n⚠️ {random_event['name']} ({int((1-event_mult)*100)}% reduction)"
        
        premium_mult = self._get_premium_multiplier(player_data.get("premium_tier", "citizen"))
        
        total_earned = int(base_pay * tier_mult * event_mult * premium_mult)
        
        await self.bot.services.player.update_balance(interaction.user.id, wallet_delta=total_earned)
        
        await self.bot.services.work.record_work(interaction.user.id, job_id, total_earned)
        
        await self.bot.services.player.set_cooldown(interaction.user.id, f"work_{job_id}", job_data.get("cooldown_minutes", 30) * 60)
        
        result_embed = discord.Embed(
            title=f"💼 {outcome['name']} at {job_data.get('name', 'Work')}",
            color=outcome["color"],
            timestamp=datetime.now(timezone.utc)
        )
        
        result_embed.add_field(
            name="💰 Earnings",
            value=(
                f"Base: {format_sc(base_pay)}\n"
                f"Performance: {tier_mult}x\n"
                f"{f'Event: {event_mult}x' if random_event else ''}\n"
                f"Premium: {premium_mult}x\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"**Total: +{format_sc(total_earned)}**"
            ),
            inline=False
        )
        
        await tension.resolve(result_embed)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
        
        reaction_context = f"Player worked at {job_data.get('name')} and earned {format_sc(total_earned)}. Outcome was {outcome['name']}."
        if random_event:
            reaction_context += f" Also {random_event['name']} happened."
        
        await npc_delayed.send_line(
            npc_id,
            {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": district, "premium_tier": player_data.get("premium_tier", "citizen")},
            reaction_context,
            delay=1.5,
            ephemeral=ephemeral
        )
        
        if random_event and random_event["effect"] == "item":
            await self.bot.services.inventory.add_item(interaction.user.id, random_event["item"], 1)
            item_embed = discord.Embed(
                description=f"📦 You received: **{random_event['item'].replace('_', ' ').title()}**",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=item_embed, ephemeral=ephemeral)
        
        if random_event and random_event["effect"] == "reputation":
            await self.bot.services.player.update_reputation(interaction.user.id, random_event["rep_gain"])
            rep_embed = discord.Embed(
                description=f"⭐ +{random_event['rep_gain']} Reputation!",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=rep_embed, ephemeral=ephemeral)
        
        await self.bot.event_bus.fire("player.worked", {
            "discord_id": interaction.user.id,
            "username": interaction.user.name,
            "job_id": job_id,
            "job_name": job_data.get("name"),
            "earned": total_earned,
            "outcome": outcome["name"]
        })

    @app_commands.command(name="collect", description="Collect passive income from all jobs")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def collect(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Collect pending passive income from all jobs"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        pending = await self.bot.services.work.get_pending_income(interaction.user.id)
        
        if not pending:
            await interaction.followup.send(
                "❌ You have no pending income to collect. Work your jobs to generate income!",
                ephemeral=ephemeral
            )
            return
        
        total_earned = 0
        breakdown = []
        
        for job in pending:
            job_name = job.get("name", "Unknown")
            amount = job.get("pending", 0)
            total_earned += amount
            breakdown.append(f"**{job_name}:** +{format_sc(amount)}")
        
        await self.bot.services.work.collect_pending(interaction.user.id)
        
        await self.bot.services.player.update_balance(interaction.user.id, wallet_delta=total_earned)
        
        embed = discord.Embed(
            title="💰 Passive Income Collected",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Breakdown",
            value="\n".join(breakdown[:10]),
            inline=False
        )
        
        embed.add_field(
            name="🏦 Total",
            value=f"+{format_sc(total_earned)}",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        await npc_delayed.send_line(
            "marco",
            {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": player_data.get("district", 1), "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Player collected {format_sc(total_earned)} from passive income. Acknowledge their hustle.",
            delay=1.5,
            ephemeral=ephemeral
        )

    @app_commands.command(name="myjobs", description="View your active jobs")
    @app_commands.describe(ephemeral="Hide the response from others (default: False)")
    @requires_profile()
    @not_jailed()
    async def myjobs(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Show active jobs with efficiency status and pending SC"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        active_jobs = await self.bot.services.work.get_active_jobs(interaction.user.id)
        
        if not active_jobs:
            await interaction.followup.send(
                "❌ You're not employed anywhere. Use `/jobs` to find work!",
                ephemeral=ephemeral
            )
            return
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        embed = discord.Embed(
            title="💼 Your Jobs",
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc)
        )
        
        for job in active_jobs:
            job_id = job.get("job_id")
            job_data = await self.bot.services.work.get_job(job_id)
            job_name = job_data.get("name", "Unknown") if job_data else job_id
            
            pending = job.get("pending_income", 0)
            efficiency = job.get("efficiency", 1.0)
            last_worked = job.get("last_worked")
            
            efficiency_bar = self._get_efficiency_bar(efficiency)
            
            last_worked_text = "Never"
            if last_worked:
                days_ago = (datetime.now(timezone.utc) - last_worked).days
                if days_ago == 0:
                    last_worked_text = "Today"
                elif days_ago == 1:
                    last_worked_text = "Yesterday"
                else:
                    last_worked_text = f"{days_ago} days ago"
            
            status = "🟢 Active"
            if efficiency < 0.5:
                status = "🔴 Neglected"
            elif efficiency < 0.8:
                status = "🟡 Declining"
            
            embed.add_field(
                name=f"{job_name}",
                value=(
                    f"**Status:** {status}\n"
                    f"**Efficiency:** {efficiency_bar} {int(efficiency*100)}%\n"
                    f"**Pending:** {format_sc(pending)}\n"
                    f"**Last worked:** {last_worked_text}"
                ),
                inline=False
            )
        
        max_jobs = self._get_max_jobs(player_data.get("premium_tier", "citizen"))
        embed.set_footer(text=f"{len(active_jobs)}/{max_jobs} jobs | Use /collect to claim pending income")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="quit", description="Quit your job")
    @app_commands.describe(
        job_id="Job ID to quit",
        ephemeral="Hide the response from others (default: False)"
    )
    @requires_profile()
    @not_jailed()
    async def quit(self, interaction: discord.Interaction, job_id: str, ephemeral: bool = False):
        """Leave a job with 7-day field cooldown and NPC farewell"""
        
        await interaction.response.defer(ephemeral=ephemeral)
        
        job_contract = await self.bot.services.work.get_active_job(interaction.user.id, job_id)
        
        if not job_contract:
            await interaction.followup.send(
                f"❌ You're not employed at '{job_id}'.",
                ephemeral=ephemeral
            )
            return
        
        job_data = await self.bot.services.work.get_job(job_id)
        job_name = job_data.get("name", job_id) if job_data else job_id
        
        pending = job_contract.get("pending_income", 0)
        
        if pending > 0:
            confirm_embed = discord.Embed(
                title="⚠️ Uncollected Income",
                description=f"You have {format_sc(pending)} pending from {job_name}. Collect it with `/collect` before quitting, or it will be lost.",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=confirm_embed, ephemeral=ephemeral)
            return
        
        player_data = await self.bot.services.player.get(interaction.user.id)
        
        await self.bot.services.work.quit_job(interaction.user.id, job_id)
        
        await self.bot.services.player.set_cooldown(interaction.user.id, f"field_{job_id}", 7 * 24 * 3600)
        
        district = job_data.get("district", 1) if job_data else 1
        npc_id = self._get_district_npc(district)
        
        embed = discord.Embed(
            title="❌ Job Quit",
            description=f"You have left **{job_name}**.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="⏰ Field Cooldown",
            value="You cannot work in this field for 7 days.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        
        npc_delayed = NPCDelayedResponse(interaction, self.bot.services.ai)
        
        await npc_delayed.send_line(
            npc_id,
            {"username": interaction.user.name, "reputation": player_data.get("reputation", 0), "rep_rank": player_data.get("rep_rank", 1), "district": district, "premium_tier": player_data.get("premium_tier", "citizen")},
            f"Player quit {job_name}. Say farewell, maybe hint they can return after 7 days.",
            delay=1.5,
            ephemeral=ephemeral
        )
        
        await self.bot.event_bus.fire("player.quit_job", {
            "discord_id": interaction.user.id,
            "username": interaction.user.name,
            "job_id": job_id,
            "job_name": job_name
        })

    def _calculate_outcome(self, player_data: Dict[str, Any], job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate work outcome tier based on rep, efficiency, and luck"""
        
        rep_rank = player_data.get("rep_rank", 1)
        efficiency = player_data.get("business_efficiency", 1.0)
        
        base_chance = random.random()
        
        rep_bonus = min(0.3, (rep_rank - 1) * 0.03)
        efficiency_bonus = min(0.2, (efficiency - 1) * 0.5)
        
        final_roll = base_chance + rep_bonus + efficiency_bonus
        
        if final_roll > 0.95:
            tier = "legendary"
        elif final_roll > 0.75:
            tier = "exceptional"
        elif final_roll > 0.35:
            tier = "solid"
        else:
            tier = "grinded"
        
        outcome = self.outcome_tiers[tier]
        
        mult = random.uniform(outcome["min_mult"], outcome["max_mult"])
        
        return {
            "name": outcome["name"],
            "multiplier": mult,
            "color": outcome["color"]
        }
    
    def _calculate_hire_chance(self, rep_rank: int, rep_required: int, players_today: int) -> float:
        """Calculate hire chance based on rep and competition"""
        
        rep_advantage = max(0, (rep_rank - rep_required) * 0.1)
        competition_penalty = min(0.3, players_today * 0.05)
        
        base_chance = 0.5
        final_chance = min(0.95, base_chance + rep_advantage - competition_penalty)
        
        return final_chance
    
    def _chance_to_text(self, chance: float) -> str:
        """Convert chance to descriptive text"""
        if chance >= 0.8:
            return "Very High"
        elif chance >= 0.6:
            return "High"
        elif chance >= 0.4:
            return "Moderate"
        elif chance >= 0.2:
            return "Low"
        else:
            return "Very Low"
    
    def _get_district_name(self, district_id: int) -> str:
        names = {
            1: "Slums",
            2: "Downtown",
            3: "Financial District",
            4: "Underground",
            5: "Industrial Zone",
            6: "The Strip"
        }
        return names.get(district_id, "Unknown")
    
    def _get_district_npc(self, district_id: int) -> str:
        npcs = {
            1: "ray",
            2: "chen",
            3: "broker",
            4: "ghost",
            5: "marco",
            6: "lou"
        }
        return npcs.get(district_id, "ray")
    
    def _get_npc_name(self, npc_id: str) -> str:
        names = {
            "ray": "Ray",
            "chen": "Ms. Chen",
            "broker": "The Broker",
            "ghost": "Ghost",
            "marco": "Marco",
            "lou": "Lucky Lou"
        }
        return names.get(npc_id, npc_id.title())
    
    def _get_efficiency_bar(self, efficiency: float) -> str:
        """Visual bar for job efficiency"""
        filled = int(efficiency * 10)
        filled = max(0, min(10, filled))
        
        if efficiency >= 0.8:
            bar = "█" * filled + "░" * (10 - filled)
        elif efficiency >= 0.5:
            bar = "🟡" + "█" * (filled - 1) + "░" * (10 - filled)
        else:
            bar = "🔴" + "█" * (filled - 1) + "░" * (10 - filled)
        
        return bar
    
    def _get_max_jobs(self, premium_tier: str) -> int:
        tiers = {
            "citizen": 3,
            "resident": 3,
            "elite": 4,
            "obsidian": 5
        }
        return tiers.get(premium_tier, 3)
    
    def _get_premium_multiplier(self, premium_tier: str) -> float:
        multipliers = {
            "citizen": 1.0,
            "resident": 1.2,
            "elite": 1.4,
            "obsidian": 2.0
        }
        return multipliers.get(premium_tier, 1.0)


async def setup(bot):
    await bot.add_cog(WorkCog(bot))