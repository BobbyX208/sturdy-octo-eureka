import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from database.connection import DatabasePool
from database.queries import PlayerQueries
from core.cache import CacheManager
from events.bus import EventBus
from domain.market_rules import MarketRules
from config.settings import Config


class MarketService:
    
    def __init__(self, db: DatabasePool, cache: CacheManager, event_bus: EventBus):
        self.db = db
        self.cache = cache
        self.event_bus = event_bus
        self.logger = logging.getLogger("simcoin.services.market")
        
        self.player_queries = PlayerQueries(db)
        self.market_rules = MarketRules()
    
    async def list_item(self, user_id: int, item_id: str, quantity: int, price_per_unit: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            can_list, reason = self.market_rules.can_list_item(player.get("reputation", 0))
            
            if not can_list:
                return {"success": False, "message": reason}
            
            async with self.db.acquire() as conn:
                inventory = await conn.fetchrow("""
                    SELECT quantity FROM inventory
                    WHERE discord_id = $1 AND item_id = $2
                """, user_id, item_id)
                
                if not inventory or inventory["quantity"] < quantity:
                    return {"success": False, "message": f"You don't have {quantity} of {item_id}."}
                
                fee = self.market_rules.calculate_listing_fee(price_per_unit, quantity)
                
                if player.get("wallet", 0) < fee:
                    return {"success": False, "message": f"Insufficient funds for listing fee of {fee} SC."}
                
                async with conn.transaction():
                    await self.player_queries.update_balance(user_id, wallet_delta=-fee)
                    
                    await conn.execute("""
                        UPDATE inventory
                        SET quantity = quantity - $3
                        WHERE discord_id = $1 AND item_id = $2
                    """, user_id, item_id, quantity)
                    
                    await conn.execute("""
                        INSERT INTO market_listings (seller_id, item_id, quantity, price_per_unit, expires_at)
                        VALUES ($1, $2, $3, $4, NOW() + INTERVAL '7 days')
                    """, user_id, item_id, quantity, price_per_unit)
            
            await self.cache.delete(self.cache.generate_key("inventory", user_id))
            
            return {
                "success": True,
                "message": f"Listed {quantity}x {item_id} at {price_per_unit} SC each. Fee: {fee} SC",
                "item_id": item_id,
                "quantity": quantity,
                "price": price_per_unit,
                "fee": fee
            }
            
        except Exception as e:
            self.logger.error(f"List item failed for {user_id}: {e}")
            raise
    
    async def buy_item(self, user_id: int, listing_id: int, quantity: int) -> Dict[str, Any]:
        try:
            player = await self.player_queries.get(user_id)
            
            if not player:
                return {"success": False, "message": "Player not found."}
            
            async with self.db.acquire() as conn:
                listing = await conn.fetchrow("""
                    SELECT * FROM market_listings
                    WHERE id = $1 AND status = 'active' AND expires_at > NOW()
                """, listing_id)
                
                if not listing:
                    return {"success": False, "message": "Listing not found or expired."}
                
                if quantity > listing["quantity"]:
                    return {"success": False, "message": f"Only {listing['quantity']} available."}
                
                total_cost = quantity * listing["price_per_unit"]
                
                if player.get("wallet", 0) < total_cost:
                    return {"success": False, "message": f"Insufficient funds. Need {total_cost} SC."}
                
                tax = self.market_rules.calculate_market_tax(total_cost, player.get("reputation", 0))
                seller_receives = total_cost - tax
                
                async with conn.transaction():
                    await self.player_queries.update_balance(user_id, wallet_delta=-total_cost)
                    await self.player_queries.update_balance(listing["seller_id"], wallet_delta=seller_receives)
                    
                    await conn.execute("""
                        INSERT INTO inventory (discord_id, item_id, quantity)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (discord_id, item_id)
                        DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
                    """, user_id, listing["item_id"], quantity)
                    
                    new_quantity = listing["quantity"] - quantity
                    
                    if new_quantity == 0:
                        await conn.execute("""
                            UPDATE market_listings SET status = 'sold' WHERE id = $1
                        """, listing_id)
                    else:
                        await conn.execute("""
                            UPDATE market_listings SET quantity = $2 WHERE id = $1
                        """, listing_id, new_quantity)
                    
                    await self.player_queries.add_transaction(
                        user_id, -total_cost, player.get("wallet", 0) - total_cost,
                        "market_purchase", f"Bought {quantity}x {listing['item_id']} from {listing['seller_id']}"
                    )
                    
                    await self.player_queries.add_transaction(
                        listing["seller_id"], seller_receives, 0,
                        "market_sale", f"Sold {quantity}x {listing['item_id']} to {user_id}"
                    )
            
            await self.cache.delete(self.cache.generate_key("inventory", user_id))
            await self.cache.delete(self.cache.generate_key("inventory", listing["seller_id"]))
            
            return {
                "success": True,
                "message": f"Bought {quantity}x {listing['item_id']} for {total_cost} SC",
                "item_id": listing["item_id"],
                "quantity": quantity,
                "total": total_cost,
                "tax": tax
            }
            
        except Exception as e:
            self.logger.error(f"Buy item failed for {user_id}: {e}")
            raise
    
    async def get_listings(self, item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            async with self.db.acquire() as conn:
                if item_id:
                    rows = await conn.fetch("""
                        SELECT l.*, p.username as seller_name
                        FROM market_listings l
                        JOIN players p ON p.discord_id = l.seller_id
                        WHERE l.item_id = $1 AND l.status = 'active' AND l.expires_at > NOW()
                        ORDER BY l.price_per_unit ASC
                        LIMIT 50
                    """, item_id)
                else:
                    rows = await conn.fetch("""
                        SELECT l.*, p.username as seller_name
                        FROM market_listings l
                        JOIN players p ON p.discord_id = l.seller_id
                        WHERE l.status = 'active' AND l.expires_at > NOW()
                        ORDER BY l.listed_at DESC
                        LIMIT 50
                    """)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Get listings failed: {e}")
            raise
    
    async def cancel_listing(self, user_id: int, listing_id: int) -> Dict[str, Any]:
        try:
            async with self.db.acquire() as conn:
                listing = await conn.fetchrow("""
                    SELECT * FROM market_listings
                    WHERE id = $1 AND seller_id = $2 AND status = 'active'
                """, listing_id, user_id)
                
                if not listing:
                    return {"success": False, "message": "Listing not found or already sold."}
                
                async with conn.transaction():
                    await conn.execute("""
                        UPDATE market_listings SET status = 'cancelled' WHERE id = $1
                    """, listing_id)
                    
                    await conn.execute("""
                        INSERT INTO inventory (discord_id, item_id, quantity)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (discord_id, item_id)
                        DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
                    """, user_id, listing["item_id"], listing["quantity"])
            
            await self.cache.delete(self.cache.generate_key("inventory", user_id))
            
            return {
                "success": True,
                "message": f"Cancelled listing for {listing['quantity']}x {listing['item_id']}"
            }
            
        except Exception as e:
            self.logger.error(f"Cancel listing failed for {user_id}: {e}")
            raise