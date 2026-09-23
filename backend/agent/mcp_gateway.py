import json
from typing import Any

from backend.config import settings


class McpGateway:
    """Small MCP client boundary used by LangGraph nodes."""

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            return {'status': 'unavailable', 'message': 'MCP依赖尚未安装。'}
        try:
            async with streamable_http_client(settings.mcp_server_url) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, {'params': arguments})
            if getattr(result, 'isError', False):
                return {'status': 'error', 'message': 'MCP工具执行失败，请核对任务及参数。'}
            structured = getattr(result, 'structuredContent', None)
            if structured:
                return dict(structured)
            for item in getattr(result, 'content', []):
                text = getattr(item, 'text', None)
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {'status': 'ok', 'text': text}
            return {'status': 'empty', 'message': 'MCP工具未返回可读取内容。'}
        except Exception as error:
            return {
                'status': 'unavailable',
                'message': f'MCP服务暂不可用（{type(error).__name__}）。',
            }
