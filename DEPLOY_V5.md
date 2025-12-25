# Deploy Bedrock Chat with Conversation Extractor (Branch v5)

## Bước 1: Clone repo và checkout branch v5

```bash
git clone https://github.com/trinhpham48/brchat-aurora.git
cd brchat-aurora
git checkout v5
```

## Bước 2: Cài đặt dependencies

```bash
# Install CDK dependencies
cd cdk
npm install

# Bootstrap CDK (nếu chưa làm)
npx cdk bootstrap

cd ..
```

## Bước 3: Deploy stack

```bash
cd cdk

# Synth để check
npx cdk synth

# Deploy
npx cdk deploy --all --require-approval never
```

## Bước 4: Lấy thông tin sau deploy

```bash
# Lấy tên Lambda function
aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ConversationExtractorFunctionName`].OutputValue' \
  --output text

# Lấy tên DynamoDB table
aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ConversationTableName`].OutputValue' \
  --output text
```

## Bước 5: Test Lambda function

```bash
# Test với conversation_id thật
aws lambda invoke \
  --function-name <FUNCTION_NAME_FROM_STEP_4> \
  --payload '{"conversation_id": "YOUR_CONVERSATION_ID"}' \
  response.json

# Xem kết quả
cat response.json | jq
```

## Kết quả mong đợi

```json
{
  "statusCode": 200,
  "body": "{\"conversation_id\": \"xxx\", \"extracted\": {\"name\": \"John Doe\", \"company\": \"Acme Corp\", \"role\": \"Engineer\", \"contact\": \"john@acme.com\", \"topic\": \"AWS Migration\", \"summary\": \"Discussion about migrating to AWS\"}}"
}
```

## Stack bao gồm:

✅ Aurora PostgreSQL Serverless v2 (vector search)
✅ DynamoDB (conversations)
✅ Lambda Conversation Extractor (NEW - extract info using Bedrock)
✅ Bedrock Claude 3.5 Sonnet integration
✅ Full bedrock-chat application

## Lambda Conversation Extractor:

- **Input**: `{"conversation_id": "xxx"}`
- **Process**: DynamoDB → Bedrock → Extract
- **Output**: name, company, role, contact, topic, summary
- **Permissions**: DynamoDB GetItem + Bedrock InvokeModel
- **Performance**: 256MB, 3min timeout
