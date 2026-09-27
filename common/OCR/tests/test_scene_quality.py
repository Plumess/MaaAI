import numpy as np
from PIL import Image,ImageDraw
import pytest
from appearance import score,select_style
from scene_dataset import place_text,clear_slots,apply_profile

def test_size_difference_is_penalized_without_clipping():
    target=Image.new('L',(10,10),255)
    assert score(target,target)==1
    assert score(Image.new('L',(11,10),255),target)==pytest.approx(200/210)

def test_fit_does_not_consult_check_labels(monkeypatch):
    import appearance as styles
    monkeypatch.setattr(styles,'cmap',lambda _:set(map(ord,'AB')))
    monkeypatch.setattr(styles,'raster',lambda text,style:Image.new('L',(style['font_size'],3),255))
    fonts=[{'path':'fake'}];grid={'font_sizes':[3,5],'stroke_widths':[0],'render_scales':[1],'horizontal_scales':[1]}
    rows=[{'id':'a','proposed_label':'A'},{'id':'b','proposed_label':'B'}]
    targets={'a':Image.new('L',(3,3),255),'b':Image.new('L',(5,3),255)}
    result=select_style(rows,targets,fonts,grid,['a'])
    assert result['style']['font_size']==3
    targets['b']=Image.new('L',(20,3),255)
    assert select_style(rows,targets,fonts,grid,['a'])['style']==result['style']

def test_reconstruction_removes_text_and_preserves_outside():
    bg=Image.new('RGB',(40,20),(30,30,30));ImageDraw.Draw(bg).rectangle((8,5,19,13),fill='white')
    slots=[{'erase_xywh':[5,3,20,14],'donor_xywh':[28,3,4,14]}]
    out,trace=clear_slots(bg,slots)
    assert np.all(np.asarray(out)==30)
    assert trace[0]['fill_rgb']==[30,30,30]
    assert out.crop((25,0,40,20)).tobytes()==bg.crop((25,0,40,20)).tobytes()

def test_busy_donor_is_not_silently_used():
    bg=Image.new('RGB',(30,20),'black');bg.putpixel((25,5),(255,255,255))
    with pytest.raises(ValueError,match='contrast'):clear_slots(bg,[{'erase_xywh':[1,1,10,10],'donor_xywh':[24,4,4,4]}])

def test_overflow_and_mask_alignment():
    canvas=Image.new('RGB',(40,20),'black');alpha=Image.new('L',(10,6),255)
    with pytest.raises(ValueError,match='does not fit'):place_text(canvas,alpha,[1,1,8,8],[255]*3)
    mask=place_text(canvas,alpha,[4,4,20,12],[255]*3)
    image,masks=apply_profile(canvas,[mask],{'scale':0.75,'blur':0})
    assert np.array_equal(np.asarray(image)[:,:,0],np.asarray(masks[0]))
    assert masks[0].getbbox() is not None
