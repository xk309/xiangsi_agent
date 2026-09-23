from dataclasses import replace
import unittest
from unittest.mock import patch
from backend.agent.knowledge import KnowledgeRepository, reciprocal_rank_fusion, query_terms
from backend.agent.ingest_knowledge import split_document
from backend.config import settings


class KnowledgeTests(unittest.IsolatedAsyncioTestCase):
    def test_rrf_rewards_agreement_without_duplicates(self):
        a, b, c = [{'chunk_id': name} for name in ('a', 'b', 'c')]
        result = reciprocal_rank_fusion([a, b], [b, c])
        self.assertEqual(result[0]['chunk_id'], 'b')
        self.assertEqual(len(result), 3)

    def test_real_splitter_preserves_chinese_sections(self):
        text = '# 扩散条件\n\n' + '逆温会抑制垂直混合。' * 300
        chunks = split_document(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 900 for chunk in chunks))
        self.assertIn('逆温', query_terms('什么是逆温'))

    async def test_keyword_search_filters_published_domain_and_retains_sources(self):
        calls = []
        def query(sql, parameters):
            calls.append((sql, parameters))
            return [{'chunk_id': 'a', 'content': '逆温抑制垂直混合', 'title': '审核资料',
                     'source_uri': 'internal:weather', 'source_locator': '第二章', 'source_version': 'v1'}]
        configuration = replace(settings, knowledge_enabled=True, knowledge_use_vectors=False, reranker_url='')
        with patch('backend.agent.knowledge.settings', configuration):
            result = await KnowledgeRepository(query).search('meteorology', '逆温')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['items'][0]['source_locator'], '第二章')
        self.assertIn("d.status='PUBLISHED'", calls[0][0])
        self.assertEqual(calls[0][1][0], 'meteorology')

    async def test_disabled_and_unavailable_are_explicit(self):
        with patch('backend.agent.knowledge.settings', replace(settings, knowledge_enabled=False)):
            self.assertEqual((await KnowledgeRepository().search('pollution', '臭氧'))['status'], 'not_configured')
        def broken(*args):
            raise RuntimeError('private secret')
        with patch('backend.agent.knowledge.settings', replace(settings, knowledge_enabled=True)):
            result = await KnowledgeRepository(broken).search('pollution', '臭氧')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('private secret', str(result))
