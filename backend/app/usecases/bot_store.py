import logging
import os

from app.repositories.bot_store import (
    find_bots_by_query,
    find_bots_sorted_by_usage_count,
    find_random_bots,
)
# Import Aurora-based search
from app.repositories.bot_store_aurora import (
    find_bots_by_query_aurora,
    find_public_bots_aurora,
)
from app.routes.schemas.bot import BotMetaOutput
from app.routes.schemas.bot_guardrails import BedrockGuardrailsOutput
from app.routes.schemas.bot_kb import BedrockKnowledgeBaseOutput
from app.user import User

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

USE_AURORA_SEARCH = os.environ.get("USE_AURORA_SEARCH", "false").lower() == "true"


def search_bots(
    user: User,
    query: str,
    limit: int = 20,
) -> list[BotMetaOutput]:
    """Search bots by query string."""
    if USE_AURORA_SEARCH:
        # Use Aurora PostgreSQL full-text search
        logger.info(f"Using Aurora search for query: {query}")
        bots = find_bots_by_query_aurora(query, user, limit=limit)
    else:
        # Fallback to OpenSearch
        logger.info(f"Using OpenSearch for query: {query}")
        bots = find_bots_by_query(query, user, limit=limit)
    
    bot_metas = []
    for bot in bots:
        bot_metas.append(bot.to_output())
    return bot_metas


def fetch_popular_bots(
    user: User,
    limit: int = 20,
) -> list[BotMetaOutput]:
    """Search bots sorted by usage count.
    This method is used for bot-store functionality (Popular bots).
    """
    if USE_AURORA_SEARCH:
        # Use Aurora to get public bots (Aurora doesn't have usage stats sorting yet)
        logger.info("Using Aurora for popular bots")
        bots = find_public_bots_aurora(limit=limit)
    else:
        bots = find_bots_sorted_by_usage_count(user, limit=limit)
    
    bot_metas = []
    for bot in bots:
        bot_metas.append(bot.to_output())
    return bot_metas


def fetch_pickup_bots(
    user: User,
    limit: int = 20,
) -> list[BotMetaOutput]:
    """Search bots sorted by usage count.
    This method is used for bot-store functionality (Today's pickup bots).
    """
    if USE_AURORA_SEARCH:
        # Use Aurora for pickup bots
        logger.info("Using Aurora for pickup bots")
        bots = find_public_bots_aurora(limit=limit, only_pinned=False)
    else:
        bots = find_random_bots(user, limit=limit)
    
    bot_metas = []
    for bot in bots:
        bot_metas.append(bot.to_output())
    return bot_metas
