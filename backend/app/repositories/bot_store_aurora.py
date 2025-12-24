"""
Bot Store repository using Aurora PostgreSQL
Replaces OpenSearch for bot search and discovery
"""
import logging
from typing import Optional
from app.repositories.models.custom_bot import BotMeta
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


def find_bots_by_query_aurora(
    query: str, user: User, limit: int = 20, similarity_threshold: float = 0.3
) -> list[BotMeta]:
    """
    Search bots using Aurora PostgreSQL Full-Text Search + Fuzzy Matching

    Features:
    - Full-text search with ranking (title > description > instruction)
    - Fuzzy matching with pg_trgm for typo tolerance
    - Access control (private, shared, public)
    - Multi-field search
    """
    aurora_client = get_aurora_client()

    if not aurora_client.enabled:
        logger.warning("Aurora not enabled, returning empty list")
        return []

    try:
        # Prepare search query for PostgreSQL
        cleaned_query = query.strip().replace("'", "''")
        tsquery = " & ".join(cleaned_query.split())

        # SQL with FTS + Fuzzy + Vector similarity
        sql = """
        WITH search_results AS (
            SELECT 
                bot_id,
                title,
                description,
                owner_user_id,
                create_time,
                last_used_time,
                sync_status,
                shared_scope,
                is_pinned,
                -- Ranking scores
                ts_rank(search_vector, to_tsquery('english', :tsquery)) as fts_rank,
                similarity(title, :query) as title_similarity,
                CASE 
                    WHEN shared_scope = 'PRIVATE' AND owner_user_id = :user_id THEN 100
                    WHEN shared_scope = 'PUBLIC' THEN 50
                    WHEN shared_scope = 'SHARED' AND :user_id = ANY(allowed_users) THEN 75
                    ELSE 0
                END as access_boost
            FROM bot_vectors
            WHERE 
                -- Access control
                (shared_scope = 'PUBLIC' 
                 OR (shared_scope = 'PRIVATE' AND owner_user_id = :user_id)
                 OR (shared_scope = 'SHARED' AND :user_id = ANY(allowed_users)))
                -- Search conditions
                AND (
                    search_vector @@ to_tsquery('english', :tsquery)
                    OR similarity(title, :query) > :threshold
                    OR title ILIKE :like_query
                    OR description ILIKE :like_query
                )
                AND sync_status = 'SUCCEEDED'
        )
        SELECT 
            bot_id,
            title,
            description,
            owner_user_id,
            create_time,
            last_used_time,
            sync_status,
            shared_scope,
            is_pinned,
            -- Combined ranking
            (fts_rank * 10 + title_similarity * 5 + access_boost) as final_rank
        FROM search_results
        ORDER BY 
            is_pinned DESC,
            final_rank DESC,
            last_used_time DESC
        LIMIT :limit
        """

        parameters = [
            {"name": "tsquery", "value": {"stringValue": tsquery}},
            {"name": "query", "value": {"stringValue": cleaned_query}},
            {"name": "user_id", "value": {"stringValue": user.id}},
            {"name": "threshold", "value": {"doubleValue": similarity_threshold}},
            {
                "name": "like_query",
                "value": {"stringValue": f"%{cleaned_query}%"},
            },
            {"name": "limit", "value": {"longValue": limit}},
        ]

        response = aurora_client.execute_statement(sql, parameters)

        # Parse results
        bots = []
        for record in response.get("records", []):
            bot = BotMeta(
                id=_get_field_value(record, 0, "stringValue"),
                title=_get_field_value(record, 1, "stringValue"),
                description=_get_field_value(record, 2, "stringValue", ""),
                create_time=_get_field_value(record, 4, "longValue", 0),
                last_used_time=_get_field_value(record, 5, "longValue", 0),
                is_pinned=_get_field_value(record, 8, "booleanValue", False),
                owned=_get_field_value(record, 3, "stringValue") == user.id,
                available=True,
                sync_status=_get_field_value(record, 6, "stringValue", "SUCCEEDED"),
            )
            bots.append(bot)

        logger.info(f"Found {len(bots)} bots for query: {query}")
        return bots

    except Exception as e:
        logger.error(f"Aurora bot search failed: {e}")
        return []


