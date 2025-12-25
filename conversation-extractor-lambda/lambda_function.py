"""
Simple Lambda to extract info from bedrock-chat conversations
Trigger: Manual or API Gateway
Input: {"conversation_id": "01xxxxx"}
Output: {"name": "...", "company": "...", "role": "...", ...}
"""
import json
import os
import boto3

# Config
CONVERSATION_TABLE = os.environ.get("CONVERSATION_TABLE", "")
BEDROCK_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# Clients
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")


def lambda_handler(event, context):
    """Main handler"""
    # Get conversation_id from event
    conversation_id = event.get("conversation_id")
    if not conversation_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing conversation_id"})
        }
    
    try:
        # 1. Get conversation from DynamoDB
        table = dynamodb.Table(CONVERSATION_TABLE)
        response = table.get_item(Key={"SK": conversation_id})
        
        if "Item" not in response:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Conversation not found"})
            }
        
        conversation = response["Item"]
        
        # 2. Build conversation text
        messages = conversation.get("message_map", {})
        conversation_text = build_conversation_text(messages)
        
        # 3. Extract info using Bedrock
        extracted_info = extract_info_with_bedrock(conversation_text)
        
        # 4. Return result
        return {
            "statusCode": 200,
            "body": json.dumps({
                "conversation_id": conversation_id,
                "extracted_info": extracted_info
            })
        }
        
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def build_conversation_text(messages):
    """Convert message_map to readable text"""
    texts = []
    
    for msg_id in sorted(messages.keys()):
        msg = messages[msg_id]
        role = msg.get("role", "user")
        content = msg.get("content", [])
        
        for item in content:
            if isinstance(item, dict) and "body" in item:
                texts.append(f"{role.upper()}: {item['body']}")
    
    return "\n".join(texts[:50])  # Limit to 50 messages


def extract_info_with_bedrock(conversation_text):
    """Use Bedrock to extract structured info"""
    prompt = f"""Analyze this conversation and extract the following information in JSON format:
- name: Full name of the person (if mentioned)
- company: Company or organization name (if mentioned)
- role: Job title or position (if mentioned)
- contact: Email or phone number (if mentioned)
- topic: Main topic of discussion
- summary: Brief summary of the conversation (1-2 sentences)

Return ONLY valid JSON, no other text.

Conversation:
{conversation_text}

JSON:"""
    
    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        )
        
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        
        # Parse JSON from response
        extracted = json.loads(text.strip())
        return extracted
        
    except Exception as e:
        print(f"Bedrock error: {e}")
        return {
            "name": "",
            "company": "",
            "role": "",
            "contact": "",
            "topic": "",
            "summary": f"Error: {str(e)}"
        }
