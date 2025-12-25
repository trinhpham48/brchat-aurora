-- ============================================
-- Aurora PostgreSQL Schema
-- Table: conversation_metadata
-- Purpose: Store extracted information from conversations
-- ============================================

-- Create table
CREATE TABLE IF NOT EXISTS conversation_metadata (
    -- Primary key
    conversation_id VARCHAR(255) PRIMARY KEY,
    
    -- User reference
    user_id VARCHAR(255) NOT NULL,
    
    -- Extracted information
    extracted_name VARCHAR(255),
    extracted_company VARCHAR(255),
    extracted_role VARCHAR(255),
    extracted_contact VARCHAR(500),
    main_topic TEXT,
    summary TEXT,
    
    -- Model tracking
    model_id VARCHAR(100),
    
    -- Timestamps
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes
    CONSTRAINT conversation_metadata_pkey PRIMARY KEY (conversation_id)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_conversation_metadata_user_id 
    ON conversation_metadata(user_id);

CREATE INDEX IF NOT EXISTS idx_conversation_metadata_extracted_at 
    ON conversation_metadata(extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_metadata_company 
    ON conversation_metadata(extracted_company) 
    WHERE extracted_company IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversation_metadata_name 
    ON conversation_metadata(extracted_name) 
    WHERE extracted_name IS NOT NULL;

-- Add comments for documentation
COMMENT ON TABLE conversation_metadata IS 'Stores extracted structured information from conversations using Bedrock';
COMMENT ON COLUMN conversation_metadata.conversation_id IS 'Unique conversation identifier from DynamoDB';
COMMENT ON COLUMN conversation_metadata.user_id IS 'User who owns the conversation';
COMMENT ON COLUMN conversation_metadata.extracted_name IS 'Extracted person name from conversation';
COMMENT ON COLUMN conversation_metadata.extracted_company IS 'Extracted company/organization name';
COMMENT ON COLUMN conversation_metadata.extracted_role IS 'Extracted job title or role';
COMMENT ON COLUMN conversation_metadata.extracted_contact IS 'Extracted email or phone number';
COMMENT ON COLUMN conversation_metadata.main_topic IS 'Main topic discussed in conversation';
COMMENT ON COLUMN conversation_metadata.summary IS 'Brief summary of conversation content';
COMMENT ON COLUMN conversation_metadata.model_id IS 'Bedrock model ID used for extraction';
COMMENT ON COLUMN conversation_metadata.extracted_at IS 'When the extraction was performed';

-- ============================================
-- Sample Queries
-- ============================================

-- Query all extracted conversations for a user
-- SELECT * FROM conversation_metadata WHERE user_id = 'user_123';

-- Search by company
-- SELECT * FROM conversation_metadata WHERE extracted_company LIKE '%FPT%';

-- Get recent extractions
-- SELECT * FROM conversation_metadata ORDER BY extracted_at DESC LIMIT 100;

-- Count extractions by company
-- SELECT extracted_company, COUNT(*) 
-- FROM conversation_metadata 
-- WHERE extracted_company IS NOT NULL 
-- GROUP BY extracted_company 
-- ORDER BY COUNT(*) DESC;

-- Find conversations with contact info
-- SELECT conversation_id, extracted_name, extracted_contact 
-- FROM conversation_metadata 
-- WHERE extracted_contact IS NOT NULL;
