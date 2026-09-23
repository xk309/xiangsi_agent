from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.config import ROOT


SKILLS_ROOT = ROOT / 'skills'
ALLOWED_SKILLS = {
    'pollution-similarity-review',
    'meteorology-image-review',
    'match-result-explanation',
}


@dataclass(frozen=True)
class AgentSkill:
    name: str
    version: str
    description: str
    instructions: str


def load_skill(name: str) -> AgentSkill:
    if name not in ALLOWED_SKILLS:
        raise ValueError(f'未注册的Skill: {name}')
    skill_file = SKILLS_ROOT / name / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    if not text.startswith('---\n'):
        raise ValueError(f'{name} 缺少YAML头信息')
    _, frontmatter, instructions = text.split('---', 2)
    metadata = yaml.safe_load(frontmatter)
    if metadata.get('name') != name:
        raise ValueError(f'{name} 的name与目录不一致')
    return AgentSkill(
        name=name,
        version=str(metadata.get('version', '1.0.0')),
        description=str(metadata['description']),
        instructions=instructions.strip(),
    )
