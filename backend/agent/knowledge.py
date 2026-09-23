"""Published-document retrieval, with explicit keyword/hybrid modes."""
import asyncio
import math
import re
from typing import Literal
import httpx
from backend.config import settings
from backend.database import query

KnowledgeDomain = Literal['pollution', 'meteorology']


def query_terms(text):
    terms = []
    for word in re.findall(r'[A-Za-z0-9.]+|[\u4e00-\u9fff]+', text):
        if re.fullmatch(r'[\u4e00-\u9fff]+', word):
            terms.extend(word[index:index + 2] for index in range(max(1, len(word) - 1)))
        else:
            terms.append(word.lower())
    return list(dict.fromkeys(terms))[:24]


def reciprocal_rank_fusion(*rankings, limit=10):
    scores, documents = {}, {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            identifier = str(item['chunk_id'])
            scores[identifier] = scores.get(identifier, 0.0) + 1 / (60 + rank)
            documents[identifier] = item
    return [{**documents[key], 'retrieval_score': scores[key]} for key in sorted(scores, key=lambda key: (-scores[key], key))[:limit]]


class KnowledgeModels:
    async def embed(self, texts):
        if not settings.embedding_model or not settings.model_api_key:
            raise ValueError('Embedding模型未配置')
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.model_base_url + '/embeddings',
                headers={'Authorization': 'Bearer ' + settings.model_api_key},
                json={'model': settings.embedding_model, 'input': texts, 'dimensions': settings.embedding_dimensions})
            response.raise_for_status()
        items = sorted(response.json()['data'], key=lambda item: item['index'])
        vectors = [item['embedding'] for item in items]
        if len(vectors) != len(texts) or any(len(vector) != settings.embedding_dimensions or not all(math.isfinite(float(x)) for x in vector) for vector in vectors):
            raise ValueError('Embedding返回数量或维度无效')
        return vectors

    async def rerank(self, question, items):
        # Contract: {model,query,documents,top_n} -> results[{index,relevance_score}].
        if not settings.reranker_url or not settings.reranker_model:
            return items, False
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.reranker_url,
                headers={'Authorization': 'Bearer ' + settings.model_api_key},
                json={'model': settings.reranker_model, 'query': question,
                      'documents': [item['content'] for item in items], 'top_n': len(items)})
            response.raise_for_status()
        ranking = response.json()['results']
        indexes = [item['index'] for item in ranking]
        if len(indexes) != len(items) or set(indexes) != set(range(len(items))):
            raise ValueError('Reranker返回索引无效')
        return [{**items[item['index']], 'rerank_score': float(item['relevance_score'])} for item in ranking], True


class KnowledgeRepository:
    def __init__(self, database_query=query, models=None):
        self.query = database_query
        self.models = models or KnowledgeModels()

    async def search(self, domain: KnowledgeDomain, query: str, limit: int = 5):
        if domain not in ('pollution', 'meteorology') or not 1 <= limit <= 10 or not 2 <= len(query) <= 500:
            raise ValueError('知识检索范围或参数无效')
        if not settings.knowledge_enabled:
            return {'status': 'not_configured', 'domain': domain, 'items': [], 'message': '知识库尚未启用；需导入已审核资料。'}
        try:
            fields = '''SELECT c.chunk_id,c.content,c.source_locator,d.title,d.source_uri,d.source_version
                FROM knowledge_chunk c JOIN knowledge_document d USING(document_id)
                WHERE d.status='PUBLISHED' AND d.domain=%s'''
            terms = query_terms(query)
            patterns = ['%' + term + '%' for term in terms]
            keyword = await asyncio.to_thread(self.query, fields + ''' AND c.content ILIKE ANY(%s)
                ORDER BY (SELECT count(*) FROM unnest(%s::text[]) AS term WHERE c.content ILIKE term) DESC,
                c.chunk_id LIMIT 30''', (domain, patterns, patterns))
            keyword.sort(key=lambda item: -sum(item['content'].lower().count(term) for term in terms))
            vectors = []
            if settings.knowledge_use_vectors:
                vector = (await self.models.embed([query]))[0]
                vectors = await asyncio.to_thread(self.query, fields + ''' AND c.embedding IS NOT NULL
                    AND c.embedding_model=%s AND vector_dims(c.embedding)=%s
                    ORDER BY c.embedding <=> %s::vector LIMIT 30''',
                    (domain, settings.embedding_model, settings.embedding_dimensions, str(vector)))
            items = reciprocal_rank_fusion(keyword[:30], vectors)
            if not items:
                return {'status': 'empty', 'domain': domain, 'items': [], 'message': '已发布资料中没有检索到依据。'}
            items, reranked = await self.models.rerank(query, items)
            return {'status': 'ok', 'domain': domain, 'items': items[:limit],
                    'retrieval_mode': 'hybrid_rrf' if settings.knowledge_use_vectors else 'keyword',
                    'is_reranked': reranked, 'message': '专业知识不是当前污染过程的实测证据。'}
        except Exception as error:
            return {'status': 'unavailable', 'domain': domain, 'items': [],
                    'message': f'知识检索未完成（{type(error).__name__}），请检查资料、数据库扩展及模型配置。'}
