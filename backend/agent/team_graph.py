"""Three specialist subgraphs, selected by a LangGraph orchestration graph."""
import asyncio
import re
from hashlib import sha256
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agent.context import build_context
from backend.agent.contracts import AgentAction, SpecialistReport
from backend.agent.graph import classify_intent_by_rules, route_for_intent
from backend.agent.middleware import SPECIALIST_TOOLS, TOOL_DESCRIPTIONS
from backend.agent.skills import load_skill
from backend.agent.model_client import model_response_sink

SKILLS = {'pollution': 'pollution-similarity-review', 'meteorology': 'meteorology-image-review',
          'matching': 'match-result-explanation'}
TITLES = {'pollution': '污染过程', 'meteorology': '气象背景', 'matching': '案例与偏差'}
PROMPT_VERSION = 'bounded-specialists-v1'


class TeamState(TypedDict, total=False):
    question: str
    intent: str
    specialists: list[str]
    reports: list[dict]
    answer: str


class SpecialistState(TypedDict, total=False):
    evidence: list[dict]
    round_count: int
    action: Any
    should_stop: bool
    limitations: list[str]
    report: dict


def select_specialists(question, intent):
    if intent == 'unknown':
        return []
    primary = route_for_intent(intent, question)
    selected = {primary} if primary != 'unknown' else set()
    if intent not in ('professional_knowledge', 'system_operation'):
        if any(word in question for word in ('污染风险', '哪些区域', '峰值', '污染情况')):
            selected.add('pollution')
        if any(word in question.replace('风险', '') for word in ('天气', '气象', '成因', '扩散', '风', '湿度')):
            selected.add('meteorology')
        if any(word.lower() in question.lower() for word in ('历史', '偏差', '相似', 'top3', '调整')):
            selected.add('matching')
    return [name for name in TITLES if name in selected]


