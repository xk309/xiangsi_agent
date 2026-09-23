"""Scope, budget, deadline, context and result checks shared by all specialists."""
import asyncio
from dataclasses import dataclass, field
from hashlib import sha256
import json
from time import monotonic

from backend.agent.contracts import AgentAction


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class RunBudget:
    deadline: float
    max_models: int = 16
    max_tools: int = 12
    model_calls: int = 0
    tool_calls: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def reserve(self, kind):
        async with self.lock:
            if monotonic() >= self.deadline:
                raise TimeoutError('分析超过总时限')
            attribute, maximum = ('model_calls', self.max_models) if kind == 'model' else ('tool_calls', self.max_tools)
            if getattr(self, attribute) >= maximum:
                raise BudgetExceeded('已达到本次分析调用预算')
            setattr(self, attribute, getattr(self, attribute) + 1)

    def remaining(self, maximum):
        return max(0.001, min(maximum, self.deadline - monotonic()))


SPECIALIST_TOOLS = {
    'pollution': ('get_task', 'get_pollution', 'search_knowledge'),
    'meteorology': ('get_task', 'get_weather', 'get_reviews', 'search_knowledge'),
    'matching': ('get_task', 'get_candidates', 'get_residuals', 'get_reviews'),
}
TOOL_DESCRIPTIONS = {
    'get_task': '读取同版本任务状态、日期、正式Top3和固定权重；参数为空',
    'get_pollution': '读取当前逐日九宫格污染物预测；不等于行政区；参数为空',
    'get_weather': '读取当前逐日气象均值和标签；参数为空',
    'get_reviews': '读取已校验多模态复核证据及图片引用；参数为空',
    'get_candidates': '读取最多10个候选的分项得分；参数为空',
    'get_residuals': '读取历史实况减预测的残差和适用限制；参数为空',
    'search_knowledge': '检索本专业已发布资料；参数query为2至500字字符串',
}


class ToolMiddleware:
    def __init__(self, snapshot, budget, knowledge, emit, tool_timeout):
        self.snapshot = snapshot
        self.budget = budget
        self.knowledge = knowledge
        self.emit = emit
        self.tool_timeout = tool_timeout
        self.seen = set()

    async def execute(self, specialist, action: AgentAction):
        if action.tool_name not in SPECIALIST_TOOLS[specialist]:
            raise ValueError('工具不在本专家白名单中')
        arguments = action.arguments
        if action.tool_name == 'search_knowledge':
            if set(arguments) != {'query'} or not isinstance(arguments['query'], str) or not 2 <= len(arguments['query']) <= 500:
                raise ValueError('知识检索参数无效')
        elif arguments:
            raise ValueError('证据工具固定使用当前任务，禁止传入其他任务或任意参数')
        key = (specialist, action.tool_name, json.dumps(arguments, sort_keys=True))
        if key in self.seen:
            raise ValueError('重复调用没有新增证据，已停止本专家循环')
        self.seen.add(key)
        await self.budget.reserve('tool')
        if action.tool_name == 'search_knowledge':
            result = await asyncio.wait_for(self.knowledge.search(specialist, arguments['query']), self.budget.remaining(self.tool_timeout))
        elif self.snapshot.get('status') != 'ok':
            result = {'status': self.snapshot.get('status', 'unavailable'),
                      'message': self.snapshot.get('message', '任务证据不可用')}
        else:
            result = self.snapshot.get(action.tool_name.removeprefix('get_'), {'status': 'missing'})
        evidence_id = specialist + '-' + sha256(json.dumps([action.tool_name, arguments, result], sort_keys=True, default=str).encode()).hexdigest()[:12]
        evidence = {'evidence_id': evidence_id, 'tool': action.tool_name,
                    'snapshot_version': self.snapshot.get('snapshot_version'), 'data': result}
        await self.emit('tool_completed', {'specialist': specialist, 'tool': action.tool_name,
                                         'evidence_id': evidence_id, 'status': result.get('status', 'ok')})
        return evidence
