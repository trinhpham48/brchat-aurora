"""
Lambda Handler - Extract info from conversations using Bedrock
Runs every 8 hours via EventBridge
"""
import json
import logging
import os
from typing import Any, Dict

import boto3

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
CONVERSATION_TABLE_NAME = os.environ.get("CONVERSATION_TABLE_NAME", "")
AURORA_CLUSTER_ARN = os.environ.get("AURORA_CLUSTER_ARN", "")
AURORA_SECRET_ARN = os.environ.get("AURORA_SECRET_ARN", "")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "bedrockchat")
BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# AWS clients
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")
rds_data = boto3.client("rds-data")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler"""
    logger.info("Starting conversation extraction")
    
    try:
        # Get conversations from DynamoDB (simplified for now)
        table = dynamodb.Table(CONVERSATION_TABLE_NAME)
        response = table.scan(Limit=10)  # Small batch for testing
        
        processed = 0
        for item in response.get("Items", []):
            conversation_id = item.get("SK", "")
            user_id = item.get("PK", "")
            
            if not conversation_id or not user_id:
                continue
            
            logger.info(f"Processing: {conversation_id}")
            
            # Extract info using Bedrock
            extracted_info = extract_with_bedrock(item)
            
            # Save to Aurora
            save_to_aurora(conversation_id, user_id, extracted_info)
            
            processed += 1
        
        return {
            "statusCode": 200,
            "body": json.dumps({"processed": processed})
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def extract_with_bedrock(conversation: Dict) -> Dict:
    """Extract structured info using Bedrock"""
    messages = conversation.get("message_map", {})
    
    # Format conversation text
    conversation_text = format_messages(messages)
    
    # Bedrock prompt
    prompt = f"""Extract from this conversation:
- name (person's name)
- company (organization name)
- role (job title)
- contact (email or phone)
- topic (main topic)
- summary (brief summary)

Return ONLY valid JSON.

Conversation:
{conversation_text}

JSON:"""
    
    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        
        # Parse JSON from response
        return json.loads(text.strip())
        
    except Exception as e:
        logger.warning(f"Bedrock extraction failed: {e}")
        return {}


def format_messages(messages: Dict) -> str:
    """Format message map to text"""
    texts = []
    for msg_id, msg in messages.items():
        role = msg.get("role", "user")
        content = msg.get("content", [])
        for c in content:
            if isinstance(c, dict) and "body" in c:
                texts.append(f"{role.upper()}: {c['body']}")
    return "\n".join(texts[:20])  # Limit length


def save_to_aurora(conversation_id: str, user_id: str, info: Dict) -> None:
    """Save extracted info to Aurora"""
    sql = """
    INSERT INTO conversation_metadata 
    (conversation_id, user_id, extracted_name, extracted_company, 
     extracted_role, extracted_contact, main_topic, summary)
    VALUES (:cid, :uid, :name, :company, :role, :contact, :topic, :summary)
    ON CONFLICT (conversation_id) DO NOTHING
    """
    
    try:
        rds_data.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=DATABASE_NAME,
            sql=sql,
            parameters=[
                {"name": "cid", "value": {"stringValue": conversation_id}},
                {"name": "uid", "value": {"stringValue": user_id}},
                {"name": "name", "value": {"stringValue": info.get("name", "") or ""}},
                {"name": "company", "value": {"stringValue": info.get("company", "") or ""}},
                {"name": "role", "value": {"stringValue": info.get("role", "") or ""}},
                {"name": "contact", "value": {"stringValue": info.get("contact", "") or ""}},
                {"name": "topic", "value": {"stringValue": info.get("topic", "") or ""}},
                {"name": "summary", "value": {"stringValue": info.get("summary", "") or ""}},
            ]
        )
        logger.info(f"Saved to Aurora: {conversation_id}")
    except Exception as e:
        logger.error(f"Aurora save failed: {e}")
