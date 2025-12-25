# Conversation Information Extractor - Deployment Guide

## 📦 Đã tạo xong!

### File Structure
```
backend/conversation_extractor/
├── __init__.py                 # Module initialization
├── handler.py                  # Lambda entry point
├── extractor.py                # Bedrock extraction logic
├── repository.py               # DynamoDB & Aurora data access
├── requirements.txt            # Python dependencies
├── schema.sql                  # Aurora table schema
└── README.md                   # Documentation

cdk/lib/
└── conversation-extractor-stack.ts  # CDK infrastructure
```

---

## 🎯 Flow đã chốt

```
EventBridge Schedule (every 8 hours)
├─ 00:00 AM
├─ 08:00 AM  
└─ 16:00 PM

        ↓

Lambda: conversation-info-extractor
├─ Query DynamoDB (conversations idle 8-16h)
├─ Call Bedrock (Claude 3.5 Sonnet)
└─ Save to Aurora PostgreSQL

        ↓

Output: name, company, role, contact, topic, summary
```

---

## 🚀 Deployment Steps

### 1. Setup Aurora Schema

Chạy script SQL để tạo bảng:

```bash
# Connect to Aurora PostgreSQL
psql -h <aurora-endpoint> -U <username> -d bedrock_chat

# Run schema
\i backend/conversation_extractor/schema.sql
```

Hoặc dùng RDS Data API:
```bash
aws rds-data execute-statement \
  --resource-arn <cluster-arn> \
  --secret-arn <secret-arn> \
  --database bedrock_chat \
  --sql "$(cat backend/conversation_extractor/schema.sql)"
```

### 2. Integrate vào CDK Main Stack

Thêm vào `bedrock-chat-stack.ts`:

```typescript
import { ConversationExtractorStack } from "./conversation-extractor-stack";

// ... trong BedrockChatStack constructor:

// Add Conversation Extractor
new ConversationExtractorStack(this, "ConversationExtractor", {
  vpc: this.vpc,
  conversationTableName: database.conversationTable.tableName,
  conversationTableArn: database.conversationTable.tableArn,
  auroraClusterArn: database.auroraCluster.clusterArn,
  auroraSecretArn: database.auroraSecret.secretArn,
  databaseName: "bedrock_chat",
  bedrockModelId: "anthropic.claude-3-5-sonnet-20241022-v2:0",
  envPrefix: props.envPrefix,
});
```

### 3. Deploy

```bash
cd cdk
npm install
cdk deploy
```

---

## ⚙️ Configuration

### Environment Variables

Lambda tự động có các env vars:
- `CONVERSATION_TABLE_NAME` - DynamoDB table
- `AURORA_CLUSTER_ARN` - Aurora cluster
- `AURORA_SECRET_ARN` - DB credentials
- `DATABASE_NAME` - Database name
- `BEDROCK_MODEL_ID` - Model để extract

### Schedule

Mặc định: **Mỗi 8h** (00:00, 08:00, 16:00 UTC)

Thay đổi trong CDK:
```typescript
schedule: events.Schedule.cron({
  minute: "0",
  hour: "0,8,16",  // Modify this
}),
```

---

## 📊 Monitoring

### CloudWatch Logs

```bash
# View logs
aws logs tail /aws/lambda/ConversationExtractorFunction --follow

# Check recent executions
aws lambda get-function --function-name ConversationExtractorFunction
```

### Metrics to monitor

- **Invocations**: 3/day expected
- **Duration**: ~5-10 minutes typical
- **Errors**: Should be 0
- **Processed conversations**: Check logs

### Sample log output

```json
{
  "processed": 45,
  "errors": 0,
  "skipped": 12,
  "total": 57,
  "timestamp": "2025-12-25T08:00:00Z"
}
```

---

## 🧪 Testing

### Manual Trigger

```bash
# Invoke Lambda manually
aws lambda invoke \
  --function-name ConversationExtractorFunction \
  --payload '{}' \
  response.json

cat response.json
```

### Check Results in Aurora

```sql
-- Check recent extractions
SELECT 
  conversation_id,
  extracted_name,
  extracted_company,
  extracted_at
FROM conversation_metadata
ORDER BY extracted_at DESC
LIMIT 10;

-- Count by company
SELECT 
  extracted_company,
  COUNT(*) as count
FROM conversation_metadata
WHERE extracted_company IS NOT NULL
GROUP BY extracted_company
ORDER BY count DESC;
```

---

## 💰 Cost Estimate

**Assumptions:**
- 300 conversations/day
- Average 1000 tokens/conversation

**Costs:**
- Lambda: ~$0.10/month (minimal runtime)
- Bedrock: ~$9/month (300 calls/day × $0.001)
- DynamoDB: ~$0.05/month (read ops)
- Aurora: Included in existing cluster
- **Total: ~$10/month**

---

## 🔧 Troubleshooting

### Lambda timeout
- Increase timeout in CDK (currently 15 min)
- Reduce batch size (currently 200)

### No conversations found
- Check idle time range (8-16h)
- Verify DynamoDB has data
- Check last_message_time field

### Bedrock errors
- Verify model ID
- Check IAM permissions
- Confirm region supports model

### Aurora connection issues
- Verify Lambda in correct VPC
- Check security groups
- Verify RDS Data API enabled

---

## ✅ Checklist

- [ ] Aurora schema created
- [ ] CDK stack integrated
- [ ] Deployed successfully
- [ ] Manual test passed
- [ ] CloudWatch logs visible
- [ ] First scheduled run completed
- [ ] Data in Aurora verified

---

## 📝 Next Steps

1. **Monitor first few runs** to ensure stable
2. **Adjust schedule** if needed (currently 8h)
3. **Add alerting** for errors (SNS/CloudWatch Alarms)
4. **Create dashboard** for extracted data analytics
5. **Consider GSI** on DynamoDB for better performance (future optimization)

---

**Status: ✅ READY TO DEPLOY**

Bạn có thể chạy `cdk deploy` ngay!
