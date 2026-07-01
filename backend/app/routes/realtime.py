"""Real-time WebSocket management with Redis Pub/Sub for distributed broadcasting.

Uses Upstash serverless Redis to enable WebSocket messaging across multiple
server instances. Local WebSocket connections are stored in-memory, but
messages are published to Redis channels so all instances receive and relay them.

Architecture:
- Each server instance maintains a local dict of active WebSocket connections by room
- Messages are published to Redis channels, not directly to local connections
- Each instance subscribes to Redis channels for rooms with active clients
- A background listener task relays Redis messages to local connections
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from redis.asyncio.client import PubSub

from app.security import require_roles
from app.services.redis_service import get_redis_service
from app.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class RealTimeConnectionManager:
    """Manages WebSocket connections and Redis Pub/Sub for distributed messaging.

    Design:
    - `active_connections`: local storage of WebSocket connections by room
    - `subscriptions`: maps room -> PubSub object for Redis subscriptions
    - `listeners`: background tasks listening to Redis channels
    """

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.subscriptions: Dict[str, PubSub] = {}
        self.listeners: Dict[str, asyncio.Task] = {}
        self.redis_service = get_redis_service()

    async def connect(self, room: str, websocket: WebSocket) -> None:
        """Accept WebSocket connection and subscribe to Redis channel for the room."""
        await websocket.accept()

        # Add to local connections
        self.active_connections.setdefault(room, []).append(websocket)
        logger.info(f"Client connected to room: {room} (total: {len(self.active_connections[room])})")

        # Subscribe to Redis channel if not already subscribed
        if room not in self.subscriptions:
            try:
                pubsub = await self.redis_service.subscribe(f"room:{room}")
                self.subscriptions[room] = pubsub

                # Start background listener for this room
                listener_task = asyncio.create_task(self._listen_redis_channel(room, pubsub))
                self.listeners[room] = listener_task
                logger.info(f"Subscribed to Redis channel: room:{room}")
            except Exception as e:
                logger.error(f"Failed to subscribe to Redis for room {room}: {e}")

    def disconnect(self, room: str, websocket: WebSocket) -> None:
        """Remove WebSocket connection; clean up room if empty."""
        conns = self.active_connections.get(room, [])
        if websocket in conns:
            conns.remove(websocket)
            logger.info(f"Client disconnected from room: {room} (remaining: {len(conns)})")

        # If room is empty, unsubscribe from Redis and stop listener
        if not conns and room in self.active_connections:
            self.active_connections.pop(room, None)

            # Unsubscribe and close Redis PubSub
            if room in self.subscriptions:
                pubsub = self.subscriptions.pop(room)
                try:
                    asyncio.create_task(self.redis_service.unsubscribe(pubsub, f"room:{room}"))
                    asyncio.create_task(self.redis_service.close_pubsub(pubsub))
                except Exception as e:
                    logger.error(f"Error unsubscribing from room {room}: {e}")

            # Cancel listener task
            if room in self.listeners:
                listener_task = self.listeners.pop(room)
                listener_task.cancel()
                logger.info(f"Unsubscribed from Redis channel: room:{room}")

    async def broadcast_via_redis(self, room: str, message: dict) -> None:
        """Publish a message to the Redis channel for a room.

        All server instances subscribed to this room will receive and relay
        the message to their local WebSocket connections.
        """
        try:
            channel = f"room:{room}"
            message_json = json.dumps(message)
            subscribers = await self.redis_service.publish(channel, message_json)
            logger.debug(f"Published to {channel}: {subscribers} subscribers")
        except Exception as e:
            logger.error(f"Failed to broadcast to room {room}: {e}")

    async def _listen_redis_channel(self, room: str, pubsub: PubSub) -> None:
        """Background task: listen to Redis channel and relay messages to local connections.

        Hardened against dropped Redis connections (Upstash serverless idle
        timeout, network blips). If the subscription dies, it auto-resubscribes
        with backoff instead of silently leaving the room without a listener
        until a fresh client happens to connect.
        """
        channel = f"room:{room}"
        current_pubsub = pubsub
        attempt = 0

        while True:
            try:
                async for message in current_pubsub.listen():
                    if message.get("type") == "message":
                        # Decode JSON and relay to all local WebSocket connections
                        try:
                            payload = json.loads(message["data"])
                            await self._send_to_local_connections(room, payload)
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON from Redis channel {channel}: {e}")
                        except Exception as e:
                            logger.error(f"Error relaying message in {channel}: {e}")
                # A healthy subscription never returns normally, but if it does
                # (e.g. channel closed), break out and let cleanup happen.
                break

            except asyncio.CancelledError:
                # Task cancelled on room cleanup — exit cleanly.
                raise

            except Exception as e:
                logger.warning(
                    f"Redis listener for {channel} dropped (attempt {attempt + 1}): {e}"
                )
                attempt += 1

                # Close the dead pubsub if possible, then re-create a fresh
                # subscription so the room keeps receiving broadcasts.
                try:
                    await self.redis_service.close_pubsub(current_pubsub)
                except Exception:
                    pass

                try:
                    new_pubsub = await self.redis_service.subscribe(channel)
                    # Re-point the manager's tracked pubsub; keeping an entry here
                    # also prevents a concurrent connect() from spawning a
                    # duplicate listener while we retry.
                    self.subscriptions[room] = new_pubsub
                    current_pubsub = new_pubsub
                    logger.info(f"Re-subscribed Redis channel {channel} after drop")
                    attempt = 0
                except Exception as sub_err:
                    # Redis still unavailable — back off before retrying so we
                    # don't hot-loop against an unreachable server.
                    backoff = min(2 ** attempt, 30)
                    logger.warning(
                        f"Redis re-subscribe for {channel} failed, retrying in {backoff}s: {sub_err}"
                    )
                    try:
                        await asyncio.sleep(backoff)
                    except asyncio.CancelledError:
                        raise

    async def broadcast(self, room: str, message: dict) -> None:
        """Deliver a message to a room's clients.

        Sends directly to locally-connected clients (works even without Redis,
        e.g. in local dev) AND publishes to Redis so other server instances relay
        it to their own clients. Clients treat these as idempotent refresh signals,
        so an occasional duplicate on the same instance is harmless.
        """
        try:
            await self._send_to_local_connections(room, message)
        except Exception as e:
            logger.debug(f"Local broadcast to {room} failed: {e}")
        await self.broadcast_via_redis(room, message)

    async def broadcast(self, room: str, message: dict) -> None:
        """Deliver a message to a room's clients.

        Sends directly to locally-connected clients (works even without Redis,
        e.g. in local dev) AND publishes to Redis so other server instances relay
        it to their own clients. Clients treat these as idempotent refresh signals,
        so an occasional duplicate on the same instance is harmless.
        """
        try:
            await self._send_to_local_connections(room, message)
        except Exception as e:
            logger.debug(f"Local broadcast to {room} failed: {e}")
        await self.broadcast_via_redis(room, message)

    async def _send_to_local_connections(self, room: str, message: dict) -> None:
        """Send a message to all local WebSocket connections in a room."""
        conns = list(self.active_connections.get(room, []))
        dead_connections = []

        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket in {room}: {e}")
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(room, ws)


# Global manager instance
manager = RealTimeConnectionManager()


async def notify_queue_update(
    hospital_id: Optional[str],
    doctor_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Broadcast a 'queue changed' signal to everyone affected by a queue change.

    Broadcasts to two rooms so all three portals stay in sync in real time:
      - ``hospital_<id>``  → doctor dashboard + reception board
      - ``doctor_<id>``    → the doctor's patients (patient portal my-token page)

    e.g. a doctor skipping a patient immediately updates the reception board AND
    the affected patient's token number in their own portal.
    """
    payload = {"type": "QUEUE_UPDATE"}
    if extra:
        payload.update(extra)

    rooms = []
    if hospital_id:
        rooms.append(f"hospital_{hospital_id}")
    if doctor_id:
        rooms.append(f"doctor_{doctor_id}")

    for room in rooms:
        try:
            await manager.broadcast(room, payload)
        except Exception as e:
            logger.error(f"notify_queue_update failed for room {room}: {e}")


