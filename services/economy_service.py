import random
import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from database.connection import DatabasePool
from database.queries import PlayerQueries, JobQueries, CooldownQueries
from core.cache import CacheManager
from core.cooldowns import CooldownManager
from events.bus import EventBus
from domain.jobs import JobDomain
from domain.economy_rules import EconomyRules
from domain.premium import PremiumDomain
from config.settings import Config
from config.constants import GameConstants


class EconomyService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus, cooldowns: CooldownManager):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.cooldowns = cooldowns
        self.logger = logging.getLogger("simcoin.services.economy")
        
        self.player_queries = PlayerQueries(db)
        self.job_queries = JobQueries(db)
        
        self.job_domain = JobDomain(GameConstants.JOB_BASE_PAY)
        self.economy_rules = EconomyRules()
        self.premium_domain = PremiumDomain(Config.PREMIUM_TIERS)
    
    async def work(self, user_id: int, job_id: str) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found. Use /start first."}
            
            if player.get("is_jailed", False):
                return {"success": False, "message": "You are in jail and cannot work."}
            
            cooldown_active = await self.cooldowns.is_active(user_id, "work")
            
            if cooldown_active:
                remaining = await self.cooldowns.get_remaining(user_id, "work")
                return {"success": False, "message": f"Work cooldown active. Try again in {remaining} seconds."}
            
            active_jobs = await self.job_queries.get_active_jobs(user_id)
            job_exists = any(j["job_id"] == job_id for j in active_jobs)
            
            if not job_exists:
                return {"success": False, "message": "You don't have this job. Use /jobs to see available jobs."}
            
            daily_work_count = next((j["daily_work_count"] for j in active_jobs if j["job_id"] == job_id), 0)
            
            if daily_work_count >= GameConstants.MAX_DAILY_JOBS:
                return {"success": False, "message": f"You've worked this job {daily_work_count} times today. Daily limit reached."}
            
            effective_tier = self.premium_domain.get_effective_tier(player)
            cooldown_seconds = self.job_domain.calculate_cooldown(player, Config.WORK_COOLDOWN)
            
            reward = self.job_domain.calculate_reward(player, job_id)
            
            await self.player_queries.update_balance(user_id, wallet_delta=reward)
            await self.player_queries.increment_daily_stats(user_id, earned=reward, jobs=1)
            await self.job_queries.update_last_worked(user_id, job_id)
            await self.cooldowns.set(user_id, "work", cooldown_seconds)
            
            await self.player_queries.add_transaction(
                user_id, reward, player.get("wallet", 0) + reward,
                "work", f"Worked as {job_id}"
            )
            
            await self.event_bus.fire("job.completed", {
                "user_id": user_id,
                "job_id": job_id,
                "reward": reward
            })
            
            return {
                "success": True,
                "message": f"You worked as {job_id} and earned {reward} SC.",
                "reward": reward,
                "new_balance": player.get("wallet", 0) + reward
            }
            
        except Exception as e:
            self.logger.error(f"Work failed for {user_id}: {e}")
            raise
    
    async def daily(self, user_id: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found. Use /start first."}
            
            cooldown_active = await self.cooldowns.is_active(user_id, "daily")
            
            if cooldown_active:
                remaining = await self.cooldowns.get_remaining(user_id, "daily")
                return {"success": False, "message": f"Daily reward already claimed. Try again in {remaining} seconds."}
            
            streak = player.get("daily_streak", 0)
            last_daily = player.get("last_daily")
            
            if last_daily:
                days_diff = (datetime.now(timezone.utc) - last_daily).days
                
                if days_diff > 1:
                    days_missed = days_diff - 1
                    penalty, new_streak = self.economy_rules.calculate_streak_penalty(streak, days_missed)
                    
                    if penalty > 0:
                        await self.player_queries.update_balance(user_id, wallet_delta=-penalty)
                        await self.player_queries.add_transaction(
                            user_id, -penalty, player.get("wallet", 0) - penalty,
                            "streak_penalty", f"Missed {days_missed} days"
                        )
                    
                    streak = new_streak
            
            effective_tier = self.premium_domain.get_effective_tier(player)
            reward, new_streak = self.economy_rules.calculate_daily_reward(streak, effective_tier)
            
            await self.player_queries.update_balance(user_id, wallet_delta=reward)
            await self.cooldowns.set(user_id, "daily", Config.DAILY_COOLDOWN)
            
            await self.player_queries.add_transaction(
                user_id, reward, player.get("wallet", 0) + reward,
                "daily", f"Daily reward - {new_streak} day streak"
            )
            
            await self.event_bus.fire("daily.claimed", {
                "user_id": user_id,
                "reward": reward,
                "streak": new_streak
            })
            
            return {
                "success": True,
                "message": f"You claimed your daily reward of {reward} SC! Streak: {new_streak} days",
                "reward": reward,
                "streak": new_streak
            }
            
        except Exception as e:
            self.logger.error(f"Daily failed for {user_id}: {e}")
            raise
    
    async def bank_transaction(self, user_id: int, action: str, amount: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found. Use /start first."}
            
            if amount <= 0:
                return {"success": False, "message": "Amount must be positive."}
            
            effective_tier = self.premium_domain.get_effective_tier(player)
            fee = self.economy_rules.calculate_bank_fee(amount, action == "deposit", effective_tier)
            
            if action == "deposit":
                if player.get("wallet", 0) < amount:
                    return {"success": False, "message": f"Insufficient wallet balance. You have {player.get('wallet', 0)} SC."}
                
                amount_after_fee = amount - fee
                
                await self.player_queries.update_balance(user_id, wallet_delta=-amount, bank_delta=amount_after_fee)
                
                await self.player_queries.add_transaction(
                    user_id, -amount, player.get("wallet", 0) - amount,
                    "bank_deposit", f"Deposited {amount} SC (fee: {fee})"
                )
                
                return {
                    "success": True,
                    "message": f"Deposited {amount} SC to bank. Fee: {fee} SC. New wallet: {player.get('wallet', 0) - amount}",
                    "new_wallet": player.get("wallet", 0) - amount,
                    "new_bank": player.get("bank", 0) + amount_after_fee
                }
                
            elif action == "withdraw":
                if player.get("bank", 0) < amount:
                    return {"success": False, "message": f"Insufficient bank balance. You have {player.get('bank', 0)} SC."}
                
                amount_after_fee = amount - fee
                
                await self.player_queries.update_balance(user_id, wallet_delta=amount_after_fee, bank_delta=-amount)
                
                await self.player_queries.add_transaction(
                    user_id, amount_after_fee, player.get("wallet", 0) + amount_after_fee,
                    "bank_withdraw", f"Withdrew {amount} SC (fee: {fee})"
                )
                
                return {
                    "success": True,
                    "message": f"Withdrew {amount} SC from bank. Fee: {fee} SC. New wallet: {player.get('wallet', 0) + amount_after_fee}",
                    "new_wallet": player.get("wallet", 0) + amount_after_fee,
                    "new_bank": player.get("bank", 0) - amount
                }
            
            return {"success": False, "message": "Invalid action. Use deposit or withdraw."}
            
        except Exception as e:
            self.logger.error(f"Bank transaction failed for {user_id}: {e}")
            raise
    
    async def transfer(self, sender_id: int, receiver_id: int, amount: int) -> Dict[str, Any]:
        try:
            sender = await self.player_queries.get(sender_id)
            receiver = await self.player_queries.get(receiver_id)
            
            if not sender:
                return {"success": False, "message": "Sender not found."}
            
            if not receiver:
                return {"success": False, "message": "Receiver not found."}
            
            if amount <= 0:
                return {"success": False, "message": "Amount must be positive."}
            
            if sender.get("wallet", 0) < amount:
                return {"success": False, "message": f"Insufficient balance. You have {sender.get('wallet', 0)} SC."}
            
            effective_tier = self.premium_domain.get_effective_tier(sender)
            fee = self.economy_rules.calculate_transfer_fee(amount, effective_tier)
            amount_after_fee = amount - fee
            
            async with self.db.transaction():
                await self.player_queries.update_balance(sender_id, wallet_delta=-(amount + fee))
                await self.player_queries.update_balance(receiver_id, wallet_delta=amount_after_fee)
                
                await self.player_queries.add_transaction(
                    sender_id, -(amount + fee), sender.get("wallet", 0) - (amount + fee),
                    "transfer_sent", f"Sent {amount} SC to {receiver_id} (fee: {fee})"
                )
                
                await self.player_queries.add_transaction(
                    receiver_id, amount_after_fee, receiver.get("wallet", 0) + amount_after_fee,
                    "transfer_received", f"Received {amount} SC from {sender_id}"
                )
            
            await self.cache.delete(self.cache.generate_key("player", sender_id))
            await self.cache.delete(self.cache.generate_key("player", receiver_id))
            
            await self.event_bus.fire("transfer.completed", {
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "amount": amount,
                "fee": fee
            })
            
            return {
                "success": True,
                "message": f"Sent {amount} SC to {receiver_id}. Fee: {fee} SC.",
                "amount": amount,
                "fee": fee,
                "new_balance": sender.get("wallet", 0) - (amount + fee)
            }
            
        except Exception as e:
            self.logger.error(f"Transfer failed: {e}")
            raise