#!/usr/bin/env python3
"""
One-time migration script: Sync existing DynamoDB bots to Aurora
Run after deploying Aurora infrastructure

Usage:
    cd backend
    poetry run python scripts/sync_existing_data_to_aurora.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from app.repositories.custom_bot import find_all_bots_by_user_id
from app.repositories.bot_store_aurora import sync_bot_to_aurora
from app.repositories.common import get_bot_table_client
from boto3.dynamodb.conditions import Key

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def scan_all_users():
    """Scan DynamoDB to get all unique user IDs"""
    table = get_bot_table_client()
    users = set()

    logger.info("Scanning for all users...")
    response = table.scan(ProjectionExpression="PK")

    for item in response.get("Items", []):
        users.add(item["PK"])

    while "LastEvaluatedKey" in response:
        response = table.scan(
            ProjectionExpression="PK", ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        for item in response.get("Items", []):
            users.add(item["PK"])

    logger.info(f"Found {len(users)} unique users")
    return list(users)


def migrate_user_bots(user_id: str):
    """Migrate all bots for a specific user"""
    try:
        bots = find_all_bots_by_user_id(user_id)
        migrated = 0

        for bot in bots:
            try:
                sync_bot_to_aurora(
                    bot_id=bot.id,
                    title=bot.title,
                    description=bot.description or "",
                    instruction=bot.instruction or "",
                    owner_user_id=bot.owner_user_id,
                    create_time=bot.create_time,
                    last_used_time=bot.last_used_time or bot.create_time,
                    sync_status=bot.sync_status,
                    is_public=bot.is_public,
                    shared_bot_ids=bot.shared_bot_ids,
                    is_pinned=bot.is_pinned,
                )
                migrated += 1
                logger.info(f"  ✅ Migrated bot: {bot.id} - {bot.title}")
            except Exception as e:
                logger.error(f"  ❌ Failed to migrate bot {bot.id}: {e}")

        logger.info(f"User {user_id}: Migrated {migrated}/{len(bots)} bots")
        return migrated

    except Exception as e:
        logger.error(f"Failed to process user {user_id}: {e}")
        return 0


def main():
    """Main migration function"""
    logger.info("🚀 Starting Aurora migration...")
    logger.info("=" * 60)

    # Get all users
    users = scan_all_users()

    total_migrated = 0
    total_failed = 0

    for idx, user_id in enumerate(users, 1):
        logger.info(f"\n[{idx}/{len(users)}] Processing user: {user_id}")
        try:
            migrated = migrate_user_bots(user_id)
            total_migrated += migrated
        except Exception as e:
            logger.error(f"Failed to process user {user_id}: {e}")
            total_failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Migration complete!")
    logger.info(f"   Total bots migrated: {total_migrated}")
    logger.info(f"   Users processed: {len(users) - total_failed}/{len(users)}")
    logger.info(f"   Failed users: {total_failed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Verify Aurora is enabled
    if os.environ.get("USE_AURORA_SEARCH", "false").lower() != "true":
        logger.warning("⚠️  USE_AURORA_SEARCH is not enabled!")
        logger.warning("   Set USE_AURORA_SEARCH=true in environment")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != "y":
            logger.info("Migration cancelled")
            sys.exit(0)

    main()
