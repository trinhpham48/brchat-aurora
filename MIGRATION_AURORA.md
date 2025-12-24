# Migration Guide: OpenSearch → Aurora PostgreSQL

## Overview

Dự án đã được update để thay thế **OpenSearch Bot Store** bằng **Aurora PostgreSQL** với:
- ✅ Vector search (pgvector) cho embeddings
- ✅ Full-text search cho bot/conversation discovery
- ✅ Fuzzy matching với pg_trgm
- ✅ Chi phí tiết kiệm ~$250-400/tháng (60-70%)

## Changes Made

### Infrastructure (CDK)
1. ✅ Created `cdk/lib/constructs/aurora.ts` - Aurora Serverless v2 cluster
2. ✅ Updated `bedrock-chat-stack.ts` - Added Aurora, disabled OpenSearch Bot Store
3. ✅ Updated `api.ts` - Aurora permissions and environment variables

### Backend (Python)
1. ✅ Created `backend/app/repositories/aurora_client.py` - RDS Data API client
2. ✅ Created `backend/app/repositories/bot_store_aurora.py` - Bot search with Aurora
3. ✅ Created `backend/app/repositories/conversation_search_aurora.py` - Conversation search
4. ✅ Updated `backend/app/repositories/custom_bot.py` - Auto-sync to Aurora
5. ✅ Updated `backend/app/usecases/bot_store.py` - Feature flag for Aurora

### Migration
1. ✅ Created `backend/scripts/sync_existing_data_to_aurora.py` - Sync existing data

## Deployment Steps

### 1. Deploy Infrastructure

```bash
cd cdk
npm install
npm run cdk deploy
```

**Note:** Deployment sẽ mất ~10-15 phút để:
- Tạo Aurora Serverless v2 cluster
- Tạo VPC, Security Groups
- Initialize database với pgvector extension
- Tạo tables và indexes

### 2. Verify Aurora Deployment

Sau khi deploy xong, kiểm tra outputs:

```bash
# Check CDK outputs
aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].Outputs'
```

Tìm các outputs:
- `ClusterEndpoint` - Aurora endpoint
- `ClusterArn` - ARN cho RDS Data API
- `SecretArn` - Secret chứa DB credentials

### 3. Migrate Existing Data (Optional but Recommended)

Nếu bạn đã có bots trong DynamoDB:

```bash
cd backend

# Set environment variables
export USE_AURORA_SEARCH=true
export AURORA_CLUSTER_ARN=<from-cdk-output>
export AURORA_SECRET_ARN=<from-cdk-output>
export AURORA_DATABASE_NAME=bedrockchat
export AWS_REGION=us-east-1

# Run migration
poetry run python scripts/sync_existing_data_to_aurora.py
```

Migration script sẽ:
- Scan tất cả bots trong DynamoDB
- Generate embeddings cho search
- Insert vào Aurora với full-text search indexes

### 4. Test Aurora Search

```bash
# Test connection
aws rds-data execute-statement \
  --resource-arn <CLUSTER_ARN> \
  --secret-arn <SECRET_ARN> \
  --database bedrockchat \
  --sql "SELECT COUNT(*) FROM bot_vectors"

# Verify data
aws rds-data execute-statement \
  --resource-arn <CLUSTER_ARN> \
  --secret-arn <SECRET_ARN> \
  --database bedrockchat \
  --sql "SELECT bot_id, title FROM bot_vectors LIMIT 5"
```

### 5. Enable Aurora Search (Production)

Aurora search được enable tự động qua environment variable `USE_AURORA_SEARCH=true` trong Lambda.

Verify trong Lambda console:
```
Configuration > Environment variables > USE_AURORA_SEARCH = true
```

## Cost Comparison

### Before (OpenSearch + DynamoDB):
| Service | Cost/Month |
|---------|------------|
| DynamoDB | $50-80 |
| OpenSearch Serverless (0.5 OCU min) | $350-500 |
| OSIS Pipelines | $30-50 |
| **TOTAL** | **$430-630** |

### After (Aurora + DynamoDB):
| Service | Cost/Month |
|---------|------------|
| DynamoDB | $50-80 |
| Aurora Serverless v2 (0.5-2 ACU) | $80-120 |
| **TOTAL** | **$130-200** |

