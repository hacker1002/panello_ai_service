"""
Lock Manager Service for thread locking using database locks.

This service provides database-based locking to prevent concurrent processing
of the same thread across multiple services and instances.
"""

import logging
from typing import Optional
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)


class LockManager:
    """
    Manages thread locks using Supabase database for distributed lock coordination.
    """
    
    def __init__(self):
        # Initialize Supabase client for database locks
        self.db_client = supabase_client
    
    def check_thread_lock(self, thread_id: str) -> Optional[dict]:
        """
        Check if thread has an active lock in the database.
        
        Args:
            thread_id: The thread identifier
            
        Returns:
            Lock info dict with is_locked, lock_type, expires_in_seconds, etc.
            Returns None if error occurs
        """
        try:
            response = self.db_client.rpc('get_thread_lock_status', {
                'p_thread_id': thread_id
            }).execute()
            
            if response.data:
                return response.data
            return {'is_locked': False}
        except Exception as e:
            logger.error(f"Error checking database lock for thread {thread_id}: {e}")
            return None
    
    def transition_to_ai_lock(self, thread_id: str, ai_id: str, ttl_seconds: int = 120) -> Optional[dict]:
        """
        Transition existing lock to AI or create new AI lock.
        
        Args:
            thread_id: The thread identifier
            ai_id: The AI identifier
            ttl_seconds: Lock time-to-live in seconds (default 120)
            
        Returns:
            Dict with success=True and lock details if successful, None otherwise
        """
        try:
            response = self.db_client.rpc('transition_lock_to_ai', {
                'p_thread_id': thread_id,
                'p_ai_id': ai_id,
                'p_ttl_seconds': ttl_seconds
            }).execute()
            
            if response.data:
                logger.info(f"Successfully transitioned/acquired AI lock for thread {thread_id}")
                return response.data
            return None
        except Exception as e:
            logger.error(f"Error transitioning to AI lock for thread {thread_id}: {e}")
            return None
    
    def release_thread_lock(self, thread_id: str, profile_id: str) -> bool:
        """
        Release the thread lock.
        
        Args:
            thread_id: The thread identifier
            profile_id: The profile/AI identifier holding the lock
            
        Returns:
            True if lock was released, False otherwise
        """
        try:
            response = self.db_client.rpc('release_thread_lock', {
                'p_thread_id': thread_id,
                'p_profile_id': profile_id
            }).execute()
            
            if response.data:
                logger.info(f"Successfully released thread lock for thread {thread_id}")
                return True
            else:
                logger.warning(f"No thread lock found to release for thread {thread_id}")
                return False
        except Exception as e:
            logger.error(f"Error releasing thread lock for thread {thread_id}: {e}")
            return False
    
    def refresh_thread_lock(self, thread_id: str, profile_id: str, extend_seconds: int = 30) -> bool:
        """
        Refresh/extend an existing thread lock.
        
        Args:
            thread_id: The thread identifier
            profile_id: The profile/AI identifier holding the lock
            extend_seconds: Number of seconds to extend the lock
            
        Returns:
            True if lock was refreshed, False otherwise
        """
        try:
            response = self.db_client.rpc('refresh_thread_lock', {
                'p_thread_id': thread_id,
                'p_profile_id': profile_id,
                'p_extend_seconds': extend_seconds
            }).execute()
            
            if response.data:
                logger.info(f"Successfully refreshed thread lock for thread {thread_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error refreshing thread lock for thread {thread_id}: {e}")
            return False


# Global instance
lock_manager = LockManager()