"""
Aurora PostgreSQL client using RDS Data API
Supports serverless access without VPC networking
"""
import json
import logging
import os
from typing import Any, Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AuroraClient:
    """Client for Aurora PostgreSQL using RDS Data API"""

    def __init__(self):
        self.cluster_arn = os.environ.get("AURORA_CLUSTER_ARN", "")
        self.secret_arn = os.environ.get("AURORA_SECRET_ARN", "")
        self.database_name = os.environ.get("AURORA_DATABASE_NAME", "bedrockchat")
        self.enabled = os.environ.get("USE_AURORA_SEARCH", "false").lower() == "true"

        if self.enabled and (not self.cluster_arn or not self.secret_arn):
            logger.warning("Aurora enabled but credentials not configured")
            self.enabled = False

        if self.enabled:
            self.client = boto3.client("rds-data")
            logger.info(f"✅ Aurora client initialized: {self.database_name}")
        else:
            self.client = None
            logger.info("Aurora client disabled")

    def execute_statement(
        self,
        sql: str,
        parameters: Optional[list] = None,
        transaction_id: Optional[str] = None,
    ) -> dict:
        """Execute SQL statement using RDS Data API"""
        if not self.enabled or not self.client:
            raise RuntimeError("Aurora client not enabled")

        try:
            params = {
                "resourceArn": self.cluster_arn,
                "secretArn": self.secret_arn,
                "database": self.database_name,
                "sql": sql,
            }

            if parameters:
                params["parameters"] = parameters

            if transaction_id:
                params["transactionId"] = transaction_id

            response = self.client.execute_statement(**params)
            return response

        except ClientError as e:
            logger.error(f"Aurora execute_statement failed: {e}")
            raise

    def batch_execute_statement(
        self, sql: str, parameter_sets: list[list]
    ) -> dict:
        """Execute batch SQL statements"""
        if not self.enabled or not self.client:
            raise RuntimeError("Aurora client not enabled")

        try:
            response = self.client.batch_execute_statement(
                resourceArn=self.cluster_arn,
                secretArn=self.secret_arn,
                database=self.database_name,
                sql=sql,
                parameterSets=parameter_sets,
            )
            return response
        except ClientError as e:
            logger.error(f"Aurora batch_execute failed: {e}")
            raise

    def upsert_bot_vector(
        self,
        bot_id: str,
        title: str,
        description: str,
        instruction: str,
        owner_user_id: str,
        embedding: list[float],
        create_time: int,
        last_used_time: int,
        sync_status: str,
        shared_scope: str,
        is_pinned: bool,
        allowed_users: list[str],
    ):
        """Insert or update bot vector in Aurora"""
        if not self.enabled:
            return

        try:
            # Convert embedding to PostgreSQL array format
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            sql = """
            INSERT INTO bot_vectors (
                bot_id, title, description, instruction, owner_user_id,
                embedding, create_time, last_used_time, sync_status,
                shared_scope, is_pinned, allowed_users, updated_at
            ) VALUES (
                :bot_id, :title, :description, :instruction, :owner_user_id,
                :embedding::vector, :create_time, :last_used_time, :sync_status,
                :shared_scope, :is_pinned, :allowed_users, CURRENT_TIMESTAMP
            )
            ON CONFLICT (bot_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                instruction = EXCLUDED.instruction,
                embedding = EXCLUDED.embedding,
                last_used_time = EXCLUDED.last_used_time,
                sync_status = EXCLUDED.sync_status,
                shared_scope = EXCLUDED.shared_scope,
                is_pinned = EXCLUDED.is_pinned,
                allowed_users = EXCLUDED.allowed_users,
                updated_at = CURRENT_TIMESTAMP
            """

            parameters = [
                {"name": "bot_id", "value": {"stringValue": bot_id}},
                {"name": "title", "value": {"stringValue": title}},
                {"name": "description", "value": {"stringValue": description or ""}},
                {"name": "instruction", "value": {"stringValue": instruction or ""}},
                {"name": "owner_user_id", "value": {"stringValue": owner_user_id}},
                {"name": "embedding", "value": {"stringValue": embedding_str}},
                {"name": "create_time", "value": {"longValue": create_time}},
                {"name": "last_used_time", "value": {"longValue": last_used_time}},
                {"name": "sync_status", "value": {"stringValue": sync_status}},
                {"name": "shared_scope", "value": {"stringValue": shared_scope}},
                {"name": "is_pinned", "value": {"booleanValue": is_pinned}},
                {
                    "name": "allowed_users",
                    "value": {
                        "stringValue": "{" + ",".join(allowed_users) + "}"
                        if allowed_users
                        else "{}"
                    },
                },
            ]

            self.execute_statement(sql, parameters)
            logger.info(f"✅ Upserted bot {bot_id} to Aurora")

        except Exception as e:
            logger.error(f"Failed to upsert bot {bot_id}: {e}")
            raise

    def delete_bot_vector(self, bot_id: str):
        """Delete bot vector from Aurora"""
        if not self.enabled:
            return

        try:
            sql = "DELETE FROM bot_vectors WHERE bot_id = :bot_id"
            parameters = [{"name": "bot_id", "value": {"stringValue": bot_id}}]

            self.execute_statement(sql, parameters)
            logger.info(f"✅ Deleted bot {bot_id} from Aurora")

        except Exception as e:
            logger.error(f"Failed to delete bot {bot_id}: {e}")

    def upsert_conversation_vector(
        self,
        conversation_id: str,
        user_id: str,
        title: str,
        title_embedding: list[float],
        bot_id: Optional[str] = None,
        last_updated_time: Optional[int] = None,
        message_count: int = 0,
    ):
        """Insert or update conversation vector"""
        if not self.enabled:
            return

        try:
            embedding_str = "[" + ",".join(str(x) for x in title_embedding) + "]"

            sql = """
            INSERT INTO conversation_vectors (
                conversation_id, user_id, title, title_embedding,
                bot_id, last_updated_time, message_count, updated_at
            ) VALUES (
                :conversation_id, :user_id, :title, :title_embedding::vector,
                :bot_id, :last_updated_time, :message_count, CURRENT_TIMESTAMP
            )
            ON CONFLICT (conversation_id) DO UPDATE SET
                title = EXCLUDED.title,
                title_embedding = EXCLUDED.title_embedding,
                bot_id = EXCLUDED.bot_id,
                last_updated_time = EXCLUDED.last_updated_time,
                message_count = EXCLUDED.message_count,
                updated_at = CURRENT_TIMESTAMP
            """

            parameters = [
                {
                    "name": "conversation_id",
                    "value": {"stringValue": conversation_id},
                },
                {"name": "user_id", "value": {"stringValue": user_id}},
                {"name": "title", "value": {"stringValue": title}},
                {"name": "title_embedding", "value": {"stringValue": embedding_str}},
                {
                    "name": "bot_id",
                    "value": {"stringValue": bot_id} if bot_id else {"isNull": True},
                },
                {
                    "name": "last_updated_time",
                    "value": {"longValue": last_updated_time}
                    if last_updated_time
                    else {"isNull": True},
                },
                {"name": "message_count", "value": {"longValue": message_count}},
            ]

            self.execute_statement(sql, parameters)
            logger.info(f"✅ Upserted conversation {conversation_id} to Aurora")

        except Exception as e:
            logger.error(f"Failed to upsert conversation {conversation_id}: {e}")


# Global singleton
_aurora_client: Optional[AuroraClient] = None


def get_aurora_client() -> AuroraClient:
    """Get or create Aurora client singleton"""
    global _aurora_client
    if _aurora_client is None:
        _aurora_client = AuroraClient()
    return _aurora_client