**💰 Savings: $250-430/month (60-70%)**

## Architecture

```
┌─────────────────────────────────────────────────────┐
│          Bedrock Chat (Aurora Version)             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐      ┌─────────────────────────┐ │
│  │  DynamoDB   │      │  Aurora PostgreSQL      │ │
│  ├─────────────┤      ├─────────────────────────┤ │
│  │• BotTable   │─────▶│• bot_vectors (pgvector) │ │
│  │• ConvTable  │      │• conversation_vectors   │ │
│  │• Websocket  │      │• Full-text search (GIN) │ │
│  │             │      │• Fuzzy match (pg_trgm)  │ │
│  └─────────────┘      └─────────────────────────┘ │
│   Source of Truth      Search Index                │
│                                                     │
│  Lambda auto-syncs on create/update/delete         │
└─────────────────────────────────────────────────────┘
```

## Testing

### Test Bot Search
```python
# In Lambda or local
from app.repositories.bot_store_aurora import find_bots_by_query_aurora
from app.user import User

user = User(id="test-user", groups=[])
bots = find_bots_by_query_aurora("chatbot", user, limit=10)
print(f"Found {len(bots)} bots")
```

### Test Conversation Search
```python
from app.repositories.conversation_search_aurora import find_conversations_by_query_aurora

conversations = find_conversations_by_query_aurora("hello", user, limit=10)
print(f"Found {len(conversations)} conversations")
```

## Rollback Plan (If Needed)

Nếu có vấn đề, rollback bằng cách:

1. **Disable Aurora search** (immediate):
```bash
aws lambda update-function-configuration \
  --function-name <LAMBDA_NAME> \
  --environment Variables={USE_AURORA_SEARCH=false}
```

2. **Re-enable OpenSearch Bot Store** (requires redeploy):
```typescript
// In cdk/lib/bedrock-chat-stack.ts
let botStore = undefined;
if (props.enableBotStore) {  // Uncomment this block
  botStore = new BotStore(this, "BotStore", {
    envPrefix: props.envPrefix,
    botTable: database.botTable,
    conversationTable: database.conversationTable,
    language: props.botStoreLanguage,
    enableBotStoreReplicas: props.enableBotStoreReplicas,
  });
}
```

```bash
npm run cdk deploy
```

## Monitoring

### CloudWatch Metrics to Monitor:
- `AuroraCPUUtilization` - Should be < 50%
- `AuroraServerlessDatabaseCapacity` - ACU usage (0.5-2)
- `AuroraQueryDuration` - Search performance
- Lambda `Duration` - Should not increase significantly

### CloudWatch Logs:
```
/aws/lambda/BedrockChatStack-BackendApi*
# Look for: "Using Aurora search for query"
# Any errors: "Aurora bot search failed"
```

## Troubleshooting

### Bot search returns empty
```bash
# Check if data exists in Aurora
aws rds-data execute-statement \
  --resource-arn <ARN> \
  --secret-arn <SECRET> \
  --database bedrockchat \
  --sql "SELECT COUNT(*) FROM bot_vectors"
```

### Lambda can't connect to Aurora
- Verify Lambda is in same VPC as Aurora
- Check Security Group allows port 5432
- Verify RDS Data API is enabled

### Slow search performance
```sql
-- Rebuild indexes
REINDEX TABLE bot_vectors;
REINDEX TABLE conversation_vectors;

-- Analyze tables
ANALYZE bot_vectors;
ANALYZE conversation_vectors;
```

## Next Steps

1. ✅ Monitor for 1 week
2. ✅ Collect user feedback
3. ✅ If stable, delete OpenSearch Bot Store resources
4. ⏳ Add usage analytics to Aurora (future)
5. ⏳ Add advanced search filters (future)

## Support

Nếu có vấn đề, check logs và metrics. Aurora search được thiết kế để fail gracefully - nếu có lỗi, Lambda vẫn hoạt động nhưng search sẽ return empty results.

---

**Deployment Date:** December 24, 2025  
**Migration Status:** Ready for Production
