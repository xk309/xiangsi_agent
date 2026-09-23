import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

import httpx

from backend.agent.contracts import AgentAction, AgentRequest
from backend.agent.context import build_context
from backend.agent.harness import AgentHarness
from backend.agent.middleware import RunBudget, ToolMiddleware, BudgetExceeded
from backend.agent.store import RunStore
from backend.agent.team_graph import select_specialists
from backend.config import settings
from evals.replay import ReplayGateway, ReplayKnowledge, ReplayModel, TASK_ID


class HarnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.configuration = replace(settings, agent_store_path=Path(self.temporary.name) / 'runs.sqlite3',
                                     agent_timeout_seconds=2, agent_max_active_runs=4)
        self.harness = AgentHarness(self.configuration, ReplayModel(), ReplayGateway(), ReplayKnowledge())
        self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()
        self.temporary.cleanup()

    async def complete(self, question, task_id=TASK_ID):
        run = await self.harness.create(AgentRequest(question=question, task_id=task_id))
        await self.harness.active[run['run_id']]
        return self.harness.store.get(run['run_id'])

    async def test_complex_question_runs_three_experts_with_shared_budget(self):
        run = await self.complete('明天哪些区域有污染风险，天气如何，历史案例偏差有什么参考？')
        self.assertEqual(run['status'], 'completed')
        self.assertEqual({item['specialist_name'] for item in run['result']['reports']}, {'pollution', 'meteorology', 'matching'})
        self.assertEqual(run['result']['usage']['tool_calls'], 4)
        self.assertEqual(run['result']['snapshot_version'], 'offline-fixture-v1')

    async def test_cancel_is_idempotent_and_only_one_terminal_event(self):
        started = asyncio.Event()
        async def slow(question):
            started.set()
            await asyncio.sleep(10)
        self.harness.model.classify_intent = slow
        run = await self.harness.create(AgentRequest(question='明天污染风险如何？'))
        await started.wait()
        await self.harness.cancel(run['run_id'])
        await self.harness.cancel(run['run_id'])
        self.assertEqual(self.harness.store.get(run['run_id'])['status'], 'cancelled')
        self.assertEqual(sum(item['event_type'] == 'run_finished' for item in self.harness.store.events(run['run_id'])), 1)

    async def test_deadline_stops_model_and_persists_terminal(self):
        self.harness.settings = replace(self.configuration, agent_timeout_seconds=0.05)
        async def slow(question):
            await asyncio.sleep(10)
        self.harness.model.classify_intent = slow
        run = await self.complete('明天污染风险如何？')
        self.assertEqual(run['status'], 'timed_out')

    async def test_unknown_citation_rejects_report(self):
        original = self.harness.model.write_report
        async def wrong(*args):
            report = await original(*args)
            report.findings[0].evidence_ids = ['fabricated']
            return report
        self.harness.model.write_report = wrong
        run = await self.complete('明天污染风险如何？')
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['result']['reports'][0]['findings'], [])

    async def test_one_failed_specialist_does_not_discard_other_reports(self):
        original = self.harness.model.write_report
        async def fail_matching(name, *args):
            if name == 'matching':
                raise RuntimeError('provider failure')
            return await original(name, *args)
        self.harness.model.write_report = fail_matching
        run = await self.complete('明天哪些区域有污染风险，天气如何，历史偏差如何？')
        self.assertEqual(run['status'], 'partial')
        reports = run['result']['reports']
        self.assertEqual(sum(report['status'] == 'completed' for report in reports), 2)

    async def test_final_score_not_supported_by_algorithm_is_removed(self):
        original = self.harness.model.write_report
        async def wrong_score(*args):
            report = await original(*args)
            report.findings[0].text = '最终综合分99.9，应当自动订正。'
            return report
        self.harness.model.write_report = wrong_score
        run = await self.complete('历史偏差如何？')
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(run['result']['reports'][0]['findings'], [])

    async def test_malformed_action_has_only_one_budgeted_retry(self):
        async def malformed(*args):
            raise ValueError('invalid JSON')
        self.harness.model.decide_action = malformed
        run = await self.complete('明天污染风险如何？')
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['result']['usage']['model_calls'], 3)

    async def test_run_capacity_is_enforced(self):
        self.harness.settings = replace(self.configuration, agent_max_active_runs=1)
        async def slow(*args):
            await asyncio.sleep(10)
        self.harness.model.classify_intent = slow
        run = await self.harness.create(AgentRequest(question='明天污染风险如何？'))
        with self.assertRaises(ValueError):
            await self.harness.create(AgentRequest(question='另一个问题'))
        await self.harness.cancel(run['run_id'])

    async def test_foreign_snapshot_rejected(self):
        async def foreign(*args):
            return {'status': 'ok', 'task_id': 'other'}
        self.harness.gateway.call = foreign
        run = await self.complete('明天污染风险如何？')
        self.assertEqual(run['status'], 'failed')

    async def test_missing_knowledge_produces_no_business_findings(self):
        run = await self.complete('什么是逆温？', None)
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(run['result']['reports'][0]['findings'], [])

    async def test_missing_residuals_are_limitations_not_citable_business_evidence(self):
        original = self.harness.model.write_report
        async def choose(instructions, context, tools):
            if 'get_task' in tools:
                return AgentAction(action_type='call_tool', tool_name='get_task')
            if 'get_residuals' in tools:
                return AgentAction(action_type='call_tool', tool_name='get_residuals')
            return AgentAction(action_type='finish')
        async def report(name, instructions, context):
            self.assertEqual(len(context['evidence']), 1)
            self.assertEqual(context['evidence'][0]['tool'], 'get_task')
            self.assertEqual(context['data_limitations'][0]['tool'], 'get_residuals')
            self.assertEqual(context['data_limitations'][0]['status'], 'missing')
            return await original(name, instructions, context)
        self.harness.model.decide_action = choose
        self.harness.model.write_report = report
        run = await self.complete('历史案例偏差如何？')
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(len(run['result']['reports'][0]['findings']), 1)
        self.assertTrue(any('get_residuals' in item for item in run['result']['reports'][0]['limitations']))

    async def test_scope_and_duplicate_calls_are_enforced(self):
        async def emit(*args):
            pass
        middleware = ToolMiddleware({}, RunBudget(monotonic() + 10), None, emit, 1)
        for action in [AgentAction(action_type='call_tool', tool_name='execute_sql'),
                       AgentAction(action_type='call_tool', tool_name='get_task', arguments={'task_id': 'other'})]:
            with self.assertRaises(ValueError):
                await middleware.execute('pollution', action)
        action = AgentAction(action_type='call_tool', tool_name='get_task')
        await middleware.execute('pollution', action)
        with self.assertRaisesRegex(ValueError, '重复'):
            await middleware.execute('pollution', action)

    async def test_shared_budget_cannot_be_overspent(self):
        budget = RunBudget(monotonic() + 10, max_tools=2)
        values = await asyncio.gather(*(budget.reserve('tool') for _ in range(6)), return_exceptions=True)
        self.assertEqual(budget.tool_calls, 2)
        self.assertEqual(sum(isinstance(item, BudgetExceeded) for item in values), 4)

    async def test_event_replay_and_restart_interruption(self):
        run = await self.complete('明天污染风险如何？')
        events = self.harness.store.events(run['run_id'])
        chunks = [item async for item in self.harness.stream_events(run['run_id'], events[-2]['event_id'])]
        self.assertEqual(len(chunks), 1)
        self.assertIn('run_finished', chunks[0])
        pending = self.harness.store.create(AgentRequest(question='未开始问题'))
        restarted = RunStore(self.configuration.agent_store_path)
        restarted.start()
        self.assertEqual(restarted.get(pending['run_id'])['status'], 'interrupted')

    async def test_history_is_scoped_to_task(self):
        run = await self.complete('明天污染风险如何？')
        store = self.harness.store
        self.assertEqual(store.history(run['conversation_id'], None, ''), [])
        self.assertEqual(store.history(run['conversation_id'], TASK_ID, ''), [run['question']])

    async def test_http_create_read_replay_cancel_and_invalid_input(self):
        from backend.main import app
        with patch('backend.main.agent_harness', self.harness):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/agent/runs', json={'question': '明天污染风险如何？', 'task_id': TASK_ID})
                self.assertEqual(response.status_code, 202)
                run_id = response.json()['run_id']
                if run_id in self.harness.active:
                    await self.harness.active[run_id]
                fetched = await client.get(f'/api/agent/runs/{run_id}')
                self.assertEqual(fetched.json()['status'], 'completed')
                streamed = await client.get(f'/api/agent/runs/{run_id}/events', headers={'Last-Event-ID': '1'})
                self.assertIn('run_finished', streamed.text)
                self.assertNotIn('id: 1\n', streamed.text)
                cancelled = await client.post(f'/api/agent/runs/{run_id}/cancel')
                self.assertEqual(cancelled.json()['status'], 'completed')
                invalid = await client.post('/api/agent/runs', json={'question': '有效问题', 'task_id': 'bad'})
                self.assertEqual(invalid.status_code, 422)

    def test_context_omission_preserves_complete_evidence_objects(self):
        items = [{'evidence_id': 'a', 'data': {'text': '长' * 10000}}, {'evidence_id': 'b', 'data': {'ok': True}}]
        context = build_context('问题', [], items, 2500)
        self.assertEqual(context['omitted_evidence_ids'], ['a'])
        self.assertEqual(context['evidence'], [items[1]])

    def test_five_business_routes(self):
        self.assertEqual(select_specialists('明天污染风险如何？', 'pollution_risk'), ['pollution'])
        self.assertEqual(select_specialists('什么是逆温？', 'professional_knowledge'), ['meteorology'])
        self.assertEqual(select_specialists('天气扩散原因', 'cause_analysis'), ['meteorology'])
        self.assertEqual(select_specialists('历史偏差', 'historical_adjustment'), ['matching'])
