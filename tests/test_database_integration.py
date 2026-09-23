"""Opt-in database checks. All extension/schema/fixture writes are rolled back."""
from dataclasses import replace
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from backend.database import connection
from backend.config import settings
from backend.agent.knowledge import KnowledgeRepository


@unittest.skipUnless(os.getenv('RUN_DATABASE_INTEGRATION') == '1', '设置RUN_DATABASE_INTEGRATION=1运行数据库回滚测试')
class DatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_published_hybrid_retrieval_against_real_pgvector(self):
        with connection() as database:
            try:
                with database.cursor() as cursor:
                    schema = 'agent_test_' + uuid4().hex
                    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
                    cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                    cursor.execute(sql.SQL('SET LOCAL search_path TO {}, public').format(sql.Identifier(schema)))
                    cursor.execute((Path(__file__).parents[1] / 'backend/knowledge_schema.sql').read_text(encoding='utf-8'))
                    for domain, status, content in [('meteorology', 'PUBLISHED', '逆温会抑制垂直混合'),
                                                    ('meteorology', 'DRAFT', '逆温草稿禁止引用'),
                                                    ('pollution', 'PUBLISHED', '逆温跨领域材料')]:
                        document_id = str(uuid4())
                        cursor.execute('''INSERT INTO knowledge_document(document_id,domain,title,source_version,status)
                            VALUES(%s,%s,%s,'test-v1',%s)''', (document_id, domain, content, status))
                        cursor.execute('''INSERT INTO knowledge_chunk(chunk_id,document_id,chunk_index,content,source_locator,embedding_model,embedding)
                            VALUES(%s,%s,0,%s,'第一节','test-embedding','[1,0,0]')''', (str(uuid4()), document_id, content))

                def database_query(statement, parameters):
                    with database.cursor(cursor_factory=RealDictCursor) as cursor:
                        cursor.execute(statement, parameters)
                        return [dict(row) for row in cursor.fetchall()]

                class TestModels:
                    async def embed(self, texts):
                        return [[1, 0, 0] for _ in texts]

                    async def rerank(self, question, items):
                        return items, False

                configuration = replace(settings, knowledge_enabled=True, knowledge_use_vectors=True,
                                        embedding_model='test-embedding', embedding_dimensions=3)
                with patch('backend.agent.knowledge.settings', configuration):
                    result = await KnowledgeRepository(database_query, TestModels()).search('meteorology', '逆温')
                self.assertEqual(result['status'], 'ok', result)
                self.assertEqual(result['retrieval_mode'], 'hybrid_rrf')
                self.assertEqual(len(result['items']), 1)
                self.assertEqual(result['items'][0]['content'], '逆温会抑制垂直混合')
            finally:
                database.rollback()