def build_team_graph(model, middleware, budget, emit, settings, history, semaphore):
    async def model_call(method, *args):
        async def trace_response(data):
            await emit('model_response', {'operation': method.__name__, **data})
        for attempt in range(2):
            await budget.reserve('model')
            async with semaphore:
                token = model_response_sink.set(trace_response)
                try:
                    return await asyncio.wait_for(method(*args), budget.remaining(settings.model_timeout_seconds))
                except ValueError:
                    await emit('model_response_rejected', {'operation': method.__name__, 'attempt': attempt + 1})
                    if attempt:
                        raise
                finally:
                    model_response_sink.reset(token)

    def specialist_graph(name, question):
        skill = load_skill(SKILLS[name])
        skill_metadata = {'name': skill.name, 'version': skill.version,
                          'hash': sha256(skill.instructions.encode()).hexdigest()}

        def context(state):
            return build_context(question, history, state.get('evidence', []), settings.agent_context_characters)

        async def prepare_context(state):
            await emit('specialist_started', {'specialist': name, 'title': TITLES[name], 'skill': skill_metadata})
            return {'evidence': [], 'round_count': 0, 'limitations': [], 'should_stop': False}

        async def decide_next_action(state):
            used = {item['tool'] for item in state['evidence']}
            action = await model_call(model.decide_action, skill.instructions, context(state),
                                      {tool: TOOL_DESCRIPTIONS[tool] for tool in SPECIALIST_TOOLS[name] if tool not in used})
            if action is None:
                return {'should_stop': True, 'limitations': ['模型未启用或未配置，暂不生成专业结论。']}
            await emit('action_selected', {'specialist': name, 'action': action.model_dump(),
                                           'round': state['round_count'] + 1, 'prompt_version': PROMPT_VERSION})
            return {'action': action, 'should_stop': action.action_type == 'finish',
                    'round_count': state['round_count'] + 1}

        async def execute_tool(state):
            try:
                item = await middleware.execute(name, state['action'])
                return {'evidence': [*state['evidence'], item]}
            except ValueError as error:
                return {'should_stop': True, 'limitations': [str(error)]}

        async def observe_result(state):
            return {'should_stop': state.get('should_stop', False) or state['round_count'] >= settings.agent_max_rounds}

        async def write_report(state):
            prepared = context(state)
            unavailable = [item for item in prepared['evidence']
                           if item['data'].get('status', 'ok') != 'ok']
            # Missing-data records describe a limitation, not a citable business finding.
            prepared['evidence'] = [item for item in prepared['evidence']
                                    if item['data'].get('status', 'ok') == 'ok']
            prepared['data_limitations'] = [
                {'tool': item['tool'], 'status': item['data'].get('status'),
                 'message': item['data'].get('message', '数据不可用，不能据此生成业务结论。')}
                for item in unavailable]
            available = {item['evidence_id'] for item in prepared['evidence']
                         if item['data'].get('status', 'ok') == 'ok'}
            report = None
            if available:
                prepared['allowed_evidence_ids'] = sorted(available)
                async def validated_report():
                    response = await model.write_report(name, skill.instructions, prepared)
                    if response is not None:
                        if response.specialist_name != name:
                            raise ValueError('专家响应身份不匹配')
                        if any(not set(finding.evidence_ids).issubset(available) for finding in response.findings):
                            prepared['validation_hint'] = '上一响应引用无效。只能逐字复制allowed_evidence_ids中的ID。'
                            raise ValueError('回答引用了未提供或不可用的证据')
                    return response
                report = await model_call(validated_report)
            if report is None:
                report = SpecialistReport(specialist_name=name, status='partial',
                                          limitations=['没有可用于专业回答的证据或模型响应。'])
            if report.specialist_name != name:
                raise ValueError('专家响应身份不匹配')
            for finding in report.findings:
                if not set(finding.evidence_ids).issubset(available):
                    raise ValueError('回答引用了未提供或不可用的证据')
            final_scores = [float(item['final_score']) for item in middleware.snapshot.get('task', {}).get('top3', [])
                            if item.get('final_score') is not None]
            accepted = []
            for finding in report.findings:
                claimed_scores = re.findall(r'(?<!图像)(?:最终(?:综合)?(?:分数|评分|得分|分)|综合(?:评分|得分|分数|分)|final_score)[^0-9]{0,12}(\d+(?:\.\d+)?)', finding.text)
                if any(not any(abs(float(score) - actual) <= 0.1 for actual in final_scores) for score in claimed_scores):
                    report.limitations.append('一条模型结论混淆了最终分与分项分，程序已移除；以页面正式评分为准。')
                else:
                    accepted.append(finding)
            report.findings = accepted
            if not report.findings:
                report.status = 'partial'
            report.limitations.extend(state.get('limitations', []))
            report.limitations.extend(
                f"{item['tool']}：{item['message']}" for item in prepared['data_limitations'])
            if prepared['omitted_evidence_ids']:
                report.limitations.append('部分资料超过上下文预算，未参与本轮生成。')
            if state['round_count'] >= settings.agent_max_rounds:
                report.limitations.append('已达到专家动作轮数上限。')
            if report.limitations:
                report.status = 'partial'
            result = {**report.model_dump(), 'evidence': state['evidence'], 'skill': skill_metadata,
                      'round_count': state['round_count']}
            await emit('specialist_completed', result)
            return {'report': result}

        graph = StateGraph(SpecialistState)
        for node in (prepare_context, decide_next_action, execute_tool, observe_result, write_report):
            graph.add_node(node.__name__, node)
        graph.add_edge(START, 'prepare_context')
        graph.add_edge('prepare_context', 'decide_next_action')
        graph.add_conditional_edges('decide_next_action', lambda state: 'write_report' if state['should_stop'] else 'execute_tool')
        graph.add_edge('execute_tool', 'observe_result')
        graph.add_conditional_edges('observe_result', lambda state: 'write_report' if state['should_stop'] else 'decide_next_action')
        graph.add_edge('write_report', END)
        return graph.compile()

    async def recognize_intent(state):
        intent = None
        try:
            intent = await model_call(model.classify_intent, state['question'])
        except (TimeoutError, ValueError):
            pass
        return {'intent': intent or classify_intent_by_rules(state['question'])}

    async def build_analysis_plan(state):
        specialists = select_specialists(state['question'], state['intent'])
        await emit('analysis_plan', {'intent': state['intent'], 'specialists': specialists})
        return {'specialists': specialists}

    async def run_specialists(state):
        async def run_one(name):
            try:
                result = await specialist_graph(name, state['question']).ainvoke({}, {'recursion_limit': 40})
                return result['report']
            except asyncio.CancelledError:
                raise
            except Exception as error:
                report = {'specialist_name': name, 'status': 'failed', 'findings': [],
                          'limitations': [f'本专家未能完成（{type(error).__name__}），请重试或检查配置。'], 'evidence': []}
                await emit('specialist_completed', report)
                return report
        return {'reports': await asyncio.gather(*(run_one(name) for name in state['specialists']))}

    async def validate_findings(state):
        # The result contains immutable algorithm evidence; no model writes scores or ranks.
        return {'reports': state.get('reports', [])}

    async def compose_answer(state):
        parts = []
        for report in state.get('reports', []):
            parts.append(TITLES[report['specialist_name']])
            parts.extend(f"{item['text']} [{', '.join(item['evidence_ids'])}]" for item in report['findings'])
            parts.extend('说明：' + item for item in report['limitations'])
        if not parts:
            parts = ['请补充日期、污染物或匹配任务。支持污染风险、时空演变、成因、历史案例与偏差、专业知识五类问题。']
        parts.append('以上仅供预报员参考，不自动调整正式预报。')
        return {'answer': '\n\n'.join(parts)}

    graph = StateGraph(TeamState)
    nodes = (recognize_intent, build_analysis_plan, run_specialists, validate_findings, compose_answer)
    previous = START
    for node in nodes:
        graph.add_node(node.__name__, node)
        graph.add_edge(previous, node.__name__)
        previous = node.__name__
    graph.add_edge(previous, END)
    return graph.compile()
