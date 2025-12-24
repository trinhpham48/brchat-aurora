"""
Conversation Search using Aurora PostgreSQL
Replaces OpenSearch for conversation search
"""
import logging
from typing import Optional
from app.repositories.aurora_client import get_aurora_client
from app.user import User

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_field_value(record: list, index: int, field_type: str, default=None):
    """Extract field value from RDS Data API response"""
    try:
        if index < len(record):
            field = record[index]
            if field_type in field and not field.get("isNull", False):
                return field[field_type]
        return default
    except (IndexError, KeyError):
        return default


def find_conversations_by_query_aurora(
    query: str, user: User, limit: int = 20
) -> list[dict]:
    """
    Search conversations using Aurora PostgreSQL Full-Text Search
    """
    aurora_client = get_aurora_client()

    if not aurora_client.enabled:
        logger.warning("Aurora not enabled for conversation search")
        return []

    try:
        cleaned_query = query.strip().replace("'", "''")
        tsquery = " & ".join(cleaned_query.split())

        sql = """
        SELECT 
            conversation_id,
            user_id,
            title,
            bot_id,
            last_updated_time,
            message_count,
            ts_rank(search_vector, to_tsquery('english', :tsquery)) as rank,
            similarity(title, :query) as sim
        FROM conversation_vectors
        WHERE user_id = :user_id
          AND (
              search_vector @@ to_tsquery('english', :tsquery)
              OR similarity(title, :query) > 0.2
              OR title ILIKE :like_query
          )
        ORDER BY 
            rank DESC,
            sim DESC,
            last_updated_time DESC
        LIMIT :limit
        """

        parameters = [
            {"name": "tsquery", "value": {"stringValue": tsquery}},
            {"name": "query", "value": {"stringValue": cleaned_query}},
            {"name": "user_id", "value": {"stringValue": user.id}},
            {
                "name": "like_query",
                "value": {"stringValue": f"%{cleaned_query}%"},
            },
            {"name": "limit", "value": {"longValue": limit}},
        ]

        response = aurora_client.execute_statement(sql, parameters)

        conversations = []
        for record in response.get("records", []):
            conv = {
                "id": _get_field_value(record, 0, "stringValue"),
                "title": _get_field_value(record, 2, "stringValue"),
                "bot_id": _get_field_value(record, 3, "stringValue"),
                "create_time": _get_field_value(record, 4, "longValue", 0),
                "message_count": _get_field_value(record, 5, "longValue", 0),
            }
            conversations.append(conv)

        logger.info(f"Found {len(conversations)} conversations for query: {query}")
        return conversations

    except Exception as e:
        logger.error(f"Aurora conversation search failed: {e}")
        return []


def sync_conversation_to_aurora(
    conversation_id: str,
    user_id: str,
    title: str,
    bot_id: Optional[str] = None,
    last_updated_time: Optional[int] = None,
    message_count: int = 0,
):
    """
    Sync conversation title to Aurora for search
    Called when conversation title is updated
    """
    aurora_client = get_aurora_client()

    if not aurora_client.enabled:
        logger.debug("Aurora not enabled, skipping conversation sync")
        return

    try:
        from app.bedrock import get_embedding

        title_embedding = get_embedding(title)

        aurora_client.upsert_conversation_vector(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
            title_embedding=title_embedding,
            bot_id=bot_id,
            last_updated_time=last_updated_time,
            message_count=message_count,
        )

        logger.info(f"✅ Synced conversation {conversation_id} to Aurora")

    except Exception as e:
        logger.error(f"Failed to sync conversation {conversation_id} to Aurora: {e}")
