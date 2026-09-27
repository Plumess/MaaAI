import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from appearance import fit_multiplier,register_template
from appearance import composite
from appearance import background_plane,eligible_base_names,dark_layer


def test_background_multiplier_fits_known_blank_pixels():
    b=np.full((20,20,3),180.);a=b*.4;mask=np.ones((20,20),bool)
    assert fit_multiplier([(a,b,mask)])==pytest.approx(.4)
    with pytest.raises(ValueError):fit_multiplier([])


def test_registration_ignores_quantity_area():
    rng=np.random.default_rng(2);a=rng.integers(40,230,(80,80,3),dtype='uint8');b=a.copy();b[55:]=255
    _,before=register_template(Image.fromarray(a),Image.fromarray(a));_,after=register_template(Image.fromarray(a),Image.fromarray(b))
    assert before['dx']==after['dx']==0 and before['dy']==after['dy']==0


def test_background_plane_refuses_strong_texture():
    a=np.indices((30,100)).sum(0)%2*90+150;im=Image.fromarray(np.repeat(a[:,:,None],3,axis=2).astype('uint8'))
    with pytest.raises(ValueError,match='not planar'):background_plane(im)


def test_plane_recovers_smooth_background_around_dark_text():
    a=np.zeros((30,100,3),dtype='uint8')
    for y in range(30):a[y]=150+y
    a[8:22,20:28]=30
    _,record=background_plane(Image.fromarray(a));assert record['blank_mae']<.01


def test_operator_pool_excludes_tokens_and_unobtainable_characters():
    chars={'ok':{'name':'甲','profession':'MEDIC','isNotObtainable':False},'token':{'name':'召唤物','profession':'TOKEN','isNotObtainable':False},'npc':{'name':'乙','profession':'MEDIC','isNotObtainable':True},'missing':{'name':'丙','profession':'MEDIC','isNotObtainable':False}}
    corpus=[{'id':k,'locale':'cn','category':'character_table','text_partition':'train','label':v['name'],'source':{'json_pointer':f'/{k}/name'}} for k,v in chars.items()]
    selected,excluded=eligible_base_names(corpus,chars,{'chars':{'ok':{},'token':{},'npc':{}}})
    assert [r['label'] for r in selected]==['甲'];assert len(excluded)==3


def test_compositing_without_alpha_keeps_background():
    bg=Image.new('RGB',(30,20),(120,140,160));assert composite(bg,Image.new('L',bg.size),{'ink':255,'edge_blur':.25,'shadow_opacity':.5}).tobytes()==bg.tobytes()
    with pytest.raises(ValueError,match='overflow'):dark_layer(bg,Image.new('L',(40,10)),[30]*3,[0,0])
