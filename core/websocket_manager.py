"""
WebSocket manager for real-time broadcasting.
"""

import logging

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # If sending fails, we'll clean up later or ignore for now
                logging.getLogger(__name__).debug(
                    "Operation failed; applying fallback", exc_info=True
                )


manager = ConnectionManager()
