"""Azure Functions v2 — timer ingestion + queue processing."""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func

app = func.FunctionApp()
logger = logging.getLogger(__name__)

QUEUE_NAME = os.getenv("EMAIL_PROCESSING_QUEUE", "email-processing")


@app.function_name(name="EmailIngestionTimer")
@app.timer_trigger(schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False)
def email_ingestion_timer(timer: func.TimerRequest) -> None:
    """Pull recent Graph messages and enqueue IDs for processing."""
    from app.graph_client import get_email_backend
    from app.ingestion import load_recent_emails

    backend = get_email_backend(os.getenv("EMAIL_BACKEND", "graph"))
    emails = load_recent_emails(backend, top=int(os.getenv("INGEST_TOP", "25")))

    from azure.storage.queue import QueueClient

    conn = os.environ["AzureWebJobsStorage"]
    queue = QueueClient.from_connection_string(conn, QUEUE_NAME)
    try:
        queue.create_queue()
    except Exception:
        pass

    for email in emails:
        payload = json.dumps({"message_id": email.message_id})
        queue.send_message(payload)
        logger.info("Enqueued %s", email.message_id)

    logger.info("Ingestion complete: %d messages", len(emails))


@app.function_name(name="EmailProcessor")
@app.queue_trigger(
    arg_name="msg",
    queue_name=QUEUE_NAME,
    connection="AzureWebJobsStorage",
)
def email_processor(msg: func.QueueMessage) -> None:
    """Process a single email from the queue."""
    from app.action_router import ActionRouter
    from app.classifier import classify_email, get_classifier
    from app.entity_matcher import match_entities
    from app.graph_client import get_email_backend
    from app.obsidian_writer import ObsidianWriter
    from app.responder import draft_response, get_responder
    from app.schemas import NormalizedEmail

    data = json.loads(msg.get_body().decode("utf-8"))
    message_id = data["message_id"]

    backend = get_email_backend(os.getenv("EMAIL_BACKEND", "graph"))
    emails = backend.list_recent_messages(top=100)
    email = next((e for e in emails if e.message_id == message_id), None)
    if not email:
        logger.warning("Message not found: %s", message_id)
        return

    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "")
    writer = ObsidianWriter(vault_path) if vault_path else None

    entity_match = match_entities(email)
    classification = classify_email(email, entity_match, get_classifier())
    draft = draft_response(email, classification, get_responder())
    router = ActionRouter(writer=writer, backend=backend)
    action = router.route(email, classification, draft)

    _persist_metadata(email, classification, action)
    logger.info("Processed %s -> %s", message_id, classification.category)


def _persist_metadata(email, classification, action) -> None:
    """Optional: write to Azure Table Storage."""
    conn = os.getenv("AzureWebJobsStorage")
    table_name = os.getenv("EMAIL_METADATA_TABLE", "emailmetadata")
    if not conn:
        return
    try:
        from azure.data.tables import TableClient

        table = TableClient.from_connection_string(conn, table_name)
        try:
            table.create_table()
        except Exception:
            pass
        entity = {
            "PartitionKey": email.received_at[:10] if email.received_at else "unknown",
            "RowKey": email.message_id.replace("/", "_"),
            "subject": email.subject,
            "category": classification.category,
            "priority": classification.priority,
            "sender": email.sender_email,
        }
        table.upsert_entity(entity)
    except Exception as e:
        logger.warning("Table persist skipped: %s", e)
