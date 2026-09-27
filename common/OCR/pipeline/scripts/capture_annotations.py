"""Offline review of supplied 1280x720 MAA frames; no automatic label confirmation."""
import argparse,base64,json
from pathlib import Path
from urllib.parse import urlparse,unquote
from collections import Counter
from file_utils import sha

HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OCR 截图文字复核</title>
<style>body{margin:0;background:#eef2f7;color:#183047;font:15px/1.5 system-ui}header{position:sticky;top:0;background:white;padding:12px 22px;border-bottom:1px solid #ccd5e0;z-index:2}button,select,input{font:inherit;padding:6px;margin:4px}main{padding:18px}.layout{display:grid;grid-template-columns:minmax(650px,2fr) minmax(340px,1fr);gap:18px}.image{position:relative;align-self:start;background:#222}.image img{width:100%;display:block}.image svg{position:absolute;inset:0;width:100%;height:100%;touch-action:none}rect{fill:transparent;stroke:#ffbc37;stroke-width:2;cursor:pointer}rect.active{stroke:#00f9b8;stroke-width:4}table{width:100%;background:white;border-collapse:collapse}td{border-bottom:1px solid #ddd;padding:8px}input.text{width:90%}.selected{background:#e0efff}.note{color:#526278}.toolbar{display:flex;align-items:center;flex-wrap:wrap}#panel{max-height:75vh;overflow:auto}@media(max-width:1050px){.layout{display:block}.image{margin-bottom:20px}}</style>
<header><b>截图文字复核 · 全部仅用于开发校准</b><div class="toolbar"><select id="frame"></select><input id="reviewer" placeholder="复核者姓名/代号"><button id="hide">显示/隐藏候选文字</button><button id="add">拖框补充漏检区域</button><button id="save">下载复核 JSON</button><label>载入进度 <input type="file" id="load" accept="application/json"></label><span id="status"></span></div><div class="note">内部核对工具：由助手先检查原图，只将少量疑难项交给用户。黄色框是机器候选，不是已确认答案；原图已内嵌，可离线查看。人工确认须明确操作；不自动保存，也不上传。</div></header>
<main><p id="scene"></p><div class="layout"><div class="image"><img id="image" alt="原始 MAA 输入截图"><p id="image-error" hidden>原图未能显示，请使用浏览器直接打开此 HTML 文件；也可在对话中查看截图。</p><svg id="boxes" viewBox="0 0 1280 720"></svg></div><div id="panel"><table id="rows"></table></div></div></main>
<script id="payload" type="application/json">__PAYLOAD__</script><script id="embedded-images" type="application/json">__IMAGES__</script><script>
const data=JSON.parse(document.getElementById('payload').textContent);let index=0,selected=null,hidden=true,adding=false,start=null;
const $=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
const embeddedImages=JSON.parse($('embedded-images').textContent);
$('image').onerror=()=>{$('image-error').hidden=false};$('image').onload=()=>{$('image-error').hidden=true};
for(const [i,f] of data.frames.entries()){let o=document.createElement('option');o.value=i;o.textContent=f.id+' · '+(f.title||f.scene);$('frame').append(o)}
function counts(){let all=data.frames.flatMap(f=>f.regions);$('status').textContent=all.filter(r=>r.review_status==='confirmed').length+' 已确认 / '+all.length+' 候选'}
function render(){const f=data.frames[index];$('image-error').hidden=true;$('image').src=embeddedImages[f.id];$('scene').textContent=f.id+' / '+(f.title||f.scene)+' / '+f.theme+'；本图 '+f.regions.length+' 个候选。';$('boxes').replaceChildren();$('rows').replaceChildren();
for(const r of f.regions){let rect=document.createElementNS(ns,'rect');for(const [k,v] of Object.entries({x:r.box_xywh[0],y:r.box_xywh[1],width:r.box_xywh[2],height:r.box_xywh[3]}))rect.setAttribute(k,v);if(r.id===selected)rect.classList.add('active');rect.onclick=()=>{selected=r.id;render();document.getElementById(r.id)?.scrollIntoView({block:'nearest'})};$('boxes').append(rect);
let tr=document.createElement('tr');tr.id=r.id;if(r.id===selected)tr.className='selected';let td=document.createElement('td');let info=document.createElement('div');info.textContent=r.id+' · ['+r.box_xywh.join(',')+']';td.append(info);let text=document.createElement('input');text.className='text';text.value=hidden?(r.confirmed_label??''):(r.confirmed_label??r.proposed_label);text.placeholder=hidden?'先看图：点击“显示候选文字”或直接填写':'图片中的完整文字';text.onchange=()=>{r.confirmed_label=text.value;r.review_status='pending';render()};td.append(text);let state=document.createElement('select');for(const [v,n] of [['pending','待复核'],['confirmed','确认文字与框'],['rejected','排除：错框/非文字']]){let o=document.createElement('option');o.value=v;o.textContent=n;state.append(o)}state.value=r.review_status;state.onchange=()=>{if(state.value==='confirmed'&&!$('reviewer').value.trim()){alert('先填写复核者');state.value=r.review_status;return}if(state.value==='confirmed'&&hidden&&r.confirmed_label==null){alert('请填写文字，或显示候选后核对；不可在候选不可见时直接确认。');state.value=r.review_status;return}if(state.value==='confirmed'&&!(r.confirmed_label??r.proposed_label??'').trim()){alert('确认文字不能为空');state.value=r.review_status;return}r.review_status=state.value;r.reviewer=$('reviewer').value.trim();if(state.value==='confirmed')r.confirmed_label=r.confirmed_label??r.proposed_label;counts()};td.append(state);tr.append(td);$('rows').append(tr)}counts()}
$('frame').onchange=e=>{index=+e.target.value;selected=null;render()};$('hide').onclick=()=>{hidden=!hidden;render()};$('add').onclick=()=>{adding=!adding;$('add').textContent=adding?'正在补框：拖动原图区域':'拖框补充漏检区域'};
function point(e){let b=$('boxes').getBoundingClientRect();return [Math.max(0,Math.min(1280,(e.clientX-b.left)*1280/b.width)),Math.max(0,Math.min(720,(e.clientY-b.top)*720/b.height))]}
$('boxes').onpointerdown=e=>{if(adding){start=point(e);$('boxes').setPointerCapture(e.pointerId)}};$('boxes').onpointerup=e=>{if(!adding||!start)return;let end=point(e),x=Math.round(Math.min(start[0],end[0])),y=Math.round(Math.min(start[1],end[1])),w=Math.round(Math.abs(start[0]-end[0])),h=Math.round(Math.abs(start[1]-end[1]));start=null;if(w<3||h<3)return;let f=data.frames[index];selected=f.id+'-manual-'+f.regions.length;f.regions.push({id:selected,box_xywh:[x,y,w,h],proposed_label:'',confirmed_label:'',review_status:'pending',proposal_origin:'manual_added'});render()};
$('save').onclick=()=>{let blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ocr-reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)};
$('load').onchange=async e=>{try{let candidate=JSON.parse(await e.target.files[0].text());if(candidate.source_manifest_sha256!==data.source_manifest_sha256)throw Error('来源清单不一致');if(candidate.frames.length!==data.frames.length)throw Error('帧数量不一致');for(let i=0;i<data.frames.length;i++){let a=candidate.frames[i],b=data.frames[i];if(a.id!==b.id||a.image_sha256!==b.image_sha256)throw Error('原图不一致');if(!Array.isArray(a.regions)||a.regions.some(r=>!Array.isArray(r.box_xywh)||r.box_xywh.length!==4))throw Error('区域格式不正确')}for(let i=0;i<data.frames.length;i++)data.frames[i].regions=candidate.frames[i].regions;render()}catch(err){alert('载入失败：'+err.message)}};render();
</script></html>'''

def render_review_html(document):
    """Embed verified original PNG bytes; JSON exports retain provenance, not copies."""
    images={}
    for frame in document['frames']:
        uri=urlparse(frame['image_uri'])
        if uri.scheme!='file' or uri.netloc not in {'','localhost'}:
            raise ValueError('review source must be a local file')
        path=Path(unquote(uri.path))
        if sha(path)!=frame['image_sha256']:
            raise ValueError('review image hash changed')
        raw=path.read_bytes()
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('review image must be PNG')
        images[frame['id']]='data:image/png;base64,'+base64.b64encode(raw).decode('ascii')
    payload=json.dumps(document,ensure_ascii=False).replace('<','\\u003c')
    return HTML.replace('__PAYLOAD__',payload).replace('__IMAGES__',json.dumps(images))

def validate_review(document,source):
    """Fail closed on changed provenance or invalid confirmed labels/boxes."""
    if document['source_manifest_sha256']!=source['source_manifest_sha256']:raise ValueError('source changed')
    originals={f['id']:f for f in source['frames']};seen=set();ids=set();counts=Counter()
    for frame in document['frames']:
        if frame['id'] in seen:raise ValueError('duplicate frame')
        seen.add(frame['id']);original=originals[frame['id']]
        if frame['image_sha256']!=original['image_sha256']:raise ValueError('image changed')
        for r in frame['regions']:
            if r['id'] in ids:raise ValueError('duplicate region ID')
            ids.add(r['id']);x,y,w,h=r['box_xywh']
            if any(not isinstance(v,int) or isinstance(v,bool) for v in [x,y,w,h]) or min(x,y)<0 or min(w,h)<=0 or x+w>1280 or y+h>720:raise ValueError('invalid box')
            state=r['review_status']
            if state not in {'confirmed','rejected','pending'}:raise ValueError('invalid review status')
            if state=='confirmed' and (not r.get('reviewer','').strip() or not r.get('confirmed_label','').strip()):raise ValueError('confirmation needs reviewer and text')
            counts[state]+=1
    if seen!=set(originals):raise ValueError('missing frames')
    return dict(counts)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=json.loads(a.source.read_text())
    if a.review:
        review=json.loads(a.review.read_text());counts=validate_review(review,source)
        result=json.dumps({'counts':counts,'source_sha256':sha(a.source),'review_sha256':sha(a.review),'formal_acceptance':False},indent=2)
    else:result=render_review_html(source)
    with a.output.open('x') as f:f.write(result)
