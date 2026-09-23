---
status: accepted
---

# RAG优先复用PolarDB pgvector

专业知识RAG优先使用现有PostgreSQL兼容PolarDB提供的`pgvector`，统一保存文档版本、分块、向量和引用，减少新增数据库及同步成本。向量访问封装在知识库接口后；如果权限、容量或压测不满足要求，可以切换独立向量库而不改变LangGraph流程。
