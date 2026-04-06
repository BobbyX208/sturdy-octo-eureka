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

    async def apply_job(self, user_id: int, job_id: str) -> Dict[str, Any]:
        """Apply for a job."""
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found. Use /start first."}
            
            if player.get("is_jailed", False):
                return {"success": False, "message": "You are in jail and cannot apply for jobs."}
            
            job_config = GameConstants.JOB_BASE_PAY.get(job_id)
            if not job_config:
                return {"success": False, "message": "Job does not exist."}
            
            required_rep = GameConstants.JOB_HIRE_CHANCE.get(job_id, 0.5)
            required_rep_val = 0
            if job_id == "manager":
                required_rep_val = 1000
            elif job_id == "analyst":
                required_rep_val = 500
            elif job_id == "trader":
                required_rep_val = 300
            
            if player.get("reputation", 0) < required_rep_val:
                return {"success": False, "message": f"Requires {required_rep_val} reputation for this job."}
            
            active_jobs = await self.job_queries.get_active_jobs(user_id)
            max_jobs = self.premium_domain.get_max_jobs(self.premium_domain.get_effective_tier(player))
            
            if len(active_jobs) >= max_jobs:
                return {"success": False, "message": f"You already have the maximum of {max_jobs} jobs."}
            
            await self.job_queries.hire(user_id, job_id)
            
            await self.event_bus.fire("job.hired", {
                "user_id": user_id,
                "job_id": job_id,
                "npc_name": "Ray",
                "npc_line": f"Welcome aboard, {player.get('username', 'player')}. Don't mess up."
            })
            
            return {
                "success": True,
                "message": f"You have been hired as {job_id}!",
                "job_id": job_id
            }
            
        except Exception as e:
            self.logger.error(f"Apply job failed for {user_id}: {e}")
            raise

    async def quit_job(self, user_id: int, job_id: str) -> Dict[str, Any]:
        """Quit a job."""
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            active_jobs = await self.job_queries.get_active_jobs(user_id)
            job_exists = any(j["job_id"] == job_id for j in active_jobs)
            
            if not job_exists:
                return {"success": False, "message": "You don't have this job."}
            
            await self.job_queries.quit(user_id, job_id)
            
            await self.event_bus.fire("job.quit", {
                "user_id": user_id,
                "job_id": job_id,
                "npc_line": f"You quit {job_id}. The city will remember."
            })
            
            return {
                "success": True,
                "message": f"You have quit {job_id}.",
                "job_id": job_id
            }
            
        except Exception as e:
            self.logger.error(f"Quit job failed for {user_id}: {e}")
            raise

    async def gamble(self, user_id: int, game: str, amount: int) -> Dict[str, Any]:
        """Gamble SC on a game."""
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            if player.get("is_jailed", False):
                return {"success": False, "message": "You are in jail and cannot gamble."}
            
            if amount <= 0:
                return {"success": False, "message": "Amount must be positive."}
            
            if player.get("wallet", 0) < amount:
                return {"success": False, "message": f"Insufficient funds. You have {player.get('wallet', 0)} SC."}
            
            daily_gambled = player.get("daily_gambled", 0)
            if daily_gambled + amount > GameConstants.MAX_DAILY_GAMBLED:
                return {"success": False, "message": f"Daily gambling limit reached. Max {GameConstants.MAX_DAILY_GAMBLED} SC per day."}
            
            cooldown_active = await self.cooldowns.is_active(user_id, "gamble")
            if cooldown_active:
                remaining = await self.cooldowns.get_remaining(user_id, "gamble")
                return {"success": False, "message": f"Gambling cooldown active. Try again in {remaining} seconds."}
            
            game_config = GameConstants.GAMBLING_GAMES.get(game)
            if not game_config:
                return {"success": False, "message": "Invalid game. Choose: slots, blackjack, dice, roulette"}
            
            from utils.luck import Luck
            luck = Luck()
            
            if game == "slots":
                won, payout_multiplier, outcome_detail = self._play_slots(luck)
            elif game == "dice":
                won, payout_multiplier, outcome_detail = self._play_dice(luck, game_config)
            elif game == "roulette":
                won, payout_multiplier, outcome_detail = self._play_roulette(luck, game_config)
            elif game == "blackjack":
                won, payout_multiplier, outcome_detail = self._play_blackjack(luck, game_config)
            else:
                return {"success": False, "message": "Game not implemented."}
            
            if won:
                amount_won = int(amount * payout_multiplier)
                net = amount_won - amount
                await self.player_queries.update_balance(user_id, wallet_delta=amount_won)
                await self.player_queries.add_transaction(
                    user_id, amount_won, player.get("wallet", 0) + amount_won,
                    "gamble_win", f"Won {amount_won} SC playing {game}"
                )
            else:
                amount_won = 0
                net = -amount
                await self.player_queries.update_balance(user_id, wallet_delta=-amount)
                await self.player_queries.add_transaction(
                    user_id, -amount, player.get("wallet", 0) - amount,
                    "gamble_loss", f"Lost {amount} SC playing {game}"
                )
            
            await self.player_queries.increment_daily_stats(user_id, gambled=amount)
            await self.cooldowns.set(user_id, "gamble", 30)
            
            return {
                "success": True,
                "game": game,
                "won": won,
                "amount_bet": amount,
                "amount_won": amount_won,
                "net": net,
                "new_wallet": player.get("wallet", 0) + (amount_won if won else -amount),
                "outcome_detail": outcome_detail
            }
            
        except Exception as e:
            self.logger.error(f"Gamble failed for {user_id}: {e}")
            raise

    def _play_slots(self, luck) -> tuple:
        """Slots game logic."""
        symbols = ["🍒", "🍒", "🍒", "🍋", "🍋", "7️⃣", "7️⃣", "🎰", "🎰", "💎"]
        reels = [luck.weighted_choice(symbols, [0.3, 0.3, 0.2, 0.1, 0.1]) for _ in range(3)]
        outcome = " ".join(reels)
        
        if reels[0] == reels[1] == reels[2]:
            if reels[0] == "💎":
                return True, 50.0, f"🎰 JACKPOT! {outcome} (50x)"
            elif reels[0] == "7️⃣":
                return True, 10.0, f"🎰 {outcome} (10x)"
            elif reels[0] == "🎰":
                return True, 5.0, f"🎰 {outcome} (5x)"
            else:
                return True, 3.0, f"🎰 {outcome} (3x)"
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            return True, 1.5, f"🎰 {outcome} (1.5x)"
        
        return False, 0.0, f"🎰 {outcome} - Nothing"

    def _play_dice(self, luck, game_config) -> tuple:
        """Dice game logic."""
        player_roll = luck.roll_dice(6)
        house_roll = luck.roll_dice(6)
        
        if player_roll > house_roll:
            multiplier_range = game_config.get("multiplier_range", (1.5, 8.0))
            multiplier = luck.random_float(multiplier_range[0], multiplier_range[1])
            return True, multiplier, f"🎲 You rolled {player_roll}, House rolled {house_roll} ({multiplier}x)"
        elif player_roll < house_roll:
            return False, 0.0, f"🎲 You rolled {player_roll}, House rolled {house_roll} - Lost"
        else:
            return False, 0.0, f"🎲 You rolled {player_roll}, House rolled {house_roll} - Push (lost)"

    def _play_roulette(self, luck, game_config) -> tuple:
        """Roulette game logic."""
        bet_type = "red"
        numbers = list(range(37))
        winning = luck.weighted_choice(numbers, [1/37] * 37)
        
        payout = game_config.get("payouts", {}).get(bet_type, 1.8)
        
        if bet_type == "red" and winning in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]:
            return True, payout, f"🎰 Ball landed on {winning} (Red) - {payout}x"
        elif bet_type == "black" and winning in [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]:
            return True, payout, f"🎰 Ball landed on {winning} (Black) - {payout}x"
        else:
            return False, 0.0, f"🎰 Ball landed on {winning} - Lost"

    def _play_blackjack(self, luck, game_config) -> tuple:
        """Blackjack game logic."""
        player_hand = [luck.random_range(1, 11), luck.random_range(1, 11)]
        dealer_hand = [luck.random_range(1, 11), luck.random_range(1, 11)]
        
        player_total = sum(player_hand)
        dealer_total = sum(dealer_hand)
        
        if player_total == 21 and len(player_hand) == 2:
            return True, 2.5, f"🃏 Blackjack! Player: {player_total}, Dealer: {dealer_total} (2.5x)"
        elif player_total > 21:
            return False, 0.0, f"🃏 Bust! Player: {player_total}, Dealer: {dealer_total}"
        elif dealer_total > 21 or player_total > dealer_total:
            return True, 2.0, f"🃏 You win! Player: {player_total}, Dealer: {dealer_total} (2x)"
        elif player_total < dealer_total:
            return False, 0.0, f"🃏 You lose! Player: {player_total}, Dealer: {dealer_total}"
        else:
            return False, 0.0, f"🃏 Push! Player: {player_total}, Dealer: {dealer_total}"