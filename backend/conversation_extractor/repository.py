"""
Data Repositories - DynamoDB and Aurora
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

import boto3
from aws_lambda_powertools import Logger

logger = Logger(child=True)


class DynamoDBRepository:
    """Repository for DynamoDB conversation data"""
    
    def __init__(self, table_name: str):
        """
        Initialize DynamoDB repository
        
        Args:
            table_name: Name of the conversation table
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)
        logger.info(f"Initialized DynamoDB repository: {table_name}")
    
    def get_conversations_to_extract(
        self, min_idle_hours: int, max_idle_hours: int, limit: int = 200
    ) -> List[Dict]:
        """
        Get conversations that are idle for specified time range
        
        Args:
            min_idle_hours: Minimum idle time in hours
            max_idle_hours: Maximum idle time in hours
            limit: Maximum number of conversations to fetch
            
        Returns:
            List of conversation data
        """
        import time
        
        now = int(time.time())
        min_timestamp = now - (max_idle_hours * 3600)
        max_timestamp = now - (min_idle_hours * 3600)
        
        logger.info(
            f"Querying conversations with last_updated between "
            f"{datetime.fromtimestamp(min_timestamp)} and "
            f"{datetime.fromtimestamp(max_timestamp)}"
        )
        
        try:
            # Scan with filter (can be optimized with GSI in future)
            response = self.table.scan(
                # Filter conversations by update time
                # Note: This scans the table - for production, consider adding GSI
                Limit=limit,
            )
            
            conversations = []
            
            for item in response.get("Items", []):
                # Check if conversation is in the idle time range
                last_updated = self._get_last_updated_time(item)
                
                if min_timestamp <= last_updated <= max_timestamp:
                    conv_data = self._parse_conversation_item(item)
                    if conv_data:
                        conversations.append(conv_data)
                
                if len(conversations) >= limit:
                    break
            
            logger.info(f"Found {len(conversations)} conversations in time range")
            return conversations
            
        except Exception as e:
            logger.error(f"Error querying DynamoDB: {str(e)}")
            raise
    
    def _get_last_updated_time(self, item: Dict) -> int:
        """
        Extract last updated timestamp from item
        
        Args:
            item: DynamoDB item
            
        Returns:
            Timestamp (epoch)
        """
        # Try different possible timestamp fields
        if "last_message_time" in item:
            return int(item["last_message_time"])
        
        # Fallback to last message in message_map
        message_map = item.get("message_map", {})
        if message_map:
            max_time = 0
            for msg in message_map.values():
                create_time = msg.get("create_time", 0)
                if create_time > max_time:
                    max_time = create_time
            if max_time > 0:
                return int(max_time)
        
        # Fallback to create_time
        return int(item.get("create_time", 0))
    
    def _parse_conversation_item(self, item: Dict) -> Optional[Dict]:
        """
        Parse DynamoDB item to conversation data
        
        Args:
            item: DynamoDB item
            
        Returns:
            Parsed conversation data or None if invalid
        """
        try:
            # Extract IDs from PK/SK
            pk = item.get("PK", "")
            sk = item.get("SK", "")
            
            # PK format: "userId" or "userId#..."
            # SK format: "userId#CONV#conversationId" or similar
            
            user_id = pk.split("#")[0] if "#" in pk else pk
            
            # Extract conversation_id from SK
            if "#CONV#" in sk:
                conversation_id = sk.split("#CONV#")[-1]
            else:
                conversation_id = sk.split("#")[-1]
            
            return {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "messages": item.get("message_map", {}),
                "last_updated": self._get_last_updated_time(item),
                "create_time": item.get("create_time", 0),
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse item: {str(e)}")
            return None


class AuroraRepository:
    """Repository for Aurora PostgreSQL data"""
    
    def __init__(self, cluster_arn: str, secret_arn: str, database_name: str):
        """
        Initialize Aurora repository
        
        Args:
            cluster_arn: Aurora cluster ARN
            secret_arn: Secret ARN for database credentials
            database_name: Database name
        """
        self.cluster_arn = cluster_arn
        self.secret_arn = secret_arn
        self.database_name = database_name
        self.rds_client = boto3.client("rds-data")
        logger.info(f"Initialized Aurora repository: {database_name}")
    
    def is_extracted(self, conversation_id: str) -> bool:
        """
        Check if conversation is already extracted
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            True if already extracted
        """
        try:
            sql = """
            SELECT 1 
            FROM conversation_metadata 
            WHERE conversation_id = :conv_id 
            LIMIT 1
            """
            
            response = self.rds_client.execute_statement(
                resourceArn=self.cluster_arn,
                secretArn=self.secret_arn,
                database=self.database_name,
                sql=sql,
                parameters=[
                    {"name": "conv_id", "value": {"stringValue": conversation_id}}
                ],
            )
            
            return len(response.get("records", [])) > 0
            
        except Exception as e:
            logger.warning(f"Error checking extraction status: {str(e)}")
            return False
    
    def save_extraction(
        self,
        conversation_id: str,
        user_id: str,
        extracted_info: Dict,
        model_id: str,
    ) -> None:
        """
        Save extracted information to Aurora
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID
            extracted_info: Extracted fields
            model_id: Bedrock model ID used
        """
        try:
            sql = """
            INSERT INTO conversation_metadata (
                conversation_id,
                user_id,
                extracted_name,
                extracted_company,
                extracted_role,
                extracted_contact,
                main_topic,
                summary,
                model_id,
                extracted_at
            ) VALUES (
                :conv_id,
                :user_id,
                :name,
                :company,
                :role,
                :contact,
                :topic,
                :summary,
                :model_id,
                NOW()
            )
            ON CONFLICT (conversation_id) DO NOTHING
            """
            
            parameters = [
                {"name": "conv_id", "value": {"stringValue": conversation_id}},
                {"name": "user_id", "value": {"stringValue": user_id}},
                {
                    "name": "name",
                    "value": {"stringValue": extracted_info.get("name") or ""},
                },
                {
                    "name": "company",
                    "value": {"stringValue": extracted_info.get("company") or ""},
                },
                {
                    "name": "role",
                    "value": {"stringValue": extracted_info.get("role") or ""},
                },
                {
                    "name": "contact",
                    "value": {"stringValue": extracted_info.get("contact") or ""},
                },
                {
                    "name": "topic",
                    "value": {"stringValue": extracted_info.get("main_topic") or ""},
                },
                {
                    "name": "summary",
                    "value": {"stringValue": extracted_info.get("summary") or ""},
                },
                {"name": "model_id", "value": {"stringValue": model_id}},
            ]
            
            self.rds_client.execute_statement(
                resourceArn=self.cluster_arn,
                secretArn=self.secret_arn,
                database=self.database_name,
                sql=sql,
                parameters=parameters,
            )
            
            logger.info(f"Saved extraction for conversation: {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error saving to Aurora: {str(e)}")
            raise
