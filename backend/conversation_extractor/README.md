# Conversation Information Extractor

Lambda function to extract structured information from conversations using Amazon Bedrock.

## Features

- **Scheduled Extraction**: Runs every 8 hours (00:00, 08:00, 16:00) via EventBridge
- **Smart Filtering**: Only processes conversations idle for 8-16 hours
- **Bedrock Integration**: Uses Claude 3.5 Sonnet for information extraction
- **Aurora Storage**: Saves extracted data to PostgreSQL

## Extracted Information

- Name (họ tên)
- Company (công ty)
- Role (chức vụ)
- Contact (email/phone)
- Main Topic (chủ đề chính)
- Summary (tóm tắt)

## Architecture

```
EventBridge (8h schedule)
        ↓
Lambda: conversation-info-extractor
        ↓
DynamoDB (query conversations)
        ↓
Bedrock (Claude 3.5 Sonnet)
        ↓
Aurora PostgreSQL (save results)
```

## Files

- `handler.py` - Main Lambda handler
- `extractor.py` - Bedrock extraction logic
- `repository.py` - DynamoDB and Aurora data access
- `schema.sql` - Aurora table schema
- `requirements.txt` - Python dependencies

## Environment Variables

```
CONVERSATION_TABLE_NAME - DynamoDB conversation table
AURORA_CLUSTER_ARN - Aurora cluster ARN
AURORA_SECRET_ARN - Secret ARN for DB credentials
DATABASE_NAME - Aurora database name (default: bedrock_chat)
BEDROCK_MODEL_ID - Model ID (default: claude-3-5-sonnet)
```

## Deployment

Deploy using CDK (see cdk/lib/conversation-extractor-stack.ts)

## Monitoring

Check CloudWatch Logs for:
- Processing statistics
- Extraction results
- Errors and warnings

## Cost Optimization

- Runs 3 times per day only
- Processes max 200 conversations per run
- Skips already extracted conversations
- Uses efficient DynamoDB queries
