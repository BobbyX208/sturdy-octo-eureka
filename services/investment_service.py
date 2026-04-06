import logging
import random
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

from database.connection import DatabasePool
from database.queries import InvestmentQueries, PlayerQueries
from core.cache import CacheManager
from core.cooldowns import CooldownManager
from events.bus import EventBus
from domain.stock_math import StockMath
from domain.economy_rules import EconomyRules
from config.settings import Config
from config.constants import GameConstants


class InvestmentService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus, cooldowns: CooldownManager):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.cooldowns = cooldowns
        self.logger = logging.getLogger("simcoin.services.investment")
        
        self.investment_queries = InvestmentQueries(db)
        self.player_queries = PlayerQueries(db)
        
        self.stock_math = StockMath(Config.GBM_MU, Config.GBM_SIGMA, Config.SENTIMENT_MAX_PRESSURE)
        self.economy_rules = EconomyRules()
    
    async def buy_shares(self, user_id: int, company_id: str, shares: int) -> Dict[str, Any]:
        conn = None
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found. Use /start first."}
            
            current_price = await self.investment_queries.get_company_price(company_id)
            
            if not current_price:
                return {"success": False, "message": "Company not found."}
            
            total_cost = current_price * shares
            
            if player.get("wallet", 0) < total_cost:
                return {"success": False, "message": f"Insufficient funds. Need {total_cost} SC, have {player.get('wallet', 0)} SC."}
            
            cooldown_active = await self.cooldowns.is_active(user_id, "invest")
            
            if cooldown_active:
                remaining = await self.cooldowns.get_remaining(user_id, "invest")
                return {"success": False, "message": f"Investment cooldown active. Try again in {remaining} seconds."}
            
            conn = await self.db.acquire()
            try:
                await conn.execute("BEGIN")
                
                await self.player_queries.update_balance(user_id, wallet_delta=-total_cost, connection=conn)
                
                await self.player_queries.add_transaction(
                    user_id, -total_cost, player.get("wallet", 0) - total_cost,
                    "buy_shares", f"Bought {shares} shares of {company_id} at {current_price} SC",
                    connection=conn
                )
                
                await self.investment_queries.buy_shares(user_id, company_id, shares, current_price, connection=conn)
                
                await self.investment_queries.update_sentiment(company_id, shares, 0, connection=conn)
                
                await conn.execute("COMMIT")
            except Exception as e:
                await conn.execute("ROLLBACK")
                raise e
            finally:
                await self.db.release(conn)
            
            await self.cooldowns.set(user_id, "invest", Config.INVEST_COOLDOWN)
            await self.cache.delete(self.cache.generate_key("player", user_id))
            
            await self.event_bus.fire("investment.bought", {
                "user_id": user_id,
                "company": company_id,
                "shares": shares,
                "price": current_price,
                "total": total_cost
            })
            
            return {
                "success": True,
                "message": f"Bought {shares} shares of {company_id} at {current_price} SC each. Total: {total_cost} SC",
                "shares": shares,
                "price": current_price,
                "total": total_cost
            }
            
        except Exception as e:
            self.logger.error(f"Buy shares failed for {user_id}: {e}")
            if conn:
                await self.db.release(conn)
            raise
    
    async def sell_shares(self, user_id: int, company_id: str, shares: int) -> Dict[str, Any]:
        conn = None
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            current_price = await self.investment_queries.get_company_price(company_id)
            
            if not current_price:
                return {"success": False, "message": "Company not found."}
            
            investment = await self.investment_queries.sell_shares(user_id, company_id, shares)
            
            if not investment:
                return {"success": False, "message": f"You don't own {shares} shares of {company_id}."}
            
            total_value = current_price * shares
            avg_price = investment.get("avg_buy_price", 0)
            profit = (current_price - avg_price) * shares
            
            tax = self.economy_rules.calculate_investment_tax(profit) if profit > 0 else 0
            after_tax = total_value - tax
            
            conn = await self.db.acquire()
            try:
                await conn.execute("BEGIN")
                
                await self.player_queries.update_balance(user_id, wallet_delta=after_tax, connection=conn)
                
                await self.player_queries.add_transaction(
                    user_id, after_tax, player.get("wallet", 0) + after_tax,
                    "sell_shares", f"Sold {shares} shares of {company_id} at {current_price} SC",
                    connection=conn
                )
                
                await self.investment_queries.update_sentiment(company_id, 0, shares, connection=conn)
                
                await conn.execute("COMMIT")
            except Exception as e:
                await conn.execute("ROLLBACK")
                raise e
            finally:
                await self.db.release(conn)
            
            await self.cache.delete(self.cache.generate_key("player", user_id))
            
            await self.event_bus.fire("investment.sold", {
                "user_id": user_id,
                "company": company_id,
                "shares": shares,
                "price": current_price,
                "profit": profit,
                "tax": tax
            })
            
            return {
                "success": True,
                "message": f"Sold {shares} shares of {company_id} at {current_price} SC each. Total: {total_value} SC. Tax: {tax} SC. Profit: {profit} SC",
                "shares": shares,
                "price": current_price,
                "total": total_value,
                "profit": profit,
                "tax": tax
            }
            
        except Exception as e:
            self.logger.error(f"Sell shares failed for {user_id}: {e}")
            if conn:
                await self.db.release(conn)
            raise
    
    async def get_portfolio(self, user_id: int) -> Dict[str, Any]:
        try:
            portfolio = await self.investment_queries.get_portfolio(user_id)
            
            total_value = 0
            total_cost = 0
            
            for holding in portfolio:
                shares = holding.get("shares", 0)
                current_price = holding.get("current_price", 0)
                avg_buy_price = holding.get("avg_buy_price", 0)
                
                total_value += shares * current_price
                total_cost += shares * avg_buy_price
            
            total_profit = total_value - total_cost
            
            return {
                "success": True,
                "holdings": portfolio,
                "total_value": total_value,
                "total_cost": total_cost,
                "total_profit": total_profit,
                "profit_percent": (total_profit / total_cost * 100) if total_cost > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Get portfolio failed for {user_id}: {e}")
            raise
    
    async def get_stock_prices(self) -> List[Dict[str, Any]]:
        try:
            cache_key = self.cache.generate_key("stock_prices")
            cached = await self.cache.get(cache_key)
            
            if cached:
                return cached
            
            conn = await self.db.acquire()
            try:
                rows = await conn.fetch("""
                    SELECT DISTINCT ON (company_id) company_id, price, recorded_at
                    FROM stock_prices
                    ORDER BY company_id, recorded_at DESC
                """)
                
                companies = []
                for row in rows:
                    company = dict(row)
                    company_id = company["company_id"]
                    
                    yesterday = await conn.fetchval("""
                        SELECT price FROM stock_prices
                        WHERE company_id = $1 AND recorded_at < NOW() - INTERVAL '24 hours'
                        ORDER BY recorded_at DESC
                        LIMIT 1
                    """, company_id)
                    
                    yesterday_price = yesterday or company["price"]
                    company["change"] = company["price"] - yesterday_price
                    company["change_percent"] = (company["change"] / yesterday_price) * 100 if yesterday_price > 0 else 0
                    companies.append(company)
            finally:
                await self.db.release(conn)
            
            await self.cache.set(cache_key, companies, ttl=300)
            
            return companies
            
        except Exception as e:
            self.logger.error(f"Get stock prices failed: {e}")
            return []
    
    async def process_gbm_tick(self) -> None:
        conn = None
        try:
            companies = await self.get_stock_prices()
            
            conn = await self.db.acquire()
            try:
                await conn.execute("BEGIN")
                
                for company in companies:
                    current_price = company["price"]
                    company_id = company["company_id"]
                    
                    sentiment = await self._get_sentiment_for_period(company_id, conn)
                    
                    if sentiment:
                        current_price = self.stock_math.apply_sentiment(current_price, sentiment, 1000)
                    
                    news = await self._get_active_news(company_id, conn)
                    
                    if news:
                        current_price = self.stock_math.apply_news_modifier(current_price, news.get("modifier", 1.0))
                    
                    event = await self._get_active_event(company_id, conn)
                    
                    if event:
                        current_price = self.stock_math.apply_event_multiplier(current_price, event.get("multiplier", 1.0))
                    
                    new_price = self.stock_math.geometric_brownian_motion(current_price)
                    
                    new_price = max(Config.STOCK_PRICE_FLOOR, min(Config.STOCK_PRICE_CEILING, new_price))
                    
                    await self.investment_queries.save_price(company_id, new_price, connection=conn)
                
                await conn.execute("COMMIT")
            except Exception as e:
                await conn.execute("ROLLBACK")
                raise e
            finally:
                if conn:
                    await self.db.release(conn)
                    conn = None
            
            await self.cache.delete(self.cache.generate_key("stock_prices"))
            
            await self.event_bus.fire("stock_tick.completed", {
                "companies": len(companies),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            self.logger.info(f"GBM tick completed for {len(companies)} companies")
            
        except Exception as e:
            self.logger.error(f"Process GBM tick failed: {e}")
            if conn:
                await self.db.release(conn)
            raise
    
    async def _get_sentiment_for_period(self, company_id: str, conn=None) -> Optional[int]:
        try:
            should_release = False
            if conn is None:
                conn = await self.db.acquire()
                should_release = True
            
            try:
                row = await conn.fetchrow("""
                    SELECT net_pressure, period_start FROM stock_sentiment
                    WHERE company_id = $1 AND applied = FALSE
                    ORDER BY period_start ASC
                    LIMIT 1
                """, company_id)
                
                if row:
                    await conn.execute("""
                        UPDATE stock_sentiment SET applied = TRUE
                        WHERE company_id = $1 AND period_start = $2
                    """, company_id, row["period_start"])
                    
                    return row["net_pressure"]
                
                return None
            finally:
                if should_release and conn:
                    await self.db.release(conn)
                
        except Exception as e:
            self.logger.error(f"Get sentiment failed: {e}")
            return None
    
    async def _get_active_news(self, company_id: str, conn=None) -> Optional[Dict[str, Any]]:
        try:
            should_release = False
            if conn is None:
                conn = await self.db.acquire()
                should_release = True
            
            try:
                sector = await conn.fetchval("""
                    SELECT sector FROM companies WHERE id = $1
                """, company_id)
                
                if not sector:
                    return None
                
                row = await conn.fetchrow("""
                    SELECT modifier FROM market_news
                    WHERE sector = $1 AND expires_at > NOW()
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, sector)
                
                return dict(row) if row else None
            finally:
                if should_release and conn:
                    await self.db.release(conn)
                
        except Exception as e:
            self.logger.error(f"Get active news failed: {e}")
            return None
    
    async def _get_active_event(self, company_id: str, conn=None) -> Optional[Dict[str, Any]]:
        try:
            should_release = False
            if conn is None:
                conn = await self.db.acquire()
                should_release = True
            
            try:
                row = await conn.fetchrow("""
                    SELECT multiplier FROM stock_events
                    WHERE company_id = $1 AND ends_at > NOW()
                    ORDER BY started_at DESC
                    LIMIT 1
                """, company_id)
                
                return dict(row) if row else None
            finally:
                if should_release and conn:
                    await self.db.release(conn)
                
        except Exception as e:
            self.logger.error(f"Get active event failed: {e}")
            return None