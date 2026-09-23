-- Apply manually only after the vector extension and embedding dimensions are approved.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_document (
 document_id uuid PRIMARY KEY,
 domain text NOT NULL CHECK (domain IN ('pollution','meteorology')),
 title text NOT NULL,
 source_uri text,
 source_version text NOT NULL,
 status text NOT NULL CHECK (status IN ('DRAFT','PUBLISHED','RETIRED')),
 published_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(domain,title,source_version)
);

CREATE TABLE IF NOT EXISTS knowledge_chunk (
 chunk_id uuid PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES knowledge_document(document_id),
 chunk_index integer NOT NULL,
 content text NOT NULL,
 source_locator text,
 embedding_model text,
 embedding vector,
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(document_id,chunk_index)
);

COMMENT ON TABLE knowledge_document IS '经审核的污染物和气象知识文档；仅PUBLISHED状态可被智能体检索';
COMMENT ON TABLE knowledge_chunk IS '知识文档分块、来源定位和向量；向量维度由后续Embedding模型决定';
