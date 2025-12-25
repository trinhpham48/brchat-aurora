# Conversation Extractor Lambda

Simple Lambda function to extract structured information from bedrock-chat conversations using Amazon Bedrock.

## What it does

1. Reads a conversation from DynamoDB
2. Sends conversation text to Bedrock Claude 3.5 Sonnet
3. Extracts: name, company, role, contact, topic, summary
4. Returns structured JSON

## Deployment

### Option 1: AWS Console (Easiest)

1. Go to AWS Lambda Console
2. Create new function: `conversation-extractor`
3. Runtime: Python 3.12
4. Upload `lambda_function.py`
5. Set environment variable:
   - `CONVERSATION_TABLE` = your DynamoDB table name (e.g., `BedrockChatStack-DatabaseConversationTable-XXX`)
6. Add permissions to IAM role:
   - DynamoDB: `GetItem` on conversation table
   - Bedrock: `InvokeModel` on Claude 3.5 Sonnet
7. Set timeout: 5 minutes
8. Set memory: 256 MB

### Option 2: AWS CLI

```bash
# Create ZIP
cd conversation-extractor-lambda
zip -r lambda.zip lambda_function.py

# Create Lambda function
aws lambda create-function \
  --function-name conversation-extractor \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/YOUR_LAMBDA_ROLE \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda.zip \
  --timeout 300 \
  --memory-size 256 \
  --environment Variables="{CONVERSATION_TABLE=YOUR_TABLE_NAME}"
```

## Usage

### Test from AWS Console

Input:
```json
{
  "conversation_id": "01JFXXXXXXXXXXXXXXXXXXX"
}
```

### Invoke from AWS CLI

```bash
aws lambda invoke \
  --function-name conversation-extractor \
  --payload '{"conversation_id": "01JFXXXXXXXXXXXXXXXXXXX"}' \
  output.json

cat output.json
```

## Response Example

```json
{
  "statusCode": 200,
  "body": "{\"conversation_id\": \"01JFXXX...\", \"extracted_info\": {\"name\": \"John Doe\", \"company\": \"Acme Corp\", \"role\": \"Senior Engineer\", \"contact\": \"john@acme.com\", \"topic\": \"AWS migration\", \"summary\": \"Discussion about migrating infrastructure to AWS.\"}}"
}
```

## IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "dynamodb:GetItem",
      "Resource": "arn:aws:dynamodb:REGION:ACCOUNT:table/YOUR_TABLE"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:REGION::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    }
  ]
}
```

## Notes

- This Lambda is **standalone** and doesn't require the bedrock-chat CDK stack
- No VPC required
- No Aurora dependency
- Just DynamoDB read + Bedrock API call
- Can be deployed completely separately
