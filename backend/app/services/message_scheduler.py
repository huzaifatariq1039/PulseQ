from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from arq import create_pool
import redis.asyncio as redis
from app.config import REDIS_URL
from app.logger import get_logger

logger = get_logger(__name__)

# ✅ Global Redis client for message deduplication
_redis_client: Optional[redis.Redis] = None

async def _get_redis_client() -> redis.Redis:
    """Get or create Redis client for message deduplication."""
    global _redis_client
    if _redis_client is None:
        _redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client

async def _get_arq_pool():
    """Get or create arq connection pool."""
    return await create_pool(REDIS_URL)

def _to_dt(v: Any) -> Optional[datetime]:
    """Convert various datetime formats to datetime object."""
    try:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        to_dt = getattr(v, "to_datetime", None)
        if callable(to_dt):
            return to_dt()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


# ✅ MESSAGE DEDUPLICATION HELPER
async def _is_message_already_sent(phone: str, template_name: str) -> bool:
    """Check if message was already sent (Redis cache)."""
    try:
        redis_client = await _get_redis_client()
        # Key format: message:phone:template_name
        message_key = f"message:{phone}:{template_name}"
        result = await redis_client.get(message_key)
        return result is not None
    except Exception as e:
        logger.error(f"Failed to check message cache: {e}")
        return False


async def _mark_message_sent(phone: str, template_name: str, ttl_seconds: int = 86400) -> None:
    """Mark message as sent in Redis (24 hour TTL by default)."""
    try:
        redis_client = await _get_redis_client()
        message_key = f"message:{phone}:{template_name}"
        # Set with TTL (86400 seconds = 24 hours)
        await redis_client.setex(message_key, ttl_seconds, "sent")
        logger.info(f"Marked message as sent: {message_key}")
    except Exception as e:
        logger.error(f"Failed to mark message as sent: {e}")


async def schedule_at(
    run_at: datetime,
    template_name: str,
    token_context: Dict[str, Any],
    params: List[str],
) -> None:
    """Enqueue a message to be sent at a specific time via arq.
    
    ✅ Now checks Redis cache before enqueueing to prevent duplicates.
    """
    try:
        # ✅ CHECK IF MESSAGE ALREADY SENT
        patient_phone = token_context.get("patient_phone", "")
        if await _is_message_already_sent(patient_phone, template_name):
            logger.info(f"Message already sent, skipping: {template_name} to {patient_phone}")
            return
        
        now = datetime.now(timezone.utc)
        run_at_utc = run_at
        try:
            if run_at_utc.tzinfo is None:
                run_at_utc = run_at_utc.replace(tzinfo=timezone.utc)
            else:
                run_at_utc = run_at_utc.astimezone(timezone.utc)
        except Exception:
            run_at_utc = now
        
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "send_message_delayed",
            token_context,
            template_name,
            params,
            _defer_until=run_at_utc,
        )
        logger.debug(f"Enqueued job {job.id}: {template_name} at {run_at_utc}")
        
        # ✅ MARK MESSAGE AS SENT IN REDIS
        await _mark_message_sent(patient_phone, template_name)
        
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue message job: {e}")
        raise


async def schedule_messages(token: Dict[str, Any], is_webhook_trigger: bool = False) -> None:
    """Enqueue reminder-message orchestration job for a token.
    
    ✅ Now uses Redis deduplication to prevent duplicate messages between 
       webhook and scheduler paths.
    
    Args:
        token: Token dictionary with patient info
        is_webhook_trigger: True if called from webhook (patient replied YES)
                           False if called from normal token creation
    """
    try:
        # ✅ CHECK IF MESSAGES ALREADY SCHEDULED
        patient_phone = token.get("patient_phone", "")
        token_id = token.get("id", "")
        
        # Check for key messages that indicate scheduling already happened
        key_message = "queue_update_alert"
        if await _is_message_already_sent(patient_phone, key_message):
            logger.info(f"Messages already scheduled for token {token_id}, skipping")
            return
        
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "schedule_messages_job",
            token,
            is_webhook_trigger,
        )
        logger.info(f"Enqueued schedule_messages_job: {job.id}")
        
        # ✅ MARK KEY MESSAGE AS SENT TO PREVENT DUPLICATES
        await _mark_message_sent(patient_phone, key_message)
        
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue schedule_messages_job: {e}")
        raise


async def schedule_confirmation_checks(
    token_id: str,
    first_delay_minutes: int = 15,
    second_delay_minutes: int = 15,
) -> None:
    """Enqueue confirmation check job via arq."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "check_confirmation_job",
            token_id,
            first_delay_minutes,
            second_delay_minutes,
        )
        logger.info(f"Enqueued check_confirmation_job: {job.id} for token {token_id}")
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue check_confirmation_job: {e}")
        raise


async def schedule_skip_messages(token_id: str) -> None:
    """Enqueue skip notification job via arq."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "schedule_skip_message_job",
            token_id,
        )
        logger.info(f"Enqueued schedule_skip_message_job: {job.id} for token {token_id}")
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue schedule_skip_message_job: {e}")
        raise


# ✅ CLEANUP FUNCTION - Call this when app shuts down
async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None