import asyncio
from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from backend.config import settings
from mcp_server import tools


READ_ONLY = {
    'readOnlyHint': True,
    'destructiveHint': False,
    'idempotentHint': True,
    'openWorldHint': False,
}
mcp = FastMCP('similarity_match_mcp', host=settings.mcp_host, port=settings.mcp_port)


class PageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    limit: int = Field(default=20, ge=1, le=50, description='本次最多返回数量')
    offset: int = Field(default=0, ge=0, description='从第几条开始返回')


class TaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    task_id: str = Field(min_length=36, max_length=36, description='匹配任务UUID')


class CandidateInput(TaskInput):
    history_start_date: date = Field(description='历史候选开始日期，格式YYYY-MM-DD')


class CandidatePageInput(TaskInput, PageInput):
    pass


class ReviewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    cache_key: str = Field(min_length=64, max_length=64, description='模型复核缓存键')


@mcp.tool(name='similarity_list_forecast_batches', annotations=READ_ONLY)
async def similarity_list_forecast_batches(params: PageInput) -> dict[str, Any]:
    """列出可用于相似度匹配的预测批次和日期，支持分页，不创建或修改任务。"""
    return await asyncio.to_thread(tools.list_forecast_batches, params.limit, params.offset)


@mcp.tool(name='similarity_get_task_result', annotations=READ_ONLY)
async def similarity_get_task_result(params: TaskInput) -> dict[str, Any]:
    """读取一个匹配任务的状态、日期、权重和Top3摘要，不返回大体量原始数组。"""
    return await asyncio.to_thread(tools.get_task_result, params.task_id)


@mcp.tool(name='similarity_search_historical_candidates', annotations=READ_ONLY)
async def similarity_search_historical_candidates(params: CandidatePageInput) -> dict[str, Any]:
    """分页读取任务的历史候选及其排名和分项摘要，只查询已有任务。"""
    return await asyncio.to_thread(tools.search_historical_candidates, params.task_id, params.limit, params.offset)


@mcp.tool(name='similarity_get_candidate_metrics', annotations=READ_ONLY)
async def similarity_get_candidate_metrics(params: CandidateInput) -> dict[str, Any]:
    """读取指定历史候选的污染物、气象、图像和最终评分证据。"""
    return await asyncio.to_thread(tools.get_candidate_metrics, params.task_id, params.history_start_date)


@mcp.tool(name='similarity_get_weather_images', annotations=READ_ONLY)
async def similarity_get_weather_images(params: TaskInput) -> dict[str, Any]:
    """读取当前窗口和Top3历史窗口的气象图片哈希及图片接口模板，不返回图片字节。"""
    return await asyncio.to_thread(tools.get_weather_images, params.task_id)


@mcp.tool(name='similarity_get_review_evidence', annotations=READ_ONLY)
async def similarity_get_review_evidence(params: ReviewInput) -> dict[str, Any]:
    """读取已校验的多模态复核结论和请求元数据，不返回密钥或任意数据库内容。"""
    return await asyncio.to_thread(tools.get_review_evidence, params.cache_key)


@mcp.tool(name='similarity_get_analysis_snapshot', annotations=READ_ONLY)
async def similarity_get_analysis_snapshot(params: TaskInput) -> dict[str, Any]:
    """一次读取并冻结任务版本、污染网格、气象摘要、候选、已校验图像复核和残差；不修改任务。"""
    return await asyncio.to_thread(tools.get_analysis_snapshot, params.task_id)


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
