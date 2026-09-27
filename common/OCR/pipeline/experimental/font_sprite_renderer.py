"""Optional font/sprite renderer; not used by the frozen OCR refresh recipe."""

from pathlib import Path
import io
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features
from workspace import RT
from asset_utils import asset_path, cmap

def validate_label(label):
    if not isinstance(label,str) or not label or label!=label.strip() or len(label)>23 or any(not 32<=ord(c)<=126 for c in label):
        raise ValueError('invalid ASCII label')

def font_layer(label, params, font, runtime=RT):
    if font.get('label_contract','ascii')=='unicode':
        import unicodedata
        if not isinstance(label,str) or not label or label!=label.strip() or len(label)>128 or any(unicodedata.category(c) in {'Cc','Cf'} for c in label):
            raise ValueError('invalid Unicode label')
    else:
        validate_label(label)
    path=asset_path(font,runtime)
    if any(ord(c) not in cmap(str(path)) for c in label): raise ValueError('missing glyph; fallback forbidden')
    # Raster-identical upper/lower case labels are invalid for the audited display faces.
    disallowed={c for pair in font.get('raster_aliases_48px',[]) for c in pair if c.islower()}
    if set(label)&disallowed: raise ValueError('ambiguous case glyph')
    size=params['font_size'];stroke=params['stroke_width'];spacing=params['tracking']
    layout=params.get('font_layout','legacy_per_character')
    if layout=='shaped_run':
        # Use whole-run shaping for scripts whose glyph form depends on context.
        # Never silently fall back to per-character drawing on another machine.
        if spacing!=0:raise ValueError('shaped run does not support manual tracking')
        if not features.check_feature('raqm'):raise ValueError('RAQM required; no silent layout fallback')
        face=ImageFont.truetype(str(path),size,layout_engine=ImageFont.Layout.RAQM)
        language=params.get('language');kwargs={'direction':'ltr','features':['kern'],'language':language}
        left,top,right,bottom=face.getbbox(label,stroke_width=stroke,**kwargs)
        if right<=left or bottom<=top:raise ValueError('empty shaped text')
        image=Image.new('RGBA',(right-left+4,bottom-top+4))
        ImageDraw.Draw(image).text((2-left,2-top),label,font=face,fill=tuple(params['foreground']),
                                  stroke_width=stroke,stroke_fill=tuple(params['stroke_color']),**kwargs)
        return image,{'kind':'font','font':font,'layout_engine':'Pillow RAQM','layout_mode':'shaped_run',
                      'kerning':'font kerning enabled; game text-engine settings unverified','direction':'ltr','language':language,
                      'source_bbox':[left,top,right,bottom],'advance':face.getlength(label,**kwargs),
                      'shaping_runtime':{key:features.version_feature(key) for key in ['raqm','harfbuzz','fribidi']}}
    if layout!='legacy_per_character':raise ValueError('unknown font layout')
    # Keep the original per-character path for calibrated ASCII/game faces.
    # These pixels are deliberately distinct from the shaped-run variant.
    face=ImageFont.truetype(str(path),size,layout_engine=ImageFont.Layout.BASIC)
    boxes=[];positions=[];advance=0.0
    for c in label:
        boxes.append(face.getbbox(c,stroke_width=stroke));positions.append(round(advance))
        advance+=face.getlength(c)+spacing
    left=min(p+b[0] for p,b in zip(positions,boxes));right=max(p+b[2] for p,b in zip(positions,boxes))
    top=min(b[1] for b in boxes);bottom=max(b[3] for b in boxes)
    image=Image.new('RGBA',(right-left+4,bottom-top+4))
    draw=ImageDraw.Draw(image)
    for c,x in zip(label,positions):
        draw.text((x-left+2,2-top),c,font=face,fill=tuple(params['foreground']),stroke_width=stroke,stroke_fill=tuple(params['stroke_color']))
    return image, {'kind':'font','font':font,'layout_engine':'Pillow BASIC','kerning':'per-character advances; scene calibration pending','positions':positions}

