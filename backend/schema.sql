-- Only additive extension tables; existing source data is never rebuilt.
CREATE TABLE IF NOT EXISTS match_task_evidence (
 task_id uuid PRIMARY KEY REFERENCES similarity_match_task(task_id),
 stage text NOT NULL,
 evidence jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE match_task_evidence IS '联调任务的输入、参数、计算分项、进度、失败原因及结果快照';
CREATE TABLE IF NOT EXISTS match_image (
 image_hash text PRIMARY KEY,
 image_bytes bytea NOT NULL,
 metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE match_image IS '四类气象PNG原图，按SHA256去重，元数据含日期及渲染版本';
CREATE TABLE IF NOT EXISTS match_image_review (
 cache_key text PRIMARY KEY,
 model_name text NOT NULL,
 request_metadata jsonb NOT NULL,
 raw_response jsonb NOT NULL,
 validated_review jsonb,
 created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE match_image_review IS '气象图多模态原始响应与校验结果；按模型、提示词、日期和输入图哈希缓存';
ALTER TABLE match_image_review ADD COLUMN IF NOT EXISTS response_history jsonb NOT NULL DEFAULT '[]'::jsonb;
COMMENT ON COLUMN match_image_review.response_history IS '每次模型调用的响应与HTTP状态，追加保留，重试不覆盖历史';
