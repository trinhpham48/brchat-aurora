"""Lambda to extract info from conversations using Bedrock"""
import json
import logging
import os
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CONVERSATION_TABLE = os.environ.get("CONVERSATION_TABLE_NAME", "")
BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")


def handler(event, context):
    """Main handler - extract info from one conversation"""
    logger.info("Starting conversation extraction")
    
    conversation_id = event.get("conversation_id")
    if not conversation_id:
        return {"statusCode": 400, "body": "Missing conversation_id"}
    
    try:
        # Get conversation from DynamoDB
        table = dynamodb.Table(CONVERSATION_TABLE)
        response = table.get_item(Key={"SK": conversation_id})
        
        if "Item" not in response:
            return {"statusCode": 404, "body": "Conversation not found"}
        
        conversation = response["Item"]
        logger.info(f"Found conversation: {conversation_id}")
        
        # Extract info using Bedrock
        info = extract_info(conversation)
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "conversation_id": conversation_id,
                "extracted_info": info
            })
        }
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"statusCode": 500, "body": str(e)}


def extract_info(conversation):
    """Extract structured info using Bedrock"""
    messages = conversation.get("message_map", {})
    
    # Build conversation text
    texts = []
    for msg_id in sorted(messages.keys()):
        msg = messages[msg_id]
        role = msg.get("role", "user")
        content = msg.get("content", [])
        
        for c in content:
            if isinstance(c, dict) and "body" in c:
                texts.append(f"{role.upper()}: {c['body']}")
    
    conversation_text = "\n".join(texts[:50])  # Limit length
    
    # Bedrock prompt
    prompt = f"""Analyze this conversation and extract:
- name: person's full name
- company: organization/company name
- role: job title or position
- contact: email or phone number
- topic: main discussion topic
- summary: brief conversation summary

Return ONLY valid JSON format.

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
        extracted = json.loads(text.strip())
        logger.info(f"Extracted: {extracted}")
        return extracted
        
    except Exception as e:
        logger.warning(f"Extraction failed: {e}")
        return {
            "name": "",
            "company": "",
            "role": "",
            "contact": "",
            "topic": "",
            "summary": ""
        }

