import json
import unittest

from langgraph.checkpoint.memory import InMemorySaver

from backend.agent.graph import build_agent_graph, classify_intent_by_rules, route_for_intent
from backend.agent.runtime import encode_sse
from backend.agent.skills import ALLOWED_SKILLS, load_skill


class FakeModel:
    async def classify_intent(self, question):
        return None

    async def answer(self, skill_instructions, question, evidence):
        return f'已分析：{question}'


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return {'status': 'ok', 'tool': tool_name}


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def test_rule_intents_cover_business_questions(self):
        cases = {
            '明天哪些区域可能出现PM2.5污染？': 'pollution_risk',
            '这次过程什么时候达到峰值？': 'temporal_evolution',
            '浦东臭氧偏高是什么原因？': 'cause_analysis',
            '历史上有哪些相似过程和偏差？': 'historical_adjustment',
            'MDA8是什么意思？': 'professional_knowledge',
            '高湿为什么促进颗粒物累积？': 'professional_knowledge',
            '查看任务进度': 'system_operation',
        }
        for question, expected in cases.items():
            self.assertEqual(classify_intent_by_rules(question), expected)
        self.assertEqual(route_for_intent('professional_knowledge', '相对湿度如何影响污染？'), 'meteorology')

    def test_skills_have_versioned_metadata_and_evals(self):
        for name in ALLOWED_SKILLS:
            skill = load_skill(name)
            self.assertEqual(skill.name, name)
            self.assertEqual(skill.version, '1.0.0')
            self.assertTrue(skill.instructions)
            eval_file = __import__('pathlib').Path('skills') / name / 'evals' / 'evals.json'
            payload = json.loads(eval_file.read_text(encoding='utf-8'))
            self.assertGreaterEqual(len(payload['evals']), 3)

    async def test_matching_question_routes_through_mcp_and_explanation_skill(self):
        gateway = FakeGateway()
        graph = build_agent_graph(InMemorySaver(), gateway=gateway, model=FakeModel())
        result = await graph.ainvoke(
            {
                'question': '为什么这个历史案例是第一名？',
                'task_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                'conversation_id': 'test-thread',
                'evidence': [],
            },
            config={'configurable': {'thread_id': 'test-thread'}},
        )
        self.assertEqual(result['intent'], 'historical_adjustment')
        self.assertEqual(result['skill_name'], 'match-result-explanation')
        self.assertEqual([call[0] for call in gateway.calls], [
            'similarity_get_task_result', 'similarity_search_historical_candidates',
        ])
        self.assertIn('已分析', result['answer'])

    def test_sse_uses_named_event_and_json_payload(self):
        event = encode_sse('progress', {'message': '正在分析'})
        self.assertTrue(event.startswith('event: progress\n'))
        self.assertIn('"message":"正在分析"', event)
        self.assertTrue(event.endswith('\n\n'))


if __name__ == '__main__':
    unittest.main()
