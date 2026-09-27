import json
import pytest
from PIL import Image
from file_utils import sha

def test_review_needs_explicit_human_fields_and_valid_geometry():
    from capture_annotations import validate_review
    import copy
    source={'source_manifest_sha256':'a','frames':[{'id':'f','image_sha256':'b','regions':[
        {'id':'r','box_xywh':[10,10,50,20],'review_status':'pending','confirmed_label':None}]}]}
    assert validate_review(source,source)=={'pending':1}
    edited=copy.deepcopy(source);r=edited['frames'][0]['regions'][0];r['review_status']='confirmed'
    with pytest.raises(ValueError,match='reviewer'):validate_review(edited,source)
    r.update(reviewer='test-fixture-not-a-real-review',confirmed_label='A')
    assert validate_review(edited,source)=={'confirmed':1}
    r['box_xywh']=[1270,10,50,20]
    with pytest.raises(ValueError,match='invalid box'):validate_review(edited,source)
    edited=copy.deepcopy(source);edited['frames'][0]['image_sha256']='wrong'
    with pytest.raises(ValueError,match='image changed'):validate_review(edited,source)

def test_review_page_embeds_exact_png_and_rejects_changed_source(tmp_path):
    import base64
    import re
    from capture_annotations import render_review_html
    path=tmp_path/'原图 1.png'
    Image.new('RGB',(20,10),'white').save(path)
    doc={'frames':[{'id':'f1','image_uri':path.as_uri(),'image_sha256':sha(path)}]}
    page=render_review_html(doc)
    raw=json.loads(re.search(r'<script id="embedded-images" type="application/json">(.*?)</script>',page).group(1))
    assert base64.b64decode(raw['f1'].split(',',1)[1])==path.read_bytes()
    assert "$('image').src=f.image_uri" not in page
    Image.new('RGB',(20,10),'black').save(path)
    with pytest.raises(ValueError,match='hash changed'):render_review_html(doc)
