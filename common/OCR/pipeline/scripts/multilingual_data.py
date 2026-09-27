"""Explicit language/font selection and operator source filtering."""
import json
from functools import lru_cache
from file_utils import sha
from workspace import ROOT, RT
from asset_utils import asset_path, cmap
from workspace import RELEASE

@lru_cache(maxsize=32)
def font_coverage(path,checksum):
    return cmap(str(asset_path({'path':path,'sha256':checksum})))

def coverage(font):return font_coverage(font['path'],font['sha256'])

def choose_font(label,language,primary,fallback=None):
    """Whole-string font choice is explicit; never substitute individual glyphs."""
    if all(ord(c) in coverage(primary) for c in label):return primary,False
    if language=='en' and fallback and all(ord(c) in coverage(fallback) for c in label):return fallback,True
    return primary,False

def operator_candidates(source):
    """Only obtainable game operators with base data and a published MAA identity."""
    selected=[];excluded=[];cache={}
    battle_path=RELEASE/'resource/battle_data.json';battle=json.loads(battle_path.read_text())['chars']
    for row in source:
        if row.get('category')!='character_table':continue
        folder=(RT/row['source']['path']).parent
        if folder not in cache:
            cache[folder]=(json.loads((folder/'character_table.json').read_text()),json.loads((folder/'building_data.json').read_text()))
        chars,building=cache[folder];key=row['source']['json_pointer'].split('/')[1];char=chars.get(key,{})
        reason=None
        if key not in building.get('chars',{}) or char.get('profession') in {'TOKEN','TRAP'} or char.get('isNotObtainable',True):reason='not_obtainable_base_operator'
        elif key not in battle:reason='not_in_pinned_release_battle_data'
        if reason:excluded.append({'language':row['language'],'scene':'operator_name','label':row['label'],'source':row['source'],'reasons':[reason]});continue
        if char['name']!=row['label']:raise ValueError('operator source mismatch')
        selected.append({**row,'operator_id':key,'expected_internal_name':battle[key]['name']})
    return selected,excluded
