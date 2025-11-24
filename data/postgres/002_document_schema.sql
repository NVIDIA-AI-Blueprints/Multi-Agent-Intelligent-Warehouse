-- Document Extraction Agent Database Schema
-- This schema supports the intelligent document processing pipeline

-- Document storage table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size BIGINT NOT NULL,
    upload_timestamp TIMESTAMP DEFAULT NOW(),
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'uploaded',
    processing_stage VARCHAR(50),
    document_type VARCHAR(50), -- 'invoice', 'receipt', 'bol', 'purchase_order', etc.
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Link documents to warehouse operations
CREATE TABLE IF NOT EXISTS document_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    operation_type VARCHAR(50), -- 'inbound', 'outbound', 'inventory', 'safety'
    operation_id UUID, -- Reference to specific operation
    created_at TIMESTAMP DEFAULT NOW()
);

-- Document processing stages tracking
CREATE TABLE IF NOT EXISTS processing_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    stage_name VARCHAR(50) NOT NULL, -- 'preprocessing', 'ocr', 'llm_processing', 'validation', 'routing'
    status VARCHAR(50) NOT NULL, -- 'pending', 'processing', 'completed', 'failed'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    processing_time_ms INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Extraction results from each stage
CREATE TABLE IF NOT EXISTS extraction_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,
    raw_data JSONB,
    processed_data JSONB,
    confidence_score FLOAT,
    processing_time_ms INTEGER,
    model_used VARCHAR(100), -- Which NVIDIA model was used
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Quality scores and validation results
CREATE TABLE IF NOT EXISTS quality_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    overall_score FLOAT NOT NULL CHECK (overall_score >= 0 AND overall_score <= 5),
    completeness_score FLOAT NOT NULL CHECK (completeness_score >= 0 AND completeness_score <= 5),
    accuracy_score FLOAT NOT NULL CHECK (accuracy_score >= 0 AND accuracy_score <= 5),
    compliance_score FLOAT NOT NULL CHECK (compliance_score >= 0 AND compliance_score <= 5),
    quality_score FLOAT NOT NULL CHECK (quality_score >= 0 AND quality_score <= 5),
    decision VARCHAR(50) NOT NULL, -- 'APPROVE', 'REVIEW', 'REJECT', 'RESCAN'
    reasoning JSONB,
    issues_found JSONB DEFAULT '[]',
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    judge_model VARCHAR(100), -- Which judge model was used
    created_at TIMESTAMP DEFAULT NOW()
);

-- Document routing decisions
CREATE TABLE IF NOT EXISTS routing_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    routing_action VARCHAR(50) NOT NULL, -- 'auto_approve', 'flag_review', 'expert_review', 'reject'
    routing_reason TEXT,
    wms_integration_status VARCHAR(50), -- 'pending', 'integrated', 'failed'
    wms_integration_data JSONB,
    human_review_required BOOLEAN DEFAULT FALSE,
    human_reviewer_id INTEGER REFERENCES users(id),
    human_review_completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Document search and retrieval metadata
CREATE TABLE IF NOT EXISTS document_search_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    search_vector_id VARCHAR(100), -- Milvus vector ID
    embedding_model VARCHAR(100), -- 'nv-embedqa-e5-v5'
    extracted_text TEXT,
    key_entities JSONB DEFAULT '{}',
    document_summary TEXT,
    tags TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_processing_stage ON documents(processing_stage);
CREATE INDEX IF NOT EXISTS idx_documents_upload_timestamp ON documents(upload_timestamp);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);

CREATE INDEX IF NOT EXISTS idx_processing_stages_document_id ON processing_stages(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_stages_stage_name ON processing_stages(stage_name);
CREATE INDEX IF NOT EXISTS idx_processing_stages_status ON processing_stages(status);

CREATE INDEX IF NOT EXISTS idx_extraction_results_document_id ON extraction_results(document_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_stage ON extraction_results(stage);
CREATE INDEX IF NOT EXISTS idx_extraction_results_confidence ON extraction_results(confidence_score);

CREATE INDEX IF NOT EXISTS idx_quality_scores_document_id ON quality_scores(document_id);
CREATE INDEX IF NOT EXISTS idx_quality_scores_overall_score ON quality_scores(overall_score);
CREATE INDEX IF NOT EXISTS idx_quality_scores_decision ON quality_scores(decision);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_document_id ON routing_decisions(document_id);
CREATE INDEX IF NOT EXISTS idx_routing_decisions_routing_action ON routing_decisions(routing_action);

CREATE INDEX IF NOT EXISTS idx_document_search_document_id ON document_search_metadata(document_id);
CREATE INDEX IF NOT EXISTS idx_document_search_vector_id ON document_search_metadata(search_vector_id);

-- Create updated_at trigger function if it doesn't exist
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add updated_at triggers
CREATE TRIGGER update_documents_updated_at 
    BEFORE UPDATE ON documents 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE documents IS 'Stores uploaded documents and their metadata';
COMMENT ON TABLE document_operations IS 'Links documents to warehouse operations';
COMMENT ON TABLE processing_stages IS 'Tracks document processing pipeline stages';
COMMENT ON TABLE extraction_results IS 'Stores results from each processing stage';
COMMENT ON TABLE quality_scores IS 'Stores quality validation scores and decisions';
COMMENT ON TABLE routing_decisions IS 'Stores intelligent routing decisions';
COMMENT ON TABLE document_search_metadata IS 'Stores search and retrieval metadata for documents';
