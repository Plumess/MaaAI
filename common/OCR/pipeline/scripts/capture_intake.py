"""Import original screenshot packages without inventing labels or evaluation eligibility."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import shutil
import tempfile
from PIL import Image
from file_utils import sha

FIELDS=['file','session_id','source_group','captured_at','client','language','scene','theme','game_version','maa_version','emulator','width','height','capture_kind','related_frame','task','notes']
KINDS={'game_original','maa_resized','roi_crop','unknown'}
LANGUAGES={'Official':'zh-CN','Bilibili':'zh-CN','YoStarEN':'en','YoStarJP':'ja','YoStarKR':'ko','txwy':'zh-TW'}


def inspect_package(package):
    with (package/'capture-index.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        missing=set(FIELDS)-set(reader.fieldnames or [])
        if missing:raise ValueError('missing CSV columns: '+','.join(sorted(missing)))
        rows=list(reader)
    if not rows:raise ValueError('empty capture package')
    records=[];names=set()
    for number,row in enumerate(rows):
        for key in ['file','session_id','source_group','client','language','scene','capture_kind']:
            if not row.get(key):raise ValueError(f'row {number+1}: missing {key}')
        name=row['file'].replace('\\','/');row['file']=name
        row['related_frame']=row['related_frame'].replace('\\','/')
        file=(package/name).resolve()
        if not file.is_relative_to(package.resolve()):raise ValueError('image outside package')
        if name in names:raise ValueError('duplicate image entry')
        names.add(name)
        if row['capture_kind'] not in KINDS:raise ValueError('unknown capture_kind')
        if row['client'] in LANGUAGES and row['language']!=LANGUAGES[row['client']]:raise ValueError('client/language mismatch')
        with Image.open(file) as im:
            if im.format!='PNG':raise ValueError('original PNG required; do not convert to hide compression')
            im.load();width,height=im.size;rgb=im.convert('RGB')
            pixels=hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
        for key,value in [('width',width),('height',height)]:
            if row.get(key) and int(row[key])!=value:raise ValueError('declared image dimensions differ')
        record={**row,'id':f'capture-{number:05d}','source_file':name,'image':f'images/{number:05d}.png',
                'width':width,'height':height,'sha256':sha(file),'pixel_sha256':pixels,
                'annotation_status':'unreviewed','split':'unassigned','formal_evaluation_eligible':False,
                'capture_provenance':'provider declaration; original-vs-resized requires verification'}
        records.append(record)
    for row in records:
        if row['related_frame'] and row['related_frame'] not in names:raise ValueError('related frame absent from package')
    # Link whole sessions, source groups, duplicate pixels and original/crop pairs.
    parent=list(range(len(records)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):parent[find(a)]=find(b)
    seen={};index={r['source_file']:i for i,r in enumerate(records)}
    for i,row in enumerate(records):
        for key in [('session',row['session_id']),('source',row['source_group']),('pixels',row['pixel_sha256'])]:
            if key in seen:union(i,seen[key])
            else:seen[key]=i
        if row['related_frame']:union(i,index[row['related_frame']])
    for i,row in enumerate(records):row['leakage_group']=f'capture-group-{find(i):05d}'
    return records


def import_package(package,output):
    if output.exists():raise FileExistsError('choose a new capture version')
    records=inspect_package(package)
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.capture-',dir=output.parent))
    try:
        (staging/'images').mkdir()
        for row in records:
            shutil.copy2(package/row['source_file'],staging/row['image'])
            if sha(staging/row['image'])!=row['sha256']:raise ValueError('source changed while copying')
        (staging/'manifest.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
        shutil.copy2(package/'capture-index.csv',staging/'capture-index.csv')
        with (staging/'review.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['id','image','scene','review_status','text_boxes_json','reviewer','notes']);w.writeheader()
            for row in records:w.writerow({'id':row['id'],'image':row['image'],'scene':row['scene'],'review_status':'pending','text_boxes_json':'[]','notes':'Do not use OCR output alone as truth.'})
        cards=[]
        for r in records:
            e=html.escape
            cards.append(f'<article><h2>{e(r["id"])} · {e(r["scene"])}</h2><img src="{r["image"]}"><p>{e(r["language"])} / {e(r["theme"] or "主题待确认")} / {e(r["capture_kind"])}</p><p>{e(r["notes"])}</p></article>')
        (staging/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>截图待复核</title><style>body{font-family:system-ui;margin:24px;background:#eef2f7}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:20px}article{background:white;padding:18px}img{width:100%}h2{font-size:18px}</style><h1>截图待复核</h1><p>图片保持原始像素；标签未确认，未分配训练或评判用途。review.csv记录文字框与答案。</p><main>'+''.join(cards)+'</main>')
        report={'samples':len(records),'unique_pixels':len({r['pixel_sha256'] for r in records}),
                'duplicate_image_files':len(records)-len({r['pixel_sha256'] for r in records}),
                'leakage_groups':len({r['leakage_group'] for r in records}),'all_annotations_pending':True,
                'evaluation_eligible':False,'script_sha256':sha(Path(__file__)),
                'files':{str(p.relative_to(staging)):sha(p) for p in staging.rglob('*') if p.is_file()}}
        (staging/'intake-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        staging.rename(output)
        return report
    finally:
        if staging.exists():shutil.rmtree(staging)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=import_package(a.package,a.output);print(json.dumps({k:v for k,v in r.items() if k!='files'},ensure_ascii=False))
if __name__=='__main__':main()
