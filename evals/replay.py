"""Deterministic model/tool doubles; these do NOT measure real-model accuracy."""
from backend.agent.contracts import AgentAction, Finding, SpecialistReport

TASK_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'


class ReplayKnowledge:
    async def search(self, domain, query, limit=5):
        return {'status': 'not_configured', 'domain': domain, 'items': [], 'message': '离线样例不提供专业资料。'}


class ReplayGateway:
    async def call(self, tool_name, arguments):
        return {'status': 'ok', 'task_id': arguments['task_id'], 'snapshot_version': 'offline-fixture-v1',
                'task': {'status': 'ok', 'is_formal_top3': False, 'task_status': 'PARTIALLY_COMPLETED'},
                'pollution': {'status': 'ok', 'daily_grids': [], 'limitation': '离线测试数据'},
                'weather': {'status': 'ok', 'daily_grid_means': [], 'limitation': '离线测试数据'},
                'candidates': {'status': 'ok', 'items': [], 'is_formal_top3': False},
                'reviews': {'status': 'missing', 'items': []},
                'residuals': {'status': 'missing', 'is_adjustment_enabled': False}}


class ReplayModel:
    async def classify_intent(self, question):
        return None

    async def decide_action(self, instructions, context, tools):
        if context['evidence']:
            return AgentAction(action_type='finish')
        name = next((name for name in ('get_pollution', 'get_weather', 'get_candidates') if name in tools), 'get_task')
        if any(word in context['question'] for word in ('什么是', '原理', '区别')) and 'search_knowledge' in tools:
            return AgentAction(action_type='call_tool', tool_name='search_knowledge', arguments={'query': context['question']})
        return AgentAction(action_type='call_tool', tool_name=name)

    async def write_report(self, specialist, instructions, context):
        return SpecialistReport(specialist_name=specialist, status='completed', findings=[
            Finding(text='离线回放已读取指定证据，不代表实际预报结论。', evidence_ids=[context['evidence'][0]['evidence_id']])])
