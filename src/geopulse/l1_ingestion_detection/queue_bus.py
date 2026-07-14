"""Step 7 — Queue bus: the seam between Person 1 and Person 2.

Azure Functions queue triggers expect Base64-encoded message bodies, so we
encode on publish. Includes poison handling for the consumer side and a
local mode that works against Azurite (settings default).

Phase 3 swaps this class for an Event Hubs implementation with the same
three methods; nothing else changes.
"""

from __future__ import annotations

import base64
import logging

from azure.storage.queue import QueueClient

from .models import AnomalySignal
from .settings import Settings

logger = logging.getLogger("geopulse.queue")

MAX_DEQUEUE_BEFORE_POISON = 5


class QueueBus:
    def __init__(self, settings: Settings):
        self.queue = QueueClient.from_connection_string(
            settings.storage_connection_string, settings.anomaly_queue_name)
        self.poison = QueueClient.from_connection_string(
            settings.storage_connection_string,
            f"{settings.anomaly_queue_name}-poison")
        for q in (self.queue, self.poison):
            try:
                q.create_queue()
            except Exception:
                pass                        # already exists

    def publish_anomaly(self, signal: AnomalySignal) -> None:
        body = base64.b64encode(signal.model_dump_json().encode()).decode()
        self.queue.send_message(body)
        logger.info("published signal %s (theme=%s)", signal.id, signal.theme)

    def receive(self) -> tuple[AnomalySignal, object] | None:
        """Manual consumption (dev loop / non-Functions consumers).
        Returns (signal, raw_message) — call complete(raw_message) when done."""
        msgs = self.queue.receive_messages(messages_per_page=1)
        for msg in msgs:
            if msg.dequeue_count > MAX_DEQUEUE_BEFORE_POISON:
                self.poison.send_message(msg.content)
                self.queue.delete_message(msg)
                logger.error("moved poison message to poison queue")
                continue
            raw = base64.b64decode(msg.content).decode()
            return AnomalySignal.model_validate_json(raw), msg
        return None

    def complete(self, raw_message) -> None:
        self.queue.delete_message(raw_message)
