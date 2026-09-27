import csv,json
from pathlib import Path
import pytest
from PIL import Image
from capture_intake import FIELDS,inspect_package,import_package
from file_utils import sha

def write_package(tmp_path):
    p=tmp_path/'package';p.mkdir();(p/'images').mkdir()
    rows=[]
    for i in range(3):
        Image.new('RGB',(40,20),'white' if i<2 else 'black').save(p/f'images/{i}.png')
        rows.append({k:'' for k in FIELDS}|{'file':f'images/{i}.png','session_id':str(i),'source_group':str(i),'client':'Official','language':'zh-CN','scene':'home','capture_kind':'game_original','notes':'<script>alert(1)</script>'})
    rows[2]['related_frame']='images/0.png';save_csv(p,rows);return p,rows

def save_csv(p,rows):
    with (p/'capture-index.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)

def test_capture_duplicate_and_crop_groups_stay_together(tmp_path):
    p,rows=write_package(tmp_path);out=tmp_path/'out';report=import_package(p,out)
    assert report['samples']==3 and report['duplicate_image_files']==1 and report['leakage_groups']==1
    records=[json.loads(x) for x in (out/'manifest.jsonl').read_text().splitlines()]
    assert all(r['split']=='unassigned' and not r['formal_evaluation_eligible'] for r in records)
    assert (out/'images/00000.png').read_bytes()==(p/'images/0.png').read_bytes()
    assert '<script>alert(1)</script>' not in (out/'review.html').read_text()
    with pytest.raises(FileExistsError):import_package(p,out)

@pytest.mark.parametrize('field,value',[('width','90'),('language','ja'),('file','../../outside.png'),('related_frame','missing.png')])
def test_capture_rejects_false_metadata_and_broken_relations(tmp_path,field,value):
    p,rows=write_package(tmp_path);rows[0][field]=value;save_csv(p,rows)
    with pytest.raises((ValueError,FileNotFoundError)):inspect_package(p)

def test_windows_csv_paths_are_portable(tmp_path):
    p,rows=write_package(tmp_path)
    for row in rows:
        row['file']=row['file'].replace('/', chr(92))
        row['related_frame']=row['related_frame'].replace('/', chr(92))
    save_csv(p,rows)
    records=inspect_package(p)
    assert records[0]['source_file']=='images/0.png'
    assert len({r['leakage_group'] for r in records})==1

def archive_fixture(tmp_path):
    import zipfile
    p,rows=write_package(tmp_path)
    checks=[]
    for row in rows:
        path=p/row['file'];checks.append({'file':row['file'],'sha256':sha(path),'bytes':path.stat().st_size,'width':40,'height':20})
    (p/'image-checksums.json').write_text(json.dumps(checks))
    archive=tmp_path/'capture.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for path in p.rglob('*'):
            if path.is_file():z.write(path,'capture/'+str(path.relative_to(p)))
    return archive

def test_capture_archive_verifies_all_original_images(tmp_path):
    from capture_archive import unpack
    archive=archive_fixture(tmp_path);out=tmp_path/'unpacked';report=unpack(archive,out)
    assert report['images']==3 and report['image_checksums_verified']
    assert (out/'capture/images/0.png').read_bytes()==(tmp_path/'package/images/0.png').read_bytes()

def test_capture_archive_rejects_traversal_without_output(tmp_path):
    import zipfile
    from capture_archive import unpack
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside.txt','bad')
    with pytest.raises(ValueError,match='unsafe archive path'):unpack(archive,tmp_path/'out')
    assert not (tmp_path/'out').exists() and not (tmp_path/'outside.txt').exists()

def test_capture_archive_rejects_wrong_provided_hash(tmp_path):
    import zipfile
    from capture_archive import unpack
    archive=archive_fixture(tmp_path);bad=tmp_path/'changed.zip'
    with zipfile.ZipFile(archive) as old,zipfile.ZipFile(bad,'w') as new:
        for name in old.namelist():
            data=old.read(name)
            if name.endswith('image-checksums.json'):
                rows=json.loads(data);rows[0]['sha256']='0'*64;data=json.dumps(rows).encode()
            new.writestr(name,data)
    with pytest.raises(ValueError,match='checksum'):unpack(bad,tmp_path/'out')
    assert not (tmp_path/'out').exists()
