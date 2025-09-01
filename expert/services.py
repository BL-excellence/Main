# app/expert/services.py (exemple utilitaire)
import copy
from copy import deepcopy

def _rel_key(r):
    return (
        r.get('source',{}).get('type',''),
        r.get('source',{}).get('value',''),
        r.get('type',''),
        r.get('target',{}).get('type',''),
        r.get('target',{}).get('value',''),
    )

def _qa_key(q): return str(q.get('question','')).strip().lower()

def apply_expert_deltas(base_json, deltas_qs):
    data = copy.deepcopy(base_json or {})
    data.setdefault('relations', [])
    data.setdefault('questions_answers', [])

    # relations -> dictionnaire par clé unique
    rels = { _rel_key(r): r for r in data['relations'] }

    for d in deltas_qs.filter(active=True).order_by('created_at'):
        p = d.payload or {}

        for r in p.get('relations_added', []):
            rels[_rel_key(r)] = r

        for m in p.get('relations_modified', []):
            # {before:{...}, after:{...}}
            before = m.get('before') or {}
            after  = m.get('after') or {}
            rels.pop(_rel_key(before), None)
            if after:
                rels[_rel_key(after)] = after

        # Q&A
        for qa in p.get('qa_added', []):
            data['questions_answers'].append(qa)

        for mqa in p.get('qa_modified', []):
            # si tu as une clé de QA (ex question)
            q = (mqa.get('question') or '').strip()
            if not q:
                continue
            for i, qa in enumerate(data['questions_answers']):
                if (qa.get('question') or '').strip() == q:
                    data['questions_answers'][i] = mqa.get('after') or qa
                    break
            else:
                # si absente, on l’ajoute
                data['questions_answers'].append(mqa.get('after') or mqa)

    data['relations'] = list(rels.values())
    return data



