"""
Lock Manager Service for preventing concurrent requests with the same room_id and thread_id.

This service provides an in-memory locking mechanism using asyncio primitives to ensure
that only one chat streaming request can be processed at a time for a given room/thread combination.
"""

import asyncio
import logging
from typing import Dict, Set
from contextlib import asynccontextmanager
import time

logger = logging.getLogger(__name__)


class LockManager:
    """
    Manages locks for room_id and thread_id combinations to prevent concurrent processing.
    """
    
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._active_requests: Set[str] = set()
        self._lock_creation_lock = asyncio.Lock()
        
    def _get_lock_key(self, room_id: str, thread_id: str) -> str:
        """Generate a unique lock key from room_id and thread_id"""
        return f"{room_id}:{thread_id}"
    
    async def _get_lock(self, lock_key: str) -> asyncio.Lock:
        """
        Get or create a lock for the given key.
        Uses a separate lock to ensure thread-safe lock creation.
        """
        async with self._lock_creation_lock:
            if lock_key not in self._locks:
                self._locks[lock_key] = asyncio.Lock()
            return self._locks[lock_key]
    
    def is_locked(self, room_id: str, thread_id: str) -> bool:
        """
        Check if a room/thread combination is currently locked (non-blocking).
        
        Args:
            room_id: The room identifier
            thread_id: The thread identifier
            
        Returns:
            True if the combination is currently locked, False otherwise
        """
        lock_key = self._get_lock_key(room_id, thread_id)
        return lock_key in self._active_requests
    
    @asynccontextmanager
    async def acquire_lock(self, room_id: str, thread_id: str):
        """
        Async context manager to acquire a lock for a room/thread combination.
        
        Args:
            room_id: The room identifier
            thread_id: The thread identifier
            
        Raises:
            Exception: If the lock is already held by another request
            
        Usage:
            async with lock_manager.acquire_lock(room_id, thread_id):
                # Perform exclusive operations
                pass
        """
        lock_key = self._get_lock_key(room_id, thread_id)
        
        # Check if already locked (fast path)
        if lock_key in self._active_requests:
            raise ConflictException(f"Request already in progress for room {room_id}, thread {thread_id}")
        
        # Get the lock for this key
        lock = await self._get_lock(lock_key)
        
        # Try to acquire the lock with timeout to prevent indefinite waiting
        try:
            # Use wait_for with timeout to prevent hanging on acquire
            await asyncio.wait_for(lock.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            raise ConflictException(f"Request already in progress for room {room_id}, thread {thread_id}")
        
        # Mark as active
        self._active_requests.add(lock_key)
        start_time = time.time()
        
        logger.info(f"Acquired lock for {lock_key}")
        
        try:
            yield
        finally:
            # Always cleanup, even on exceptions
            self._active_requests.discard(lock_key)
            lock.release()
            
            duration = time.time() - start_time
            logger.info(f"Released lock for {lock_key} after {duration:.2f}s")
            
            # Clean up the lock from memory if no one is waiting
            # This prevents memory leaks for inactive rooms/threads
            async with self._lock_creation_lock:
                if lock_key in self._locks and not lock.locked():
                    # Check if anyone is waiting for this lock
                    if not hasattr(lock, '_waiters') or not lock._waiters:
                        del self._locks[lock_key]
                        logger.debug(f"Cleaned up unused lock for {lock_key}")
    
    def get_active_locks(self) -> Set[str]:
        """
        Get a copy of currently active lock keys for monitoring/debugging.
        
        Returns:
            Set of active lock keys in format "room_id:thread_id"
        """
        return self._active_requests.copy()
    
    def get_lock_count(self) -> int:
        """
        Get the total number of locks in memory.
        
        Returns:
            Number of locks currently in memory
        """
        return len(self._locks)


class ConflictException(Exception):
    """Exception raised when a lock conflict occurs"""
    pass


# Global instance
lock_manager = LockManager()