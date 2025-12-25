# Test Conversation Extractor Lambda

## Bước 1: Deploy stack (nếu chưa deploy)

```bash
cd cdk
npx cdk deploy --all --require-approval never
```

## Bước 2: Lấy tên Lambda function

```bash
# Cách 1: Từ CloudFormation output
aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ConversationExtractorFunctionName`].OutputValue' \
  --output text

# Cách 2: List tất cả Lambda có tên chứa "Extractor"
aws lambda list-functions \
  --query 'Functions[?contains(FunctionName, `Extractor`)].FunctionName' \
  --output text
```

## Bước 3: Lấy conversation_id từ DynamoDB

```bash
# Lấy tên table
TABLE_NAME=$(aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].Outputs[?contains(OutputKey, `ConversationTable`)].OutputValue' \
  --output text)

echo "Table: $TABLE_NAME"

# Scan lấy 1 conversation để test
aws dynamodb scan \
  --table-name $TABLE_NAME \
  --max-items 5 \
  --query 'Items[].SK.S' \
  --output text
```

## Bước 4: Test Lambda với conversation_id thật

```bash
# Thay YOUR_FUNCTION_NAME và YOUR_CONVERSATION_ID
aws lambda invoke \
  --function-name BedrockChatStack-ConversationExtractorFunction-XXXXX \
  --payload '{"conversation_id": "01JFXXXXXXXXXXXXXXXXXX"}' \
  output.json

# Xem kết quả
cat output.json | jq
```

## Bước 5: Kiểm tra kết quả

### Kết quả thành công:
```json
{
  "statusCode": 200,
  "body": "{\"conversation_id\": \"01JFXXX...\", \"extracted\": {\"name\": \"John Doe\", \"company\": \"Acme Corp\", \"role\": \"Engineer\", \"contact\": \"john@acme.com\", \"topic\": \"AWS migration\", \"summary\": \"Discussion about migrating to AWS\"}}"
}
```

### Nếu không tìm thấy conversation:
```json
{
  "statusCode": 404,
  "body": "Not found"
}
```

### Nếu thiếu conversation_id:
```json
{
  "statusCode": 400,
  "body": "Missing conversation_id"
}
```

## Bước 6: Test từ AWS Console

1. Vào **AWS Lambda Console**
2. Tìm function `BedrockChatStack-ConversationExtractorFunction-XXX`
3. Click **Test** tab
4. Tạo test event với payload:
   ```json
   {
     "conversation_id": "01JFXXXXXXXXXXXXXXXXXX"
   }
   ```
5. Click **Test** button
6. Xem kết quả trong **Execution results**

## Bước 7: Xem CloudWatch Logs

```bash
# Lấy log group name
FUNCTION_NAME="BedrockChatStack-ConversationExtractorFunction-XXXXX"

# Xem logs gần nhất
aws logs tail /aws/lambda/$FUNCTION_NAME --follow
```

## Script test nhanh (All-in-one)

```bash
#!/bin/bash

# Get function name
FUNCTION=$(aws lambda list-functions \
  --query 'Functions[?contains(FunctionName, `Extractor`)].FunctionName' \
  --output text | head -1)

# Get table name
TABLE=$(aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].Outputs[?contains(OutputKey, `ConversationTable`)].OutputValue' \
  --output text)

# Get first conversation
CONV_ID=$(aws dynamodb scan \
  --table-name $TABLE \
  --max-items 1 \
  --query 'Items[0].SK.S' \
  --output text)

echo "Function: $FUNCTION"
echo "Table: $TABLE"
echo "Testing with conversation: $CONV_ID"

# Invoke Lambda
aws lambda invoke \
  --function-name $FUNCTION \
  --payload "{\"conversation_id\": \"$CONV_ID\"}" \
  result.json

# Show result
cat result.json | jq
```

Lưu script trên thành `test-lambda.sh`, chạy `bash test-lambda.sh` là xong!
