"""Compare paired MAA analyzer outputs; equality is not ground-truth accuracy."""
import argparse
import json
from pathlib import Path


def business(value):
    if isinstance(value, dict):
        return {k: business(v) for k, v in value.items() if k != 'score'}
    if isinstance(value, list):
        return [business(v) for v in value]  # Order/multiplicity can affect shop selection.
    return value


def index(document):
    result = {}
    for row in document['predictions']:
        if row['id'] in result:
            raise ValueError('duplicate case ID')
        if not isinstance(row.get('analyze_ok'), bool) or not row.get('mode'):
            raise ValueError('missing analyzer status/mode')
        result[row['id']] = row
    if not result:
        raise ValueError('empty replay')
    return result


def compare(official, candidate):
    for field in ['client', 'release']:
        if not official.get(field) or official[field] != candidate.get(field):
            raise ValueError(f'{field} mismatch or missing')
    left, right = index(official), index(candidate)
    if set(left) != set(right):
        raise ValueError('missing/extra cases; cannot compare partial results as complete')
    return [dict(id=key, business_equal_excluding_scores=business(left[key]) == business(right[key]),
                 official_analyze_ok=left[key]['analyze_ok'], candidate_analyze_ok=right[key]['analyze_ok']) for key in left]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('official', type=Path); p.add_argument('candidate', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    rows = compare(json.loads(a.official.read_text(encoding='utf-8-sig')), json.loads(a.candidate.read_text(encoding='utf-8-sig')))
    a.output.write_text(json.dumps({'cases':rows, 'accuracy_claim':False,
        'requirement':'Caller must verify same image hashes, task resources, binary, settings; review differences against truth.'}, ensure_ascii=False, indent=2)+'\n')
    raise SystemExit(0 if all(r['business_equal_excluding_scores'] for r in rows) else 1)


if __name__ == '__main__':
    main()
