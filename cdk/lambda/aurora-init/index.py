import json
import boto3
import os

rds_data = boto3.client('rds-data')

def handler(event, context):
    request_type = event['RequestType']
    
    if request_type == 'Delete':
        return send_response(event, context, 'SUCCESS', {})
    
    if request_type != 'Create':
        return send_response(event, context, 'SUCCESS', {})
    
    cluster_arn = os.environ['CLUSTER_ARN']
    secret_arn = os.environ['SECRET_ARN']
    database_name = os.environ['DATABASE_NAME']
    
    # SQL statements to execute one by one
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE EXTENSION IF NOT EXISTS btree_gin",
        """CREATE TABLE IF NOT EXISTS bot_vectors (
              bot_id VARCHAR(255) PRIMARY KEY,
              title TEXT NOT NULL,
              description TEXT,
              instruction TEXT,
              owner_user_id VARCHAR(255),
              embedding vector(1536),
              create_time BIGINT,
              last_used_time BIGINT,
              sync_status VARCHAR(50) DEFAULT 'SUCCEEDED',
              shared_scope VARCHAR(50) DEFAULT 'PRIVATE',
              is_pinned BOOLEAN DEFAULT FALSE,
              allowed_users TEXT[],
              search_vector tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(instruction, '')), 'C')
              ) STORED,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
        "CREATE INDEX IF NOT EXISTS bot_vectors_embedding_idx ON bot_vectors USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS bot_vectors_search_idx ON bot_vectors USING GIN(search_vector)",
        "CREATE INDEX IF NOT EXISTS bot_vectors_title_trgm_idx ON bot_vectors USING GIN(title gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS bot_vectors_owner_idx ON bot_vectors(owner_user_id)",
        "CREATE INDEX IF NOT EXISTS bot_vectors_shared_idx ON bot_vectors(shared_scope)",
        """CREATE TABLE IF NOT EXISTS conversation_vectors (
              conversation_id VARCHAR(255) PRIMARY KEY,
              user_id VARCHAR(255) NOT NULL,
              title TEXT NOT NULL,
              title_embedding vector(1536),
              bot_id VARCHAR(255),
              last_updated_time BIGINT,
              message_count INTEGER DEFAULT 0,
              search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(title, ''))
              ) STORED,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
        "CREATE INDEX IF NOT EXISTS conversation_vectors_embedding_idx ON conversation_vectors USING ivfflat (title_embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS conversation_vectors_search_idx ON conversation_vectors USING GIN(search_vector)",
        "CREATE INDEX IF NOT EXISTS conversation_vectors_user_idx ON conversation_vectors(user_id)",
        "CREATE INDEX IF NOT EXISTS conversation_vectors_bot_idx ON conversation_vectors(bot_id)",
        """CREATE TABLE IF NOT EXISTS conversation_metadata (
              id SERIAL PRIMARY KEY,
              conversation_id VARCHAR(255) UNIQUE NOT NULL,
              user_id VARCHAR(255) NOT NULL,
              extracted_name VARCHAR(255),
              extracted_company VARCHAR(255),
              extracted_role VARCHAR(255),
              extracted_contact VARCHAR(255),
              main_topic TEXT,
              summary TEXT,
              extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
        "CREATE INDEX IF NOT EXISTS conversation_metadata_conversation_idx ON conversation_metadata(conversation_id)",
        "CREATE INDEX IF NOT EXISTS conversation_metadata_user_idx ON conversation_metadata(user_id)",
    ]
    
    try:
        for sql in statements:
            print(f"Executing: {sql[:100]}...")
            response = rds_data.execute_statement(
                resourceArn=cluster_arn,
                secretArn=secret_arn,
                database=database_name,
                sql=sql
            )
            print(f"Success: {response.get('numberOfRecordsUpdated', 0)} records affected")
        
        return send_response(event, context, 'SUCCESS', {'Message': 'Database initialized successfully'})
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return send_response(event, context, 'FAILED', {'Message': str(e)})


def send_response(event, context, response_status, response_data):
    import urllib3
    http = urllib3.PoolManager()
    
    response_body = json.dumps({
        'Status': response_status,
        'Reason': f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    })
    
    headers = {'Content-Type': ''}
    
    try:
        http.request('PUT', event['ResponseURL'], body=response_body, headers=headers)
    except Exception as e:
        print(f"Failed to send response: {e}")
    
    return {
        'statusCode': 200,
        'body': json.dumps(response_data)
    }
