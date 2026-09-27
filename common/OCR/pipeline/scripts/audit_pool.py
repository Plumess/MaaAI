"""Audit frozen pool expansion and report actual sampling exposure without training."""
import argparse,json
from collections import Counter
from pathlib import Path
from recipe_sampling import schedule
from routes import CLIENT
from file_utils import sha


def read_pool(path):
    audit=json.loads((path/'audit.json').read_text())
    if not audit['passed'] or audit['manifest_sha256']!=sha(path/'manifest.jsonl'):raise ValueError('pool audit mismatch')
    rows=[json.loads(s) for s in (path/'manifest.jsonl').read_text().splitlines()]
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate IDs')
    if len({r['pixel_sha256'] for r in rows})!=len(rows):raise ValueError('duplicate pixels')
    for r in rows:
        if sha(path/r['image'])!=r['sha256']:raise ValueError('image changed')
    return rows


def audit_pool(dataset,strategies,presentations,base=None):
    if not 1<=presentations<=10_000_000:raise ValueError('exposure budget exceeded')
    rows=read_pool(dataset);nested=None
    if base:
        old=read_pool(base);index={r['id']:r for r in rows}
        for r in old:
            if r['id'] not in index:raise ValueError('base sample missing')
            original={k:v for k,v in r.items() if k not in ['recipe_sha256','inherited_from']}
            added={k:v for k,v in index[r['id']].items() if k not in ['recipe_sha256','inherited_from']}
            if original!=added:raise ValueError('base sample changed')
        if {r['id'] for r in old if r['split']=='dev'}!={r['id'] for r in rows if r['split']=='dev'}:raise ValueError('development pool changed')
        nested={'base_manifest_sha256':sha(base/'manifest.jsonl'),'base_samples':len(old),'added_samples':len(rows)-len(old),'development_unchanged':True}
    result={'manifest_sha256':sha(dataset/'manifest.jsonl'),'samples':len(rows),'nested':nested,'routes':{},'formal_acceptance':False}
    for route,strategy in strategies.items():
        if route not in CLIENT:raise ValueError('unknown route')
        pool=[r for r in rows if r['split']=='train' and (r['route']=='CharOCR' if route=='char' else r['route']=='WordOCR' and r['language']==route)]
        _,exposure=schedule(pool,'char' if route=='char' else 'word',strategy,presentations)
        result['routes'][route]={'pool_images':len(pool),'active_pool_images':sum(r['scene'] in exposure['families'] for r in pool),'scene_counts':dict(Counter(r['scene'] for r in pool)),'exposure':exposure}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--base',type=Path);p.add_argument('--strategies',type=Path,required=True);p.add_argument('--presentations',type=int,default=16000);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit_pool(a.dataset,json.loads(a.strategies.read_text()),a.presentations,a.base)
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