@router.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    """WebSocket endpoint for real-time messaging in a room.

    Flow:
    1. Accept connection and subscribe to Redis channel
    2. Run a server-side ping task so idle connections survive load-balancer
       idle timeouts (AWS ALB ~60s, API Gateway ~10min)
    3. Listen to WebSocket for incoming messages
    4. Forward each message to Redis Pub/Sub (distributed)
    5. Disconnect and unsubscribe when client disconnects
    """
    await manager.connect(room, websocket)

    # Server-initiated pings keep the socket "active" from the server side so
    # intermediaries (ALB idle timeout, NAT, Upstash) don't kill an idle
    # connection. Client also replies with a pong (see RealtimeService).
    PING_INTERVAL_SECONDS = 25

    async def _ping_loop() -> None:
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL_SECONDS)
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    # Socket already gone — let the receive loop handle cleanup.
                    break
        except asyncio.CancelledError:
            # Task cancelled on disconnect; nothing to do.
            pass

    ping_task = asyncio.create_task(_ping_loop())

    try:
        while True:
            # Wait for client message
            data = await websocket.receive_text()

            # Parse and forward to Redis
            try:
                message = json.loads(data) if isinstance(data, str) else data
                # Enrich with type if not present
                if "type" not in message:
                    message["type"] = "message"

                # Client ping/pong frames are just keep-alive chatter — don't
                # relay them to the rest of the room (they already count as
                # traffic in the client->server direction for idle timeouts).
                if message.get("type") in ("ping", "pong"):
                    continue

                # Publish to Redis so all instances can relay
                await manager.broadcast_via_redis(room, message)
            except json.JSONDecodeError:
                # Send raw echo ACK if not JSON
                await websocket.send_json({"type": "ack"})
            except Exception as e:
                logger.error(f"Error processing WebSocket message in {room}: {e}")
                await websocket.send_json({"type": "error", "detail": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(room, websocket)
    except Exception as e:
        logger.error(f"WebSocket error in room {room}: {e}")
        manager.disconnect(room, websocket)
    finally:
        # Always stop the ping task when the connection ends.
        ping_task.cancel()
        try:
            await ping_task
        except (asyncio.CancelledError, Exception):
            pass


@router.post("/notify/{room}")
async def notify_room(
    room: str,
    payload: dict,
    _=Depends(require_roles("doctor", "receptionist", "admin"))
):
    """Publish a notification to a room via Redis Pub/Sub.

    Accessible only to authenticated staff. The message is published to
    Redis so all server instances relaying connections in this room
    will deliver it to their local clients.
    """
    try:
        message = {
            "type": "notification",
            "data": payload
        }
        await manager.broadcast_via_redis(room, message)
        return {"success": True, "message": f"Notification sent to room: {room}"}
    except Exception as e:
        logger.error(f"Failed to notify room {room}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to notify room: {str(e)}"
        )
