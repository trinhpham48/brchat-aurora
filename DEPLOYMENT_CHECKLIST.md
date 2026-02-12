# 🚀 Deployment Checklist - S3 Vector Store Migration

## ✅ Pre-Deployment

- [x] Code đã được sửa đổi
  - [x] bedrock-custom-bot-stack.ts
  - [x] bedrock-shared-knowledge-bases-stack.ts
  - [x] README.md
  - [x] Migration guide created

- [ ] **BACKUP hiện tại**
  ```bash
  # 1. Backup DynamoDB bots table
  aws dynamodb export-table-to-point-in-time \
    --table-arn <BotTableArn> \
    --s3-bucket <BackupBucket> \
    --export-time $(date +%s)
  
  # 2. Backup Knowledge Base IDs
  aws bedrock-agent list-knowledge-bases > kb_backup_$(date +%Y%m%d).json
  
  # 3. Export CloudFormation templates
  aws cloudformation list-stacks > stacks_backup_$(date +%Y%m%d).json
  ```

- [ ] Review thay đổi
  ```bash
  cd d:\brchat\brchat-aurora\cdk
  npx cdk diff
  ```

## 🔧 Deployment Steps

### Step 1: Build và Test
```bash
cd d:\brchat\brchat-aurora\cdk

# Install dependencies
npm ci

# Build
npm run build

# Optional: Run tests
npm test
```

### Step 2: Review Changes
```bash
# See what will change
npx cdk diff BedrockChatStack

# If you have custom bots
npx cdk diff --all
```

**Expected Changes:**
- ❌ DELETE: OpenSearch Serverless Collections
- ❌ DELETE: OpenSearch Vector Indexes
- ✅ CREATE: S3 Managed Vector Store (auto-created by Bedrock)
- ℹ️ NO CHANGE: Aurora PostgreSQL (Bot Store)
- ℹ️ NO CHANGE: DynamoDB, Lambda, API Gateway

### Step 3: Deploy
```bash
# Deploy all stacks
npx cdk deploy --all

# Or deploy one by one
npx cdk deploy BedrockChatStack
```

**Duration:** ~5-10 phút

### Step 4: Verify Deployment
```bash
# 1. Check CloudFormation status
aws cloudformation describe-stacks \
  --stack-name BedrockChatStack \
  --query 'Stacks[0].StackStatus'

# Should return: UPDATE_COMPLETE

# 2. List Knowledge Bases
aws bedrock-agent list-knowledge-bases

# 3. Check one Knowledge Base detail
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id <KB_ID> \
  --query 'knowledgeBase.storageConfiguration.type'

# Should return: "S3" (not "OPENSEARCH_SERVERLESS")
```

## 🧪 Testing

### Test 1: Create New Bot with Knowledge
- [ ] Login to UI
- [ ] Create new bot
- [ ] Add knowledge base (upload PDF/document)
- [ ] Wait for ingestion to complete
- [ ] Test query: Ask question about document
- [ ] Verify response is correct

### Test 2: Existing Bots
- [ ] Open existing bot with knowledge
- [ ] Test query
- [ ] If fails: Trigger re-sync
  ```bash
  aws stepfunctions start-execution \
    --state-machine-arn $EMBEDDING_STATE_MACHINE_ARN
  ```

### Test 3: Shared Knowledge Base
- [ ] Create bot with "shared" knowledge type
- [ ] Upload document
- [ ] Create another bot using same shared KB
- [ ] Verify both bots can query

### Test 4: Performance
- [ ] Compare query latency (should be similar or better)
- [ ] Check CloudWatch metrics
  ```bash
  aws cloudwatch get-metric-statistics \
    --namespace AWS/Bedrock \
    --metric-name KnowledgeBaseQueryLatency \
    --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Average
  ```

## 📊 Post-Deployment Monitoring

### CloudWatch Logs
```bash
# Monitor backend logs
aws logs tail /aws/lambda/BedrockChatStack-BackendApi* --follow

# Look for:
# ✅ "Successfully created knowledge base"
# ✅ "Knowledge base query completed"
# ❌ Any errors
```

### CloudWatch Metrics
Monitor for 7 days:
- [ ] `KnowledgeBaseQueryCount` - Should be normal
- [ ] `KnowledgeBaseQueryLatency` - Should be <2s
- [ ] `Lambda Duration` - Should not increase
- [ ] `API Gateway 4XX/5XX` - Should be low

### Cost Analysis
```bash
# After 7 days, check billing
# Expected savings: ~$330-500/month

# 1. Check S3 costs (should be $5-20)
# 2. Check OpenSearch costs (should be $0)
# 3. Compare with previous month
```

## 🔍 Verification Checklist

- [ ] All new knowledge bases use S3 storage
- [ ] Existing bots still work
- [ ] Documents can be uploaded
- [ ] Queries return correct answers
- [ ] No errors in CloudWatch Logs
- [ ] OpenSearch billing stopped (check after 1 week)
- [ ] S3 costs are minimal (<$30/month)

## 🔄 Rollback Plan (If Needed)

Nếu có vấn đề nghiêm trọng:

```bash
# 1. Revert code changes
cd d:\brchat\brchat-aurora
git diff HEAD cdk/lib/bedrock-custom-bot-stack.ts
git diff HEAD cdk/lib/bedrock-shared-knowledge-bases-stack.ts

# If changes look good to revert:
git checkout HEAD~1 cdk/lib/bedrock-custom-bot-stack.ts
git checkout HEAD~1 cdk/lib/bedrock-shared-knowledge-bases-stack.ts
git checkout HEAD~1 README.md

# 2. Rebuild
cd cdk
npm run build

# 3. Redeploy
npx cdk deploy --all

# 4. Restore data if needed
# (use backups from pre-deployment)
```

## 📈 Success Criteria

Migration được coi là thành công khi:

✅ **Functionality:**
- [ ] All bots work normally
- [ ] New knowledge bases can be created
- [ ] Documents sync successfully
- [ ] Queries return accurate results

✅ **Performance:**
- [ ] Query latency ≤ previous performance
- [ ] No increase in error rates
- [ ] System stable for 7 days

✅ **Cost:**
- [ ] OpenSearch charges = $0
- [ ] S3 vector store costs < $30/month
- [ ] Total savings ≥ $300/month

## 🎉 Post-Migration Tasks

After successful 7-day monitoring:

- [ ] Delete old OpenSearch collections (if any remain)
  ```bash
  # List collections
  aws opensearchserverless list-collections
  
  # Delete if safe
  aws opensearchserverless delete-collection \
    --id <collection-id>
  ```

- [ ] Update team documentation
- [ ] Notify users of improvements
- [ ] Document lessons learned
- [ ] Plan to monitor cost savings monthly

## 📞 Support Contacts

- **Documentation:** 
  - [MIGRATION_S3_VECTOR.md](./MIGRATION_S3_VECTOR.md)
  - [SUMMARY_S3_MIGRATION.md](./SUMMARY_S3_MIGRATION.md)
  - [README.md](./README.md)

- **AWS Support:** 
  - Bedrock: https://docs.aws.amazon.com/bedrock/
  - Knowledge Bases: https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html

## 📝 Notes

- **Timeline:** Allow 7 days for complete validation
- **Rollback window:** Can rollback within 30 days if needed
- **Data retention:** S3 documents retained, only vectors re-indexed
- **Zero downtime:** Migration should not cause service interruption

---

**Prepared:** February 11, 2026  
**Target Deployment:** [Your Date]  
**Estimated Duration:** 30-60 minutes  
**Risk Level:** Low (can rollback)  
