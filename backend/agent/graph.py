from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import AgentIntent, AgentState
from backend.agent.knowledge import KnowledgeRepository
from backend.agent.mcp_gateway import McpGateway
from backend.agent.model_client import AgentModelClient
from backend.agent.skills import load_skill


WEATHER_WORDS = ('气象', '天气', '温度', '降水', '风', '湿度', '环流', '高压', '低压', '边界层', '逆温')


def classify_intent_by_rules(question: str) -> AgentIntent:
    if any(word in question for word in ('创建任务', '任务进度', '打开图片', '查看结果', '重新匹配')):
        return 'system_operation'
    if any(word in question for word in ('历史案例', '相似过程', '偏差', '调高', '调低', '调整建议', 'Top3', '第一名')):
        return 'historical_adjustment'
    if any(word in question for word in ('什么时候', '哪天最高', '峰值', '持续多久', '变化趋势', '如何发展')):
        return 'temporal_evolution'
    if any(word in question for word in ('什么是', '是什么意思', '区别', '原理', '如何影响')):
        return 'professional_knowledge'
    if '为什么' in question and not any(word in question for word in ('今天', '明天', '当前', '这次', '本次')):
        return 'professional_knowledge'
    if any(word in question for word in ('为什么', '原因', '成因', '输送', '扩散', '累积')):
        return 'cause_analysis'
    if any(word in question for word in ('今天', '明天', '区域', '污染风险', '污染物', '空气质量')):
        return 'pollution_risk'
    return 'unknown'


def route_for_intent(intent: AgentIntent, question: str) -> str:
    if intent in ('pollution_risk', 'temporal_evolution'):
        return 'pollution'
    if intent == 'cause_analysis':
        return 'meteorology'
    if intent in ('historical_adjustment', 'system_operation'):
        return 'matching'
    if intent == 'professional_knowledge':
        return 'meteorology' if any(word in question for word in WEATHER_WORDS) else 'pollution'
    return 'unknown'


def build_agent_graph(
    checkpointer: Any,
    gateway: McpGateway | None = None,
    model: AgentModelClient | None = None,
    knowledge: KnowledgeRepository | None = None,
):
    gateway = gateway or McpGateway()
    model = model or AgentModelClient()
    knowledge = knowledge or KnowledgeRepository()

    async def recognize_intent(state: AgentState) -> dict[str, Any]:
        intent = await model.classify_intent(state['question'])
        intent = intent or classify_intent_by_rules(state['question'])
        return {'intent': intent, 'route': route_for_intent(intent, state['question'])}

    async def gather_pollution(state: AgentState) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        if state.get('task_id'):
            evidence.append(await gateway.call('similarity_get_task_result', {'task_id': state['task_id']}))
        elif state['intent'] != 'professional_knowledge':
            evidence.append({'status': 'missing_context', 'message': '未提供当前匹配任务。'})
        if state['intent'] == 'professional_knowledge':
            evidence.append(await knowledge.search('pollution', state['question']))
        return {'evidence': evidence, 'skill_name': 'pollution-similarity-review'}

    async def gather_meteorology(state: AgentState) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        if state.get('task_id'):
            evidence.append(await gateway.call('similarity_get_task_result', {'task_id': state['task_id']}))
            evidence.append(await gateway.call('similarity_get_weather_images', {'task_id': state['task_id']}))
        elif state['intent'] != 'professional_knowledge':
            evidence.append({'status': 'missing_context', 'message': '未提供当前匹配任务。'})
        if state['intent'] == 'professional_knowledge':
            evidence.append(await knowledge.search('meteorology', state['question']))
        return {'evidence': evidence, 'skill_name': 'meteorology-image-review'}

    async def gather_matching(state: AgentState) -> dict[str, Any]:
        if not state.get('task_id'):
            evidence = [{'status': 'missing_context', 'message': '需要先选择或创建一个匹配任务。'}]
        else:
            evidence = [
                await gateway.call('similarity_get_task_result', {'task_id': state['task_id']}),
                await gateway.call('similarity_search_historical_candidates', {
                    'task_id': state['task_id'], 'limit': 3, 'offset': 0,
                }),
            ]
        return {'evidence': evidence, 'skill_name': 'match-result-explanation'}

    async def analyze(state: AgentState) -> dict[str, Any]:
        skill = load_skill(state['skill_name'])
        evidence = [
            {'skill': skill.name, 'skill_version': skill.version},
            *state.get('evidence', []),
        ]
        answer = await model.answer(skill.instructions, state['question'], evidence)
        if not answer:
            statuses = [str(item.get('message', item.get('status', ''))) for item in evidence[1:]]
            answer = '；'.join(item for item in statuses if item) or '已取得任务证据，模型未配置，暂不生成分析结论。'
        return {'evidence': evidence, 'answer': answer}

    async def answer_unknown(state: AgentState) -> dict[str, Any]:
        return {
            'answer': '我目前可以回答污染风险、时空演变、成因分析、历史相似案例、偏差建议和专业知识问题。请补充日期、区域、污染物或匹配任务。',
            'evidence': [],
        }

    def build_domain_subgraph(gather_node, name: str):
        graph = StateGraph(AgentState)
        graph.add_node('gather', gather_node)
        graph.add_node('analyze', analyze)
        graph.add_edge(START, 'gather')
        graph.add_edge('gather', 'analyze')
        graph.add_edge('analyze', END)
        return graph.compile(), name

    pollution_graph, pollution_name = build_domain_subgraph(gather_pollution, 'pollution')
    meteorology_graph, meteorology_name = build_domain_subgraph(gather_meteorology, 'meteorology')
    matching_graph, matching_name = build_domain_subgraph(gather_matching, 'matching')

    async def run_pollution(state: AgentState) -> dict[str, Any]:
        result = await pollution_graph.ainvoke(state)
        return {key: result[key] for key in ('skill_name', 'evidence', 'answer')}

    async def run_meteorology(state: AgentState) -> dict[str, Any]:
        result = await meteorology_graph.ainvoke(state)
        return {key: result[key] for key in ('skill_name', 'evidence', 'answer')}

    async def run_matching(state: AgentState) -> dict[str, Any]:
        result = await matching_graph.ainvoke(state)
        return {key: result[key] for key in ('skill_name', 'evidence', 'answer')}

    graph = StateGraph(AgentState)
    graph.add_node('recognize_intent', recognize_intent)
    graph.add_node(pollution_name, run_pollution)
    graph.add_node(meteorology_name, run_meteorology)
    graph.add_node(matching_name, run_matching)
    graph.add_node('unknown', answer_unknown)
    graph.add_edge(START, 'recognize_intent')
    graph.add_conditional_edges(
        'recognize_intent',
        lambda state: state['route'],
        {'pollution': pollution_name, 'meteorology': meteorology_name, 'matching': matching_name, 'unknown': 'unknown'},
    )
    for node_name in (pollution_name, meteorology_name, matching_name, 'unknown'):
        graph.add_edge(node_name, END)
    return graph.compile(checkpointer=checkpointer)
