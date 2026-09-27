"""Explicit full-scene component replacement for development, never training admission."""
import argparse,hashlib,io,json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
from file_utils import sha
from workspace import RT
from asset_utils import asset_path
from scene_style import raster


def pixel_hash(im):
    im=im.convert('RGB');return hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()

def place_text(canvas, alpha, box, color, opacity=1.0):
    x,y,w,h=box
    if x<0 or y<0 or x+w>canvas.width or y+h>canvas.height:raise ValueError('slot outside canvas')
    if alpha.width>w or alpha.height>h:raise ValueError('text does not fit; truncation and automatic shrinking forbidden')
    px=x+(w-alpha.width)//2;py=y+(h-alpha.height)//2
    mask=Image.new('L',canvas.size);mask.paste(alpha,(px,py))
    if opacity!=1:mask=mask.point(lambda v:round(v*opacity))
    canvas.paste(tuple(color),(0,0,canvas.width,canvas.height),mask)
    return mask

def clear_slots(original, slots):
    """Explicit opaque interior reconstruction, never paste over existing text.

Colors use a text-free strip in each button. Borders/shadows outside slots remain.
This is an approximation: texture inside the replacement region is not recovered.
"""
    out=original.copy();trace=[]
    for s in slots:
        x,y,w,h=s['erase_xywh'];dx,dy,dw,dh=s['donor_xywh']
        for bx,by,bw,bh in [s['erase_xywh'],s['donor_xywh']]:
            if min(bx,by)<0 or bw<=0 or bh<=0 or bx+bw>out.width or by+bh>out.height:raise ValueError('invalid background region')
        donor=np.asarray(original.crop((dx,dy,dx+dw,dy+dh))).reshape(-1,3)
        if np.ptp(donor.astype(np.int16),axis=0).max()>25:raise ValueError('donor contains unexpected contrast')
        color=np.median(donor,axis=0).astype('uint8').tolist()
        out.paste(tuple(color),(x,y,x+w,y+h))
        trace.append({'erase_xywh':s['erase_xywh'],'donor_xywh':s['donor_xywh'],'fill_rgb':color})
    return out,trace

def apply_profile(context,masks,profile):
    """Apply the same geometric transform to image and all masks."""
    factor=profile['scale'];size=tuple(max(1,round(x*factor)) for x in context.size)
    context=context.resize(size,Image.Resampling.BILINEAR)
    masks=[m.resize(size,Image.Resampling.BILINEAR) for m in masks]
    if profile['blur']:context=context.filter(ImageFilter.GaussianBlur(profile['blur']))
    if profile.get('jpeg_quality'):
        buf=io.BytesIO();context.save(buf,format='JPEG',quality=profile['jpeg_quality'],subsampling=0)
        buf.seek(0);context=Image.open(buf).convert('RGB')
    return context,masks

def emit(output,contexts,records,key,canvas,labels,masks,meta,profile):
    canvas,masks=apply_profile(canvas,masks,profile)
    context_name=f'contexts/{key}.png';canvas.save(output/context_name)
    annotations=[]
    for index,(label,mask) in enumerate(zip(labels,masks,strict=True)):
        b=mask.getbbox()
        if b is None or min(b[:2])<=0 or b[2]>=canvas.width or b[3]>=canvas.height:raise ValueError('empty or clipped glyph')
        pad=3;roi=[max(0,b[0]-pad),max(0,b[1]-pad),min(canvas.width,b[2]+pad),min(canvas.height,b[3]+pad)]
        path=f'images/{key}-{index}.png';mp=f'masks/{key}-{index}.png'
        crop=canvas.crop(roi);crop.save(output/path);mask.save(output/mp)
        row={**meta,**label,'id':f'{key}-{index}','image':path,'sha256':sha(output/path),
             'pixel_sha256':pixel_hash(crop),'context':context_name,'context_sha256':sha(output/context_name),
             'mask':mp,'mask_sha256':sha(output/mp),'bbox_xyxy':list(b),'crop_xyxy':roi,
             'crop_contract':'generated alpha bounds plus 3 pixels; not MAA detection/business ROI',
             'profile':profile,'split':'development','text_partition':'dev','training_eligible':False,
             'formal_evaluation_eligible':False,'calibration_status':'provisional','annotation_status':'generator_exact',
             'task_mapping_status':meta.get('task_mapping_status','unverified')}
        records.append(row);annotations.append({'id':row['id'],'text':row['label'],'bbox_xyxy':list(b)})
    contexts.append({**meta,'id':key,'image':context_name,'sha256':sha(output/context_name),
                     'profile':profile,'size':list(canvas.size),'annotations':annotations,
                     'split':'development','formal_evaluation_eligible':False})


def build(output,config_path):
    config=json.loads(config_path.read_text())
    if output.exists():raise ValueError('output already exists')
    # All source/label/slot inputs are supplied, never implicit capture IDs.
    if not config.get('variants') or not config.get('profiles') or not config.get('source_session'):raise ValueError('explicit source session and variants required')
    source=config['background'];original=Image.open(asset_path(source)).convert('RGB')
    background,trace=clear_slots(original,config['slots'])
    output.mkdir(parents=True)
    (output/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    for slot in config['slots']:
        if slot['style'].get('font'):asset_path(slot['style']['font'])
    for name in ['contexts','images','masks']:(output/name).mkdir()
    records=[];contexts=[]
    for i,variant in enumerate(config['variants']):
        if len(variant['labels'])!=len(config['slots']):raise ValueError('slot/label count mismatch')
        canvas=background.copy();masks=[]
        for row,slot in zip(variant['labels'],config['slots'],strict=True):
            # Caller records why this exact string belongs to the pictured task.
            if not row.get('source'):raise ValueError('missing label source')
            masks.append(place_text(canvas,raster(row['label'],slot['style']),slot['text_slot_xywh'],slot['foreground']))
        for j,profile in enumerate(config['profiles']):
            metadata={'language':config['language'],'scene':config['scene'],'route':'WordOCR','source_session':config['source_session'],'source_capture':source,'background_reconstruction':trace,'leakage_group':'capture:'+source['sha256'],'allowed_uses':['development_regression'],'task_mapping_status':config.get('task_mapping_status','unverified')}
            emit(output,contexts,records,f'{i:04}-{j:02}',canvas,variant['labels'],masks,metadata,profile)
    for name,rows in [('manifest.jsonl',records),('contexts.jsonl',contexts)]:
        (output/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (output/'build.json').write_text(json.dumps({'files':{str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()},'source_code_sha256':sha(Path(__file__)),'formal_acceptance':False},indent=2)+'\n')
    return records

def audit_scene(output):
    recorded=json.loads((output/'build.json').read_text())['files']
    for name,h in recorded.items():
        if sha(output/name)!=h:raise ValueError('scene file changed: '+name)
    with tempfile.TemporaryDirectory(prefix='scene-replay-',dir=output.parent) as temp:
        target=Path(temp)/'replay';build(target,output/'config.json')
        replay=json.loads((target/'build.json').read_text())['files']
        if replay!=recorded:raise ValueError('scene replay mismatch')
    return {'passed':True,'files':len(recorded),'formal_acceptance':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path);p.add_argument('--audit-only',action='store_true');a=p.parse_args()
    if a.audit_only:print(audit_scene(a.output))
    else:
        if not a.config:p.error('--config is required for generation')
        print('Development crops:',len(build(a.output,a.config)))
