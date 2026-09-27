"""Portable contracts use synthetic fixtures; no external game assets or GPU needed."""
import importlib.util,json,sys
from pathlib import Path
import numpy as np
import pytest

PIPELINE=Path(__file__).resolve().parents[1]/'pipeline'
@pytest.fixture
def modules(tmp_path,monkeypatch):
    monkeypatch.setenv('MAA_OCR_RUNTIME',str(tmp_path));monkeypatch.syspath_prepend(str(PIPELINE/'scripts'))
    names=['workspace','asset_utils','scene_style','scene_dataset','core_training_data','text_targets','prepare_model','source_assets','source_corpus','run_training_plan','doctor']
    for name in names:sys.modules.pop(name,None)
    def load(name):return __import__(name)
    yield load
    for name in names:sys.modules.pop(name,None)

def test_token_remap_preserves_order_and_blank_and_new_rows(modules):
    m=modules('prepare_model');a=np.arange(12,dtype=np.float32).reshape(3,4)
    new,pairs=m.remap_array(a,1,['blank','O','0','space'],['blank','0','O','space','★'],fill=-12)
    assert pairs==[(0,0),(1,2),(2,1),(3,3)]
    np.testing.assert_array_equal(new[:,:4],a[:,[0,2,1,3]])
    assert np.all(new[:,-1]==-12)
    with pytest.raises(ValueError,match='duplicate'):m.token_mapping(['0','0'],['0'])
    with pytest.raises(ValueError,match='classes'):m.remap_array(a,1,['0'],['0'])

def test_source_lock_rejects_escape_and_changed_local_file(modules,tmp_path):
    m=modules('source_assets');f=tmp_path/'asset';f.write_text('changed');lock=tmp_path/'lock.json'
    lock.write_text(json.dumps({'files':[{'path':'asset','sha256':'0'*64,'url':'https://example.invalid/never-fetched'}]}))
    with pytest.raises(ValueError,match='changed'):m.fetch(lock,offline=True)
    lock.write_text(json.dumps({'files':[{'path':'../escape','sha256':'0'*64,'url':'https://example.invalid/never-fetched'}]}))
    with pytest.raises(ValueError,match='outside'):m.fetch(lock,offline=True)

def test_scene_rejects_clipping_and_marks_capture_development(modules,tmp_path):
    from PIL import Image
    m=modules('scene_dataset');canvas=Image.new('RGB',(30,20));alpha=Image.new('L',(8,5),255)
    with pytest.raises(ValueError,match='fit'):m.place_text(canvas,alpha,[2,2,3,3],[255]*3)
    mask=m.place_text(canvas,alpha,[3,3,20,10],[255]*3)
    for name in ['images','masks','contexts']:(tmp_path/name).mkdir()
    records=[];contexts=[]
    m.emit(tmp_path,contexts,records,'x',canvas,[{'label':'0','source':{'kind':'test'}}],[mask],{'language':'zh-CN','source_session':'test','formal_evaluation_eligible':True},{'scale':1,'blur':0})
    assert records[0]['split']=='development'
    assert not records[0]['training_eligible'] and not records[0]['formal_evaluation_eligible']
    assert (tmp_path/records[0]['image']).is_file()

def test_planning_print_does_not_implicitly_train(modules,tmp_path):
    m=modules('run_training_plan');plan=tmp_path/'plan.json'
    plan.write_text(json.dumps({'route':'ko','dataset':'data','profile':'config','checkpoint':'weights','steps':2,'batch':1,'learning_rate':.000005,'eval_every':2,'sampling':'balanced','input_policy':'released','seed':1}))
    cmd=m.command(plan,tmp_path/'output',resume=True,pause_at=1)
    assert '--resume' in cmd and cmd[cmd.index('--language')+1]=='ko'
    assert not (tmp_path/'output').exists()

def test_visible_text_does_not_strip_meaningful_spaces(modules):
    m=modules('text_targets');assert m.transform('A\u00a0B')['label']=='A B'
    assert m.transform('스팀 펌프')['label']=='스팀 펌프'
    assert m.transform('Ⅱ')['label']=='Ⅱ'

def test_scene_entry_keeps_original_and_records_source(modules,tmp_path,monkeypatch):
    from PIL import Image
    m=modules('scene_dataset');source=tmp_path/'source.png';Image.new('RGB',(40,30),(45,45,45)).save(source);before=source.read_bytes()
    monkeypatch.setattr(m,'raster',lambda text,style:Image.new('L',(5,4),255))
    config={'background':{'path':'source.png','sha256':m.sha(source)},'source_session':'fixture-session','language':'ko','scene':'recruitment','slots':[{'erase_xywh':[8,8,14,9],'donor_xywh':[1,1,5,5],'text_slot_xywh':[9,9,12,7],'foreground':[255]*3,'style':{}}],'variants':[{'labels':[{'label':'힐링','source':{'kind':'synthetic_fixture'}}]}],'profiles':[{'scale':1,'blur':0},{'scale':.75,'blur':.2}]}
    path=tmp_path/'scene.json';path.write_text(json.dumps(config));rows=m.build(tmp_path/'out',path)
    assert len(rows)==2 and source.read_bytes()==before
    assert all(r['source_capture']['sha256']==m.sha(source) and not r['training_eligible'] for r in rows)
    assert len({r['sha256'] for r in rows})==2
