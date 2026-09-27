"""Measured appearance helpers; fit/check scores are not independent OCR accuracy."""
import hashlib,itertools
from functools import lru_cache
import cv2,numpy as np
from PIL import Image,ImageFilter
from scene_style import raster
from workspace import RT
from asset_utils import cmap

def mask_crop(image, polarity):
    a=np.asarray(image.convert('RGB')).astype(np.int16)
    gray=a.mean(2)
    mask=((gray>180)&((a.max(2)-a.min(2))<45)) if polarity=='light' else (gray<95)
    if not mask.any():raise ValueError('empty foreground mask')
    ys,xs=np.where(mask);box=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
    return Image.fromarray((mask*255).astype('uint8')).crop(box),box
def score(alpha, target):
    pred = np.asarray(alpha) > 128
    ys, xs = np.where(pred)
    if not len(xs): return 0.0
    pred = pred[ys.min():ys.max()+1, xs.min():xs.max()+1]
    truth = np.asarray(target) > 0
    h,w = truth.shape; ph,pw = pred.shape
    # Include overflow as false-positive foreground instead of clipping it or
    # turning a one-pixel size mismatch into a zero score.
    ch,cw=max(h,ph)+6,max(w,pw)+8
    canvas=np.zeros((ch,cw),dtype=bool)
    ty,tx=(ch-h)//2,(cw-w)//2
    canvas[ty:ty+h,tx:tx+w]=truth
    best = 0.0
    for dx in [-2,-1,0,1,2]:
        for dy in [-1,0,1]:
            y,x=(ch-ph)//2+dy,(cw-pw)//2+dx
            inter=np.logical_and(canvas[y:y+ph,x:x+pw],pred).sum()
            best=max(best,float(2*inter/(truth.sum()+pred.sum())))
    return best

def select_style(regions, targets, fonts, grid, fit_ids):
    fit_ids = set(fit_ids)
    fit_rows = [r for r in regions if r['id'] in fit_ids]
    if len(fit_rows)!=len(fit_ids) or not fit_rows: raise ValueError('invalid fit region IDs')
    ranked=[]
    for font in fonts:
        if any(ord(c) not in cmap(str(RT/font['path'])) for r in fit_rows for c in r['proposed_label']): continue
        for size, stroke, scale, width in itertools.product(grid['font_sizes'],grid['stroke_widths'],grid['render_scales'],grid['horizontal_scales']):
            if stroke*scale != round(stroke*scale): continue
            style={'font':font,'font_size':size,'stroke_width':stroke,'render_scale':scale,'horizontal_scale':width}
            values=[score(raster(r['proposed_label'],style),targets[r['id']]) for r in fit_rows]
            ranked.append({'style':style,'fit_mean_dice':float(np.mean(values))})
    if not ranked: raise ValueError('no candidates')
    ranked.sort(key=lambda x:x['fit_mean_dice'],reverse=True)
    chosen=ranked[0]
    # Check labels have played no role in selection, including font availability.
    chosen['regions']=[{'id':r['id'],'role':'fit' if r['id'] in fit_ids else 'check',
        'mask_dice':score(raster(r['proposed_label'],chosen['style']),targets[r['id']])} for r in regions]
    checks=[r['mask_dice'] for r in chosen['regions'] if r['role']=='check']
    chosen['check_mean_dice']=float(np.mean(checks)) if checks else None
    chosen['candidates_searched']=len(ranked)
    chosen['runner_up']={k:v for k,v in ranked[1].items()} if len(ranked)>1 else None
    return chosen
