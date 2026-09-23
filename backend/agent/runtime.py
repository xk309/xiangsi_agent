from contextlib import asynccontextmanager
import json
from typing import AsyncIterator
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from backend.agent.contracts import AgentRequest
from backend.agent.graph import build_agent_graph
from backend.config import settings


NODE_MESSAGES = {
    'recognize_intent': '正在识别问题类型',
    'pollution': '正在分析污染物数据',
    'meteorology': '正在分析气象条件',
    'matching': '正在读取相似过程与偏差证据',
    'unknown': '正在整理可支持的问题范围',
}


@asynccontextmanager
async def checkpoint_context():
    if not settings.agent_checkpoint_database_url:
        yield InMemorySaver()
        return
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    async with AsyncPostgresSaver.from_conn_string(settings.agent_checkpoint_database_url) as checkpointer:
        if settings.agent_checkpoint_auto_setup:
            await checkpointer.setup()
        yield checkpointer


class AgentRuntime:
    def __init__(self):
        self._checkpoint_manager = None
        self.graph = None

    async def start(self) -> None:
        if self.graph is not None:
            return
        self._checkpoint_manager = checkpoint_context()
        checkpointer = await self._checkpoint_manager.__aenter__()
        self.graph = build_agent_graph(checkpointer)

    async def stop(self) -> None:
        if self._checkpoint_manager is not None:
            await self._checkpoint_manager.__aexit__(None, None, None)
        self._checkpoint_manager = None
        self.graph = None

    async def stream(self, request: AgentRequest) -> AsyncIterator[str]:
        await self.start()
        conversation_id = request.conversation_id or str(uuid4())
        state = {
            'question': request.question,
            'task_id': request.task_id,
            'conversation_id': conversation_id,
            'evidence': [],
        }
        config = {'configurable': {'thread_id': conversation_id}}
        yield encode_sse('conversation', {'conversation_id': conversation_id})
        final_state = dict(state)
        async for update in self.graph.astream(state, config=config, stream_mode='updates'):
            for node_name, values in update.items():
                final_state.update(values)
                yield encode_sse('progress', {
                    'node': node_name,
                    'message': NODE_MESSAGES.get(node_name, '正在生成分析建议'),
                })
        yield encode_sse('answer', {
            'conversation_id': conversation_id,
            'intent': final_state.get('intent', 'unknown'),
            'answer': final_state.get('answer', ''),
            'evidence': final_state.get('evidence', []),
        })
        yield encode_sse('done', {'conversation_id': conversation_id})


def encode_sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str, separators=(',', ':'))
    return f'event: {event}\ndata: {payload}\n\n'


agent_runtime = AgentRuntime()
