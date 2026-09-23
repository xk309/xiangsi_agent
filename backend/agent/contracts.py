from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from uuid import UUID


AgentIntent = Literal[
    'pollution_risk',
    'temporal_evolution',
    'cause_analysis',
    'historical_adjustment',
    'professional_knowledge',
    'system_operation',
    'unknown',
]


class AgentState(TypedDict, total=False):
    question: str
    task_id: str | None
    conversation_id: str
    intent: AgentIntent
    route: Literal['pollution', 'meteorology', 'matching', 'unknown']
    skill_name: str
    evidence: list[dict[str, Any]]
    answer: str


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=2000, description='预报员输入的问题')
    task_id: str | None = Field(default=None, description='当前匹配任务UUID，可为空')
    conversation_id: str | None = Field(default=None, max_length=100, description='对话标识；事件续接使用run_id')

    @field_validator('task_id', 'conversation_id')
    @classmethod
    def validate_identifier(cls, value):
        return str(UUID(value)) if value else None


class AgentAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action_type: Literal['call_tool', 'finish']
    tool_name: str = Field(default='', max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_finish(self):
        if self.action_type == 'finish' and (self.tool_name or self.arguments):
            raise ValueError('finish动作不接受工具名、分析内容或参数')
        return self


class Finding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=1600)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class SpecialistReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    specialist_name: str
    status: Literal['completed', 'partial', 'failed']
    findings: list[Finding] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=12)