def register_template(template,observed):
    base=np.asarray(template).astype('float32');obs=np.asarray(observed).astype('float32')
    h,w=base.shape[:2];valid=(base.mean(2)>35)&(base.max(2)<250)
    valid[int(h*.65):]=False;valid[:3]=False;valid[:,:3]=False;valid[:,-3:]=False
    ranked=[]
    for dx in range(-3,4):
        for dy in range(-3,4):
            warp=cv2.warpAffine(base,np.float32([[1,0,dx],[0,1,dy]]),(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            mask=cv2.warpAffine(valid.astype('uint8'),np.float32([[1,0,dx],[0,1,dy]]),(w,h)).astype(bool)
            if mask.sum()<100:continue
            err=np.abs(warp-obs).mean(2)[mask]
            ranked.append((float(np.median(err)),abs(dx)+abs(dy),dx,dy,warp))
    if not ranked:raise ValueError('insufficient template registration pixels')
    ranked.sort(key=lambda x:x[:4]);err,_,dx,dy,warp=ranked[0]
    return Image.fromarray(np.uint8(warp)),{'dx':dx,'dy':dy,'top_region_median_abs_error':err,'quantity_region_used':False}

def background_pixels(observed,template):
    a=np.asarray(observed).astype(float);b=np.asarray(template).astype(float)
    ink=((a.mean(2)>180)&(a.max(2)-a.min(2)<45)).astype('uint8')
    ink=cv2.dilate(ink,np.ones((3,3),dtype='uint8'),iterations=1).astype(bool)
    valid=(~ink)&(b.mean(2)>45)&(b.mean(2)<230)&(a.mean(2)<175)
    # Remove outer pixels where the source ROI can include outside-of-plate area.
    valid[:2]=False;valid[-2:]=False;valid[:,:2]=False;valid[:,-2:]=False
    return a,b,valid

def fit_multiplier(pairs):
    if not pairs:raise ValueError('no fit cases')
    candidates=np.linspace(.2,1.,161)
    # Per-case equal weight, robust channel loss; big crops do not dominate.
    losses=[]
    for v in candidates:
        per=[float(np.mean(np.minimum(np.abs(a[vld]-b[vld]*v),40))) for a,b,vld in pairs if vld.sum()>=20]
        if not per:raise ValueError('insufficient background evidence')
        losses.append(np.mean(per))
    return float(candidates[int(np.argmin(losses))])
def quantity_foreground(image):
    a=np.array(image).astype(int);raw=np.uint8((a.mean(2)>180)&(a.max(2)-a.min(2)<45))
    _,components,stats,_=cv2.connectedComponentsWithStats(raw,8)
    keep=[i for i,(x,y,w,h,area) in enumerate(stats) if i and 6<=w<=20 and 12<=h<=23 and area>=25]
    if not keep:raise ValueError('no text geometry')
    return Image.fromarray(np.uint8(np.isin(components,keep))*255)

def composite(background,alpha,params):
    a=alpha.filter(ImageFilter.GaussianBlur(params['edge_blur'])) if params['edge_blur'] else alpha
    out=background.copy()
    if params['shadow_opacity']:
        shadow=Image.new('L',a.size);shadow.paste(a,(0,1));shadow=shadow.filter(ImageFilter.GaussianBlur(.7)).point(lambda v:round(v*params['shadow_opacity']))
        out.paste((0,0,0),(0,0,out.width,out.height),shadow)
    out.paste((params['ink'],)*3,(0,0,out.width,out.height),a)
    return out
def eligible_base_names(corpus,characters,building):
    selected={};excluded=[]
    for r in corpus:
        if r.get('locale')!='cn' or r.get('category')!='character_table' or r.get('text_partition')=='eval' or r.get('label_issue'):continue
        key=r['source']['json_pointer'].split('/')[1];char=characters.get(key,{})
        if key not in building.get('chars',{}) or char.get('profession') in {'TOKEN','TRAP'} or char.get('isNotObtainable',True):
            excluded.append({'id':r['id'],'label':r['label'],'reason':'not an obtainable operator with building data'});continue
        if char.get('name')!=r['label']:raise ValueError('character source differs')
        selected.setdefault(r['label'],r)
    return sorted(selected.values(),key=lambda r:hashlib.sha256(r['label'].encode()).hexdigest()),excluded

def background_plane(image):
    a=np.asarray(image.convert('RGB')).astype(float);h,w=a.shape[:2]
    ink=(a.mean(2)<105).astype('uint8');excluded=cv2.dilate(ink,np.ones((5,5),dtype='uint8')).astype(bool)
    valid=(~excluded)&(a.mean(2)>135)
    if valid.sum()<max(30,h*w*.05):raise ValueError('insufficient blank pixels for background')
    yyv,xxv=np.where(valid)
    if np.ptp(xxv)<w*.5 or np.ptp(yyv)<h*.5:raise ValueError('blank pixels do not span the region')
    yy,xx=np.mgrid[:h,:w];design=np.stack([np.ones((h,w)),xx/max(w-1,1),yy/max(h-1,1)],axis=-1)
    coef=np.linalg.lstsq(design[valid],a[valid],rcond=None)[0];plane=np.clip(design@coef,0,255)
    residual=float(np.abs(plane[valid]-a[valid]).mean())
    if residual>8:raise ValueError('background not planar enough; do not erase texture')
    return Image.fromarray(np.uint8(np.rint(plane))),{'coefficients':coef.tolist(),'blank_pixels':int(valid.sum()),'blank_mae':residual,'text_exclusion':'gray<105, dilated 5x5; fit pixels gray>135','model':'per-channel affine RGB plane; approximate background, not recovered original'}

def dark_layer(background,alpha,color,offset):
    x,y=offset
    if min(x,y)<0 or x+alpha.width>background.width or y+alpha.height>background.height:raise ValueError('glyph overflow')
    out=background.copy();out.paste(tuple(color),(x,y,x+alpha.width,y+alpha.height),alpha);return out

def crop(im,box):
    x,y,w,h=box
    if min(x,y)<0 or min(w,h)<=0 or x+w>im.width or y+h>im.height:raise ValueError('box outside image')
    return im.crop((x,y,x+w,y+h))

def stamp(im,alpha,box,align='center'):
    x,y,w,h=box
    if alpha.width>w or alpha.height>h:raise ValueError('text overflow; no shrinking or truncation')
    crop(im,box)
    px=x+w-alpha.width if align=='right' else x+(w-alpha.width)//2
    py=y+(h-alpha.height)//2
    im.paste((245,245,245),(px,py,px+alpha.width,py+alpha.height),alpha)
    return [px,py,alpha.width,alpha.height]

def quantity_mask(image):
    """Fixed 720p digit geometry rejects bright icon slivers, independent of text."""
    a=np.asarray(image.convert('RGB')).astype(np.int16)
    raw=((a.mean(2)>180)&((a.max(2)-a.min(2))<45)).astype('uint8')
    _,components,stats,_=cv2.connectedComponentsWithStats(raw,8)
    kept=[i for i,(x,y,w,h,area) in enumerate(stats) if i and 6<=w<=20 and 12<=h<=23 and area>=25]
    if not kept:raise ValueError('no valid quantity foreground')
    mask=Image.fromarray(np.uint8(np.isin(components,kept))*255)
    return mask.crop(mask.getbbox()),{'component_rule':'width 6..20, height 12..23, area >=25 at 1280x720; not a general detector','kept':len(kept),'removed':len(stats)-1-len(kept)}
