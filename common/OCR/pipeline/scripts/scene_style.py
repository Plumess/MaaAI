"""Calibrated font rendering, without experiment-specific fitting entry points."""
from functools import lru_cache
from PIL import Image,ImageFont,ImageDraw
from workspace import RT
from asset_utils import cmap

@lru_cache(maxsize=128)
def face(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)

def raster(text, style):
    """Render at an explicit working resolution, without silently fitting the label."""
    path = RT/style['font']['path']
    if any(ord(c) not in cmap(str(path)) for c in text):
        raise ValueError('font missing glyph')
    forbidden = {c for pair in style['font'].get('raster_aliases_48px', []) for c in pair if c.islower()}
    if set(text) & forbidden:
        raise ValueError('ambiguous case glyph')
    scale = style['render_scale']; size = round(style['font_size']*scale)
    stroke = round(style['stroke_width']*scale)
    f = face(str(path), size)
    b = f.getbbox(text, stroke_width=stroke)
    pad = 4*scale
    im = Image.new('L', (b[2]-b[0]+2*pad, b[3]-b[1]+2*pad))
    ImageDraw.Draw(im).text((pad-b[0], pad-b[1]), text, font=f, fill=255,
                           stroke_width=stroke, stroke_fill=255)
    im = im.resize((max(1, round(im.width/scale*style['horizontal_scale'])),
                    max(1, round(im.height/scale))), Image.Resampling.BILINEAR)
    # Keep all nonzero alpha, not just a binary mask's bounds.
    bounds = im.getbbox()
    if bounds is None: raise ValueError('empty rendered text')
    return im.crop(bounds)
