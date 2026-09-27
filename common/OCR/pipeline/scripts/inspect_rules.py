"""Inspect actual released task inheritance and postprocessing, without inference."""
import argparse,json
from pathlib import Path
from doctor import inspect
from evaluate import invoke
from routes import CLIENT
from file_utils import sha
from workspace import ROOT, RT
from workspace import RELEASE,RELEASE_TAG

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--route',choices=CLIENT,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not inspect(ROOT/'configs/runtime.lock.json')['passed']:raise ValueError('released runtime changed')
    cases=json.loads(a.input.read_text())
    if not cases or len({r['id'] for r in cases})!=len(cases):raise ValueError('empty or duplicate rule cases')
    a.output.mkdir(parents=True,exist_ok=False);tasks=a.output/'tasks.json';tasks.write_text(json.dumps(sorted({r['task'] for r in cases})))
    source=a.output/'inputs.json';source.write_bytes(a.input.read_bytes());release=RELEASE
    invoke([RT/'build/maa_task_contract',release,CLIENT[a.route],tasks,a.output/'contract.json'],a.output/'contract.log')
    contract=json.loads((a.output/'contract.json').read_text())
    if contract['unresolved'] or contract['non_ocr_count']:raise ValueError('unresolved or non-OCR task')
    invoke([RT/'build/ocr_rules_probe',release,CLIENT[a.route],source,a.output/'rules.json'],a.output/'rules.log')
    provenance={'input_sha256':sha(source),'release':RELEASE_TAG,'client':CLIENT[a.route],'inference_run':False,'rules_modified':False,
                'files':{str(f.relative_to(RT)):sha(f) for f in [release/'libMaaCore.so',RT/'build/maa_task_contract',RT/'build/ocr_rules_probe',*(release/'resource').rglob('*.json')]}}
    (a.output/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
