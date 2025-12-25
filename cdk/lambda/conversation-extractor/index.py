"""
Lambda: Extract info from conversations using Bedrock
Author: Simple & Efficient
"""
import json
import os
import boto3

# Environment
TABLE_NAME = os.environ.get("TABLE_NAME", "")
BEDROCK_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# Clients
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")


def handler(event, context):
    """Main handler"""
    conversation_id = event.get("conversation_id", "")
    
    if not conversation_id:
        return {"statusCode": 400, "body": "Missing conversation_id"}
    
    try:
        # Read from DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={"SK": conversation_id})
        
        if "Item" not in response:
            return {"statusCode": 404, "body": "Not found"}
        
        # Build text from messages
        messages = response["Item"].get("message_map", {})
        text = []
        for msg_id in sorted(messages.keys()):
            msg = messages[msg_id]
            role = msg.get("role", "user")
            for c in msg.get("content", []):
                if isinstance(c, dict) and "body" in c:
                    text.append(f"{role}: {c['body']}")
        
        conversation_text = "\n".join(text[:50])
        
        # Extract using Bedrock
        prompt = f"""Extract from conversation:
- name: person name
- company: organization
- role: job title
- contact: email/phone
- topic: main topic
- summary: brief summary

Return JSON only.

{conversation_text}

JSON:"""
        
        bedrock_response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        result = json.loads(bedrock_response["body"].read())
        extracted_text = result["content"][0]["text"]
        extracted = json.loads(extracted_text.strip())
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "conversation_id": conversation_id,
                "extracted": extracted
            })
        }
        
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}
