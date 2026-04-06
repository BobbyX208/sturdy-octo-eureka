import asyncio
import logging
import traceback
from typing import Dict, List, Any, Callable, Optional, Awaitable
from datetime import datetime, timezone
import uuid


class EventBus:
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._async_handlers: Dict[str, List[Callable]] = {}
        self._event_history: List[Dict[str, Any]] = []
        self._max_history: int = 1000
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger("simcoin.events")
        self._running = True
    
    async def initialize(self) -> None:
        self._logger.info("Event bus initialized")
    
    def register(self, event_name: str, handler: Callable, async_handler: bool = True) -> None:
        if async_handler:
            if event_name not in self._async_handlers:
                self._async_handlers[event_name] = []
            self._async_handlers[event_name].append(handler)
            self._logger.debug(f"Registered async handler for {event_name}")
        else:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            self._handlers[event_name].append(handler)
            self._logger.debug(f"Registered sync handler for {event_name}")
    
    def unregister(self, event_name: str, handler: Callable) -> None:
        if event_name in self._async_handlers:
            if handler in self._async_handlers[event_name]:
                self._async_handlers[event_name].remove(handler)
                self._logger.debug(f"Unregistered async handler for {event_name}")
        
        if event_name in self._handlers:
            if handler in self._handlers[event_name]:
                self._handlers[event_name].remove(handler)
                self._logger.debug(f"Unregistered sync handler for {event_name}")
    
    async def fire(self, event_name: str, data: Dict[str, Any], source: str = "unknown") -> None:
        if not self._running:
            self._logger.warning(f"Event bus closed, dropping event {event_name}")
            return
        
        event_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc)
        
        self._logger.debug(f"Firing event {event_name} [{event_id}] from {source}")
        
        await self._store_event(event_id, event_name, data, source, timestamp)
        
        async_handlers = self._async_handlers.get(event_name, [])
        sync_handlers = self._handlers.get(event_name, [])
        
        if not async_handlers and not sync_handlers:
            self._logger.debug(f"No handlers for event {event_name}")
            return
        
        tasks = []
        
        for handler in async_handlers:
            task = asyncio.create_task(
                self._run_async_handler(event_name, event_id, handler, data)
            )
            tasks.append(task)
        
        for handler in sync_handlers:
            try:
                await asyncio.to_thread(handler, data)
            except Exception as e:
                self._logger.error(f"Sync handler error for {event_name}: {e}")
                self._logger.error(traceback.format_exc())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_async_handler(self, event_name: str, event_id: str, handler: Callable, data: Dict[str, Any]) -> None:
        try:
            await asyncio.wait_for(
                handler(data, event_id=event_id),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            self._logger.error(f"Handler timeout for {event_name}: {handler.__name__} exceeded 5s")
        except Exception as e:
            self._logger.error(f"Handler error for {event_name}: {e}")
            self._logger.error(traceback.format_exc())
    
    async def fire_and_wait(self, event_name: str, data: Dict[str, Any], timeout: float = 5.0, source: str = "unknown") -> List[Any]:
        if not self._running:
            self._logger.warning(f"Event bus closed, dropping event {event_name}")
            return []
        
        event_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc)
        
        self._logger.debug(f"Firing event with wait {event_name} [{event_id}] from {source}")
        
        await self._store_event(event_id, event_name, data, source, timestamp)
        
        async_handlers = self._async_handlers.get(event_name, [])
        
        if not async_handlers:
            return []
        
        results = []
        
        for handler in async_handlers:
            try:
                result = await asyncio.wait_for(
                    handler(data, event_id=event_id),
                    timeout=timeout
                )
                results.append(result)
            except asyncio.TimeoutError:
                self._logger.error(f"Handler timeout for {event_name}: {handler.__name__} exceeded {timeout}s")
                results.append(None)
            except Exception as e:
                self._logger.error(f"Handler error for {event_name}: {e}")
                self._logger.error(traceback.format_exc())
                results.append(None)
        
        return results
    
    async def _store_event(self, event_id: str, event_name: str, data: Dict[str, Any], source: str, timestamp: datetime) -> None:
        async with self._lock:
            self._event_history.append({
                "id": event_id,
                "name": event_name,
                "data": data,
                "source": source,
                "timestamp": timestamp
            })
            
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
    
    async def get_events(self, event_name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        async with self._lock:
            if event_name:
                events = [e for e in self._event_history if e["name"] == event_name]
                return events[-limit:]
            
            return self._event_history[-limit:]
    
    async def clear_history(self) -> None:
        async with self._lock:
            self._event_history.clear()
            self._logger.info("Event history cleared")
    
    async def has_handlers(self, event_name: str) -> bool:
        async_handlers = self._async_handlers.get(event_name, [])
        sync_handlers = self._handlers.get(event_name, [])
        
        return len(async_handlers) > 0 or len(sync_handlers) > 0
    
    async def get_handler_count(self, event_name: str = None) -> Dict[str, int]:
        result = {}
        
        if event_name:
            result[event_name] = len(self._async_handlers.get(event_name, [])) + len(self._handlers.get(event_name, []))
        else:
            all_events = set(self._async_handlers.keys()) | set(self._handlers.keys())
            for event in all_events:
                result[event] = len(self._async_handlers.get(event, [])) + len(self._handlers.get(event, []))
        
        return result
    
    async def close(self) -> None:
        self._running = False
        
        pending_tasks = []
        for handlers in self._async_handlers.values():
            for handler in handlers:
                if hasattr(handler, "close"):
                    pending_tasks.append(handler.close())
        
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        
        self._logger.info("Event bus closed")