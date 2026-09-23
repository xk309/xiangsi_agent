"""Run lifecycle, cancellation, shared budgets and durable event replay."""
import asyncio
import json
from time import monotonic

from backend.agent.knowledge import KnowledgeRepository
from backend.agent.mcp_gateway import McpGateway
from backend.agent.middleware import RunBudget, ToolMiddleware
from backend.agent.model_client import AgentModelClient, ModelServiceError
from backend.agent.store import RunStore, TERMINAL
from backend.agent.team_graph import build_team_graph, PROMPT_VERSION
from backend.config import settings


class AgentHarness:
    def __init__(self, configuration=settings, model=None, gateway=None, knowledge=None, store=None):
        self.settings = configuration
        self.model = model or AgentModelClient()
        self.gateway = gateway or McpGateway()
        self.knowledge = knowledge or KnowledgeRepository()
        self.store = store or RunStore(configuration.agent_store_path)
        self.active = {}
        self.is_started = False
        self.model_semaphore = asyncio.Semaphore(3)

    def start(self):
        if not self.is_started:
            self.store.start()
            self.is_started = True

    async def stop(self):
        tasks = list(self.active.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.active.clear()
        self.is_started = False

    async def create(self, request):
        self.start()
        if len(self.active) >= self.settings.agent_max_active_runs:
            raise ValueError('当前分析任务较多，请稍后再试。')
        run = self.store.create(request)
        task = asyncio.create_task(self._execute(run))
        self.active[run['run_id']] = task
        task.add_done_callback(lambda completed: self.active.pop(run['run_id'], None))
        return run

    async def cancel(self, run_id):
        run = self.store.get(run_id)
        if run['status'] not in TERMINAL:
            task = self.active.get(run_id)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            # Also covers cancellation before the coroutine had its first turn.
            self.store.finish(run_id, 'cancelled', {'answer': '分析已取消；已有匹配结果不受影响。'})
        return self.store.get(run_id)

    async def _execute(self, run):
        run_id = run['run_id']
        reports = []
        token_usage = {'input_tokens': 0, 'output_tokens': 0}
        budget = RunBudget(monotonic() + self.settings.agent_timeout_seconds,
                           self.settings.agent_max_model_calls, self.settings.agent_max_tool_calls)

        async def emit(kind, data):
            if kind == 'specialist_completed':
                reports.append(data)
            if kind == 'model_response':
                token_usage['input_tokens'] += int(data.get('usage', {}).get('prompt_tokens', 0))
                token_usage['output_tokens'] += int(data.get('usage', {}).get('completion_tokens', 0))
            self.store.append(run_id, kind, data)

        def result(**kwargs):
            return {'reports': list(reports), 'usage': {'model_calls': budget.model_calls, 'tool_calls': budget.tool_calls, **token_usage},
                    'prompt_version': PROMPT_VERSION, 'model_name': self.settings.agent_model_name, **kwargs}

        self.store.mark_running(run_id)
        await emit('run_started', {'conversation_id': run['conversation_id'], 'task_id': run['task_id']})
        try:
            async with asyncio.timeout(self.settings.agent_timeout_seconds):
                if run['task_id']:
                    await budget.reserve('tool')
                    snapshot = await asyncio.wait_for(self.gateway.call('similarity_get_analysis_snapshot', {'task_id': run['task_id']}),
                                                      budget.remaining(self.settings.agent_tool_timeout_seconds))
                    if snapshot.get('status') == 'ok' and snapshot.get('task_id') != run['task_id']:
                        raise ValueError('任务快照归属不匹配')
                else:
                    snapshot = {'status': 'missing_context', 'message': '未选择匹配任务；仅可进行已配置知识库的专业问答。'}
                await emit('snapshot_loaded', {'snapshot_version': snapshot.get('snapshot_version'), 'status': snapshot.get('status')})
                middleware = ToolMiddleware(snapshot, budget, self.knowledge, emit, self.settings.agent_tool_timeout_seconds)
                history = self.store.history(run['conversation_id'], run['task_id'], run_id)
                graph = build_team_graph(self.model, middleware, budget, emit, self.settings, history, self.model_semaphore)
                state = await graph.ainvoke({'question': run['question']})
                status = 'completed' if reports and all(report['status'] == 'completed' for report in reports) else 'partial'
                if reports and all(report['status'] == 'failed' for report in reports):
                    status = 'failed'
                self.store.finish(run_id, status, result(answer=state['answer'], intent=state['intent'],
                                                       snapshot_version=snapshot.get('snapshot_version')))
        except asyncio.CancelledError:
            self.store.finish(run_id, 'cancelled', result(answer='分析已取消；已有匹配结果不受影响。'))
            raise
        except TimeoutError:
            self.store.finish(run_id, 'timed_out', result(answer='分析达到时限，已完成专家报告可在下方查看。'))
        except Exception as error:
            message = str(error) if isinstance(error, ModelServiceError) else f'分析未完成（{type(error).__name__}），请检查模型与证据服务配置。'
            self.store.finish(run_id, 'failed', result(answer=message))

    async def stream_events(self, run_id, after=0):
        self.store.get(run_id)
        last_heartbeat = monotonic()
        while True:
            # Read status first so a completion between reads cannot lose its final event.
            status = self.store.get(run_id)['status']
            for event in self.store.events(run_id, after):
                after = event['event_id']
                payload = json.dumps(event['payload'], ensure_ascii=False, default=str)
                yield f"id: {after}\nevent: {event['event_type']}\ndata: {payload}\n\n"
            if status in TERMINAL:
                return
            if monotonic() - last_heartbeat > 10:
                yield ': keep-alive\n\n'
                last_heartbeat = monotonic()
            await asyncio.sleep(0.15)


agent_harness = AgentHarness()
