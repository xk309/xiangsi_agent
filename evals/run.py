"""python -m evals.run [--mode live --task-id UUID] [--output PATH]."""
import argparse
import asyncio
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter

from backend.agent.contracts import AgentRequest
from backend.agent.harness import AgentHarness
from backend.agent.team_graph import PROMPT_VERSION
from backend.config import settings
from evals.replay import ReplayGateway, ReplayKnowledge, ReplayModel, TASK_ID


async def evaluate(mode='mock', task_id=None):
    payload = Path(__file__).with_name('cases.json').read_bytes()
    dataset = json.loads(payload)
    results = []
    with tempfile.TemporaryDirectory() as directory:
        configuration = replace(settings, agent_store_path=Path(directory) / 'runs.sqlite3')
        harness = AgentHarness(configuration, ReplayModel() if mode == 'mock' else None,
                               ReplayGateway() if mode == 'mock' else None,
                               ReplayKnowledge() if mode == 'mock' else None)
        try:
            for case in dataset['cases']:
                started = perf_counter()
                run = await harness.create(AgentRequest(question=case['question'],
                    task_id=(TASK_ID if mode == 'mock' else task_id) if case['has_task'] else None))
                await harness.active[run['run_id']]
                completed = harness.store.get(run['run_id'])
                result = completed['result']
                reports = result.get('reports', [])
                citations_valid = all(set(finding['evidence_ids']).issubset({item['evidence_id'] for item in report['evidence']})
                    for report in reports for finding in report['findings'])
                events = harness.store.events(run['run_id'])
                checks = {
                    'expected_specialists': {report['specialist_name'] for report in reports} == set(case['specialists']),
                    'citation_integrity': citations_valid,
                    'single_terminal_event': sum(event['event_type'] == 'run_finished' for event in events) == 1,
                    'budget_respected': result['usage']['tool_calls'] <= configuration.agent_max_tool_calls
                        and result['usage']['model_calls'] <= configuration.agent_max_model_calls,
                    'not_failed': completed['status'] in ('completed', 'partial'),
                }
                if mode == 'mock' and not case['has_task']:
                    checks['missing_evidence_handled'] = not any(report['findings'] for report in reports)
                results.append({'case_id': case['id'], 'passed': all(checks.values()), 'checks': checks,
                                'seconds': round(perf_counter() - started, 3), 'status': completed['status'],
                                'usage': result['usage']})
        finally:
            await harness.stop()
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    source_digest = sha256()
    root = Path(__file__).resolve().parents[1]
    for directory in ('backend', 'mcp_server', 'skills', 'evals'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.md', '.json'):
                source_digest.update(str(path.relative_to(root)).replace('\\', '/').encode())
                source_digest.update(path.read_bytes())
    return {'mode': mode, 'dataset_version': dataset['version'], 'dataset_hash': sha256(payload).hexdigest(),
            'prompt_version': PROMPT_VERSION, 'code_revision': revision,
            'source_hash': source_digest.hexdigest(),
            'model': 'deterministic replay' if mode == 'mock' else settings.agent_model_name,
            'passed': sum(result['passed'] for result in results), 'total': len(results), 'cases': results,
            'limitation': '工程回归，不等于Top3命中率或RAG专业正确率；真实语义需要专家标注。'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Evaluation Harness：固定五类问题、路由、引用、预算和终态验证')
    parser.add_argument('--mode', choices=['mock', 'live'], default='mock')
    parser.add_argument('--task-id')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if args.mode == 'live' and not args.task_id:
        parser.error('live模式需要真实--task-id，会调用配置的模型及MCP服务')
    report = asyncio.run(evaluate(args.mode, args.task_id))
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
        if baseline['mode'] != report['mode'] or baseline['dataset_hash'] != report['dataset_hash']:
            parser.error('只能比较同模式、同数据集的评测')
        report['passed_delta'] = report['passed'] - baseline['passed']
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf-8')
    print(output)
    raise SystemExit(0 if report['passed'] == report['total'] else 1)
