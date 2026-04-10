"""WebSocket 实时事件推送"""

from __future__ import annotations
import asyncio
import json
from dataclasses import asdict
from fastapi import WebSocket, WebSocketDisconnect
import structlog

logger = structlog.get_logger()


class EventBroadcaster:
    """事件广播器 — 将 ExecutionLogEntry 推送给 WebSocket 客户端"""

    def __init__(self) -> None:
        # run_id -> set of websockets
        self._connections: dict[str, set[WebSocket]] = {}
        # global connections (no run_id filter)
        self._global_connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket, run_id: str | None = None) -> None:
        await ws.accept()
        if run_id:
            self._connections.setdefault(run_id, set()).add(ws)
        else:
            self._global_connections.add(ws)
        logger.info("ws.connected", run_id=run_id)

    def disconnect(self, ws: WebSocket, run_id: str | None = None) -> None:
        if run_id and run_id in self._connections:
            self._connections[run_id].discard(ws)
            if not self._connections[run_id]:
                del self._connections[run_id]
        self._global_connections.discard(ws)
        logger.info("ws.disconnected", run_id=run_id)

    async def broadcast(self, run_id: str, event: dict) -> None:
        """广播事件到指定 run_id 的所有连接 + 全局连接"""
        message = json.dumps(event, ensure_ascii=False)
        targets = set(self._global_connections)
        if run_id in self._connections:
            targets |= self._connections[run_id]

        disconnected = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws, run_id)


# Global singleton
broadcaster = EventBroadcaster()