def find_public_bots_aurora(
    limit: int = 100, only_pinned: bool = False
) -> list[BotMeta]:
    """
    Find public bots (for Bot Store discovery page)
    """
    aurora_client = get_aurora_client()

    if not aurora_client.enabled:
        logger.warning("Aurora not enabled")
        return []

    try:
        sql = """
        SELECT 
            bot_id,
            title,
            description,
            owner_user_id,
            create_time,
            last_used_time,
            sync_status,
            is_pinned
        FROM bot_vectors
        WHERE shared_scope = 'PUBLIC'
          AND sync_status = 'SUCCEEDED'
        """

        if only_pinned:
            sql += " AND is_pinned = TRUE"

        sql += """
        ORDER BY 
            is_pinned DESC,
            last_used_time DESC
        LIMIT :limit
        """

        parameters = [{"name": "limit", "value": {"longValue": limit}}]

        response = aurora_client.execute_statement(sql, parameters)

        bots = []
        for record in response.get("records", []):
            bot = BotMeta(
                id=_get_field_value(record, 0, "stringValue"),
                title=_get_field_value(record, 1, "stringValue"),
                description=_get_field_value(record, 2, "stringValue", ""),
                create_time=_get_field_value(record, 4, "longValue", 0),
                last_used_time=_get_field_value(record, 5, "longValue", 0),
                is_pinned=_get_field_value(record, 7, "booleanValue", False),
                owned=False,
                available=True,
                sync_status=_get_field_value(record, 6, "stringValue", "SUCCEEDED"),
            )
            bots.append(bot)

        logger.info(f"Found {len(bots)} public bots")
        return bots

    except Exception as e:
        logger.error(f"Failed to fetch public bots: {e}")
        return []


def sync_bot_to_aurora(
    bot_id: str,
    title: str,
    description: str,
    instruction: str,
    owner_user_id: str,
    create_time: int,
    last_used_time: int,
    sync_status: str,
    is_public: bool,
    shared_bot_ids: Optional[list[str]] = None,
    is_pinned: bool = False,
):
    """
    Sync bot data to Aurora for search indexing
    Called after creating/updating a bot
    """
    aurora_client = get_aurora_client()

    if not aurora_client.enabled:
        logger.debug("Aurora not enabled, skipping bot sync")
        return

    try:
        # Generate embedding for search (using Bedrock)
        from app.bedrock import get_embedding

        text = f"{title} {description or ''} {instruction or ''}"
        embedding = get_embedding(text[:8000])  # Limit text length

        # Determine shared scope
        if is_public:
            shared_scope = "PUBLIC"
        elif shared_bot_ids:
            shared_scope = "SHARED"
        else:
            shared_scope = "PRIVATE"

        # Upsert to Aurora
        aurora_client.upsert_bot_vector(
            bot_id=bot_id,
            title=title,
            description=description or "",
            instruction=instruction or "",
            owner_user_id=owner_user_id,
            embedding=embedding,
            create_time=create_time,
            last_used_time=last_used_time,
            sync_status=sync_status,
            shared_scope=shared_scope,
            is_pinned=is_pinned,
            allowed_users=shared_bot_ids if shared_scope == "SHARED" else [],
        )

        logger.info(f"✅ Synced bot {bot_id} to Aurora")

    except Exception as e:
        logger.error(f"Failed to sync bot {bot_id} to Aurora: {e}")
        # Don't raise - this is a background operation


def delete_bot_from_aurora(bot_id: str):
    """Delete bot from Aurora search index"""
    aurora_client = get_aurora_client()

    if not aurora_client.enabled:
        return

    try:
        aurora_client.delete_bot_vector(bot_id)
        logger.info(f"✅ Deleted bot {bot_id} from Aurora")
    except Exception as e:
        logger.error(f"Failed to delete bot {bot_id} from Aurora: {e}")
