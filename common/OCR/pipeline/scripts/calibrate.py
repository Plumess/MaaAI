"""Fit shared appearance parameters on declared fit items; report check items separately."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image
from appearance import mask_crop,select_style,register_template,background_pixels,fit_multiplier,background_plane
from file_utils import sha
from asset_utils import asset_path


def calibrate(config,output):
    cfg=json.loads(config.read_text())
    output.mkdir(parents=True,exist_ok=False)
    ids=[r['id'] for r in cfg['regions']]
    if any(not isinstance(v,str) or not v or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in v) for v in ids):raise ValueError('region ID must be a safe filename component')
    if not ids or len(ids)!=len(set(ids)):raise ValueError('empty or duplicate regions')
    if any(r['role'] not in ['fit','check'] for r in cfg['regions']):raise ValueError('declare fit/check role')
    if {r['role'] for r in cfg['regions']}!={'fit','check'}:raise ValueError('both fit and check regions required')
    images={}
    for r in cfg['regions']:
        im=Image.open(asset_path(r['source'])).convert('RGB')
        x,y,w,h=r['roi_xywh']
        if min(x,y)<0 or min(w,h)<=0 or x+w>im.width or y+h>im.height:raise ValueError('invalid ROI')
        images[r['id']]=im.crop((x,y,x+w,y+h))
    method=cfg['method']
    if method=='font':
        for f in cfg['fonts']:asset_path(f)
        regions=[dict(r,proposed_label=r['label']) for r in cfg['regions']]
        targets={r['id']:mask_crop(images[r['id']],r['polarity'])[0] for r in regions}
        result=select_style(regions,targets,cfg['fonts'],cfg['search'],[r['id'] for r in regions if r['role']=='fit'])
    elif method=='template':
        pairs={};alignment={}
        for r in cfg['regions']:
            obs=images[r['id']];template=Image.open(asset_path(r['template'])).convert('RGB').resize(obs.size)
            aligned,alignment[r['id']]=register_template(template,obs)
            pairs[r['id']]=background_pixels(obs,aligned)
        multiplier=fit_multiplier([pairs[r['id']] for r in cfg['regions'] if r['role']=='fit'])
        result={'effective_multiplier':multiplier,'regions':[]}
        for r in cfg['regions']:
            a,b,valid=pairs[r['id']]
            result['regions'].append({'id':r['id'],'role':r['role'],'registration':alignment[r['id']],
                'valid_pixels':int(valid.sum()),'mae':float(np.abs(a[valid]-b[valid]*multiplier).mean()) if valid.any() else None})
    elif method=='plane':
        result={'regions':[]}
        for r in cfg['regions']:
            try:
                im,trace=background_plane(images[r['id']]);im.save(output/(r['id']+'.png'))
                result['regions'].append({'id':r['id'],'role':r['role'],'plane':trace})
            except ValueError as e:result['regions'].append({'id':r['id'],'rejected':str(e)})
    else:raise ValueError('unknown calibration method')
    result.update(config_sha256=sha(config),source_regions=cfg['regions'],method=method,formal_acceptance=False,
        font_identity_confirmed=False,scope='appearance calibration; check strings do not select a shared style; no OCR accuracy claim')
    (output/'calibration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();calibrate(a.config,a.output)
