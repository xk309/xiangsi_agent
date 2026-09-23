# PolarDB 向量能力调研结论

调研日期：2026-09-17。以下结论仅依据阿里云官方文档。

## 结论

PolarDB 支持向量存储与相似度检索，但 PostgreSQL 版和 MySQL 版的实现、版本门槛不同。

本项目已经使用 PostgreSQL 兼容的 PolarDB，RAG 首选在现有集群启用 `pgvector`。这样可以用同一套数据库保存文档元数据、分块内容、向量和引用信息，减少额外部署与数据同步。正式采用前必须先核对引擎大版本、内核小版本及扩展启用权限；不满足条件或容量、并发压测不达标时，再使用独立向量数据库。

## PolarDB for PostgreSQL

官方提供 `PGVector` 扩展，可在 PolarDB 中存储和查询高维向量：

- 支持精确检索以及 `HNSW`、`IVFFlat` 近似最近邻索引。
- 支持欧氏距离（L2）、余弦距离和内积。
- 向量最高支持 16,000 维。
- 通过 `CREATE EXTENSION vector;` 启用，应用仍使用 PostgreSQL SQL 和事务能力。

官方当前列出的最低内核小版本为：

| PostgreSQL 大版本 | 最低 PolarDB 内核小版本 |
| --- | --- |
| 16 | `2.0.16.3.1.1` |
| 15 | `2.0.15.12.4.0` |
| 14 | `2.0.14.7.9.0` |
| 11 | `2.0.11.9.35.0` |

集群可执行 `SHOW polardb_version;` 检查内核小版本。不同引擎版本支持的 `pgvector` 扩展版本不同，应再按控制台的扩展兼容矩阵确认。

官方来源：[PGVector（向量检索）](https://www.alibabacloud.com/help/en/polardb/polardb-for-oracle/pgvector)

> 官方英文页面 URL 中保留了 `polardb-for-oracle`，但页面产品标题和导航明确为 **PolarDB for PostgreSQL (Compatible with Oracle)**。项目判断应以实际集群产品类型、引擎大版本和 `polardb_version` 为准，不能只看 URL 名称。

## PolarDB for MySQL

MySQL 版使用 `PolarVector/AISearch`，不是 `pgvector`：

- MySQL 协议路线提供内置 `VECTOR(N)` 类型、距离函数和向量索引，支持 SQL 与 ACID 事务。
- 基础向量能力和 HNSW 索引要求 PolarDB for MySQL `8.0.2`，内核小版本至少为 `8.0.2.2.30`。
- `FAISS_HNSW_FLAT`、`FAISS_HNSW_PQ` 要求至少 `8.0.2.2.31`；动态修改或删除向量索引要求至少 `8.0.2.2.32`。
- 向量索引依赖 IMCI 只读节点；官方相关 IMCI 文档将其放在 MySQL Enterprise Edition 8.0 条件下。因此不能把 MySQL 向量能力理解为所有 MySQL 版实例开箱即用，需核对具体 Edition、内核版本和是否可增加 IMCI 只读节点。
- 另有基于独立 PolarSearch 搜索节点的 OpenSearch 协议路线，适合全文、向量和标量混合检索，但它不是本项目现有 PostgreSQL 集群的直接扩展方案。

官方来源：

- [PolarVector vector search engine](https://www.alibabacloud.com/help/en/polardb/polardb-for-mysql/polarvector-vector-search-engine/)
- [Perform vector retrieval using the MySQL protocol](https://help.aliyun.com/en/polardb/polardb-for-mysql/vector-index-usage)
- [IMCI read-only node edition prerequisite](https://help.aliyun.com/en/polardb/polardb-for-mysql/user-guide/serverless-enables-auto-scaling-of-read-only-column-store-nodes)

## 本项目建议

1. 在现有 PostgreSQL 兼容 PolarDB 执行只读检查：`SELECT version();`、`SHOW polardb_version;`，并确认有权限执行 `CREATE EXTENSION vector;`。
2. 满足上表版本要求后，以 `pgvector` 建立 RAG 骨架；文档、分块、Embedding、来源页码和版本信息保存在同一集群。
3. 首版优先使用 HNSW，并用真实知识文件评测召回率、查询延迟、索引体积和写入成本；小数据量也可先精确检索建立效果基线。
4. 把向量存储封装在知识库接口之后。若生产压测、权限或内核版本不满足要求，可切换 Qdrant 等独立向量库，不影响上层 RAG 流程。

因此，对“PolarDB 是否支持向量化能力”的准确回答是：**支持；本项目现有 PostgreSQL 兼容 PolarDB 优先采用 `pgvector`，但需要先核实集群大版本、内核小版本和扩展权限。**
