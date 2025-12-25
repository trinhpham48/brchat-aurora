"""
Lambda Handler: Conversation Information Extractor

Trigger: EventBridge Schedule (every 8 hours)
Purpose: Extract name, company, role, contact info from conversations
Flow: DynamoDB → Bedrock → Aurora PostgreSQL
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import boto3

from extractor import ConversationExtractor
from repository import AuroraRepository, DynamoDBRepository

# Initialize logging
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
CONVERSATION_TABLE_NAME = os.environ.get("CONVERSATION_TABLE_NAME", "")
AURORA_CLUSTER_ARN = os.environ.get("AURORA_CLUSTER_ARN", "")
AURORA_SECRET_ARN = os.environ.get("AURORA_SECRET_ARN", "")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "bedrock_chat")
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
)

# Idle time configuration (8 hours)
MIN_IDLE_HOURS = 8
MAX_IDLE_HOURS = 16
BATCH_SIZE = 200


def handler(event: Dict, context) -> Dict:
    """
    Main Lambda handler - Extract conversation information
    
    Schedule: Every 8 hours (00:00, 08:00, 16:00)
    
    Args:
        event: EventBridge scheduled event
        context: Lambda context
        
    Returns:
        Response with processing statistics
    """
    logger.info("Starting conversation extraction job")
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        # Initialize repositories
        dynamodb_repo = DynamoDBRepository(CONVERSATION_TABLE_NAME)
        aurora_repo = AuroraRepository(
            AURORA_CLUSTER_ARN, AURORA_SECRET_ARN, DATABASE_NAME
        )
        extractor = ConversationExtractor(BEDROCK_MODEL_ID)
        
        # Get conversations to process (idle between 8-16 hours)
        logger.info(
            f"Fetching conversations idle between {MIN_IDLE_HOURS}-{MAX_IDLE_HOURS} hours"
        )
        conversations = dynamodb_repo.get_conversations_to_extract(
            min_idle_hours=MIN_IDLE_HOURS,
            max_idle_hours=MAX_IDLE_HOURS,
            limit=BATCH_SIZE,
        )
        
        logger.info(f"Found {len(conversations)} conversations to process")
        
        if not conversations:
            logger.info("No conversations to process")
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "No conversations to process",
                        "processed": 0,
                        "errors": 0,
                        "skipped": 0,
                    }
                ),
            }
        
        # Process conversations
        processed = 0
        errors = 0
        skipped = 0
        
        for conv in conversations:
            conversation_id = conv["conversation_id"]
            user_id = conv["user_id"]
            
            try:
                # Check if already extracted
                if aurora_repo.is_extracted(conversation_id):
                    logger.info(f"Skipping already extracted: {conversation_id}")
                    skipped += 1
                    continue
                
                # Validate conversation
                if not _validate_conversation(conv):
                    logger.warning(f"Invalid conversation: {conversation_id}")
                    skipped += 1
                    continue
                
                # Extract information using Bedrock
                logger.info(f"Extracting info from: {conversation_id}")
                extracted_info = extractor.extract(conv["messages"])
                
                # Save to Aurora
                aurora_repo.save_extraction(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    extracted_info=extracted_info,
                    model_id=BEDROCK_MODEL_ID,
                )
                
                processed += 1
                logger.info(f"✅ Successfully processed: {conversation_id}")
                
            except Exception as e:
                errors += 1
                logger.error(
                    f"❌ Error processing {conversation_id}: {str(e)}",
                    exc_info=True,
                )
        
        # Summary
        summary = {
            "processed": processed,
            "errors": errors,
            "skipped": skipped,
            "total": len(conversations),
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Extraction job completed: {json.dumps(summary)}")
        
        return {"statusCode": 200, "body": json.dumps(summary)}
        
    except Exception as e:
        logger.error(f"Fatal error in extraction job: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def _validate_conversation(conversation: Dict) -> bool:
    """
    Validate conversation before processing
    
    Args:
        conversation: Conversation data
        
    Returns:
        True if valid, False otherwise
    """
    # Must have messages
    messages = conversation.get("messages", {})
    if not messages or len(messages) < 5:
        logger.warning(
            f"Conversation {conversation['conversation_id']} has too few messages"
        )
        return False
    
    # Must have conversation_id and user_id
    if not conversation.get("conversation_id") or not conversation.get("user_id"):
        logger.warning("Missing conversation_id or user_id")
        return False
    
    return True
