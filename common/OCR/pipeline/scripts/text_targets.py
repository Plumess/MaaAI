"""Explicit source-to-visible-text contract; never alter source JSON in place."""
import unicodedata
from dataset_contract import split

POLICY='visible-text-v1'

def normalize_text(source):
    # Canonical composition only. Compatibility forms (II/Ⅱ, fullwidth etc.) remain distinct.
    return unicodedata.normalize('NFC',source).replace('\u00a0',' ')

def transform(source):
    target=normalize_text(source)
    operations=[]
    if unicodedata.normalize('NFC',source)!=source:operations.append('NFC')
    if '\u00a0' in source:operations.append('NBSP_TO_SPACE')
    return {'source_label':source,'label':target,'text_transform':{'policy':POLICY,'operations':operations}}

def validate_transform(row,source):
    expected=transform(source)
    if row.get('source_label')!=source or row.get('label')!=expected['label'] or row.get('text_transform')!=expected['text_transform']:
        raise ValueError('unapproved or mismatched source-to-visible-text transform')

def partition(source):
    """Preserve old dev/holdout assignments even if normalization changes the hash."""
    parts={split(source),split(normalize_text(source))}
    return 'reserved' if 'reserved' in parts else 'dev' if 'dev' in parts else 'train'
