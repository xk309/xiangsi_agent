"""Bounded context with explicit provenance; never silently truncate JSON."""
import json


def build_context(question, history, evidence, character_limit):
    context = {'question': question, 'recent_questions': history,
               'used_tools': list(dict.fromkeys(item.get('tool', '') for item in evidence)),
               'evidence': [], 'omitted_evidence_ids': []}
    for item in evidence:
        trial = {**context, 'evidence': [*context['evidence'], item]}
        if len(json.dumps(trial, ensure_ascii=False, default=str)) <= character_limit - 1000:
            context['evidence'].append(item)
        else:
            context['omitted_evidence_ids'].append(item['evidence_id'])
    return context