def sprite_layer(label, params, glyphs, runtime=RT):
    if not label.isascii() or not label.isdigit():raise ValueError('sprite labels must use mapped digits')
    if any(c not in glyphs for c in label):raise ValueError('missing sprite; fallback forbidden')
    images={c:Image.open(asset_path(a,runtime)).convert('RGBA') for c,a in glyphs.items()}
    scale=params['font_size']/max(im.height for im in images.values())
    seq=[im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS) for im in (images[c] for c in label)]
    gap=params['tracking'];width=sum(im.width for im in seq)+gap*(len(seq)-1)+4;height=max(im.height for im in seq)+4
    out=Image.new('RGBA',(width,height));x=2;positions=[]
    for c,im in zip(label,seq):
        y=height-2-im.height;out.alpha_composite(im,(x,y));positions.append({'character':c,'xy':[x,y],'size':list(im.size),'asset':glyphs[c]});x+=im.width+gap
    return out,{'kind':'game_digit_sprites','scale':scale,'placements':positions,'alignment':'bottom; inferred, not prefab-calibrated','original_rgba_preserved':True}

def render(label, params, source, background=None, runtime=RT):
    """No randomness here: the manifest alone specifies a render. Returns context, crop and geometry."""
    if source['kind']=='font':layer,trace=font_layer(label,params,source['font'],runtime)
    elif source['kind']=='sprites':layer,trace=sprite_layer(label,params,source['glyphs'],runtime)
    else:raise ValueError('unknown renderer')
    padding=params['padding'];margin=params['context_margin']
    width=max(layer.width+2*(padding+margin),params['min_width']);height=max(layer.height+2*(padding+margin),params['min_height'])
    context=Image.new('RGBA',(width,height),tuple(params['background_color']))
    background_trace=None
    if background:
        raw=Image.open(asset_path(background,runtime)).convert('RGBA')
        # Uniform contain: no arbitrary stretching of a panel or its decoration.
        factor=min(width/raw.width,height/raw.height)
        new_size=(max(1,round(raw.width*factor)),max(1,round(raw.height*factor)))
        raw=raw.resize(new_size,Image.Resampling.LANCZOS);pos=((width-raw.width)//2,(height-raw.height)//2)
        context.alpha_composite(raw,pos)
        background_trace={'asset':background,'fit':'contain','size':list(new_size),'xy':list(pos)}
    position=((width-layer.width)//2,(height-layer.height)//2)
    context.alpha_composite(layer,position)
    full_mask=Image.new('L',context.size);full_mask.paste(layer.getchannel('A'),position)
    context=context.convert('RGB')
    if params['blur_radius']:context=context.filter(ImageFilter.GaussianBlur(params['blur_radius']))
    scale=params['capture_scale'];capture_size=(max(1,round(width*scale)),max(1,round(height*scale)))
    context=context.resize(capture_size,Image.Resampling.BILINEAR)
    full_mask=full_mask.resize(capture_size,Image.Resampling.BILINEAR)
    if params['jpeg_quality']:
        buf=io.BytesIO();context.save(buf,format='JPEG',quality=params['jpeg_quality'],subsampling=0);buf.seek(0);context=Image.open(buf).convert('RGB')
    bounds=full_mask.getbbox()
    if bounds is None:raise ValueError('empty text mask')
    pad=max(2,round(padding*scale));roi=[max(0,bounds[0]-pad),max(0,bounds[1]-pad),min(context.width,bounds[2]+pad),min(context.height,bounds[3]+pad)]
    if bounds[0]<=0 or bounds[1]<=0 or bounds[2]>=context.width or bounds[3]>=context.height:raise ValueError('clipped glyph')
    crop=context.crop(tuple(roi))
    # This oracle crop trains recognition only. It does not validate MAA's
    # detector, released ROI rules or thresholding on a complete screenshot.
    return context,crop,{'text':trace,'background':background_trace,'text_position':list(position),'text_bbox':list(bounds),'roi_xyxy':roi,'capture_size':list(capture_size),
                         'crop_contract':'oracle glyph bounds + padding; not released MAA ROI/threshold pipeline',
                         'raster_runtime':{'pillow':Image.__version__,'freetype':features.version_module('freetype2')}}
