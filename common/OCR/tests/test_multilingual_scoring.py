import pytest
from multilingual_rescore import target


def test_localized_display_text_and_internal_name_are_distinct():
    row={'id':'rules/example','label':'스네구로치카','task_name':'CharsNameOcrReplace','source':{'json_pointer':'/char_4208_wintim/name'}}
    assert target(row,{'char_4208_wintim':{'name':'冬时'}})==('冬时','/chars/char_4208_wintim/name')
    assert target({**row,'id':'raw/example'},{})==('스네구로치카',None)


def test_unmapped_name_must_not_use_an_ocr_prediction_as_truth():
    row={'id':'rules/example','label':'Unknown','task_name':'CharsNameOcrReplace','source':{'json_pointer':'/unknown/name'}}
    with pytest.raises(KeyError):target(row,{})


def test_numeric_rules_keep_display_label_as_truth():
    row={'id':'rules/quantity','label':'100','task_name':'NumberOcrReplace'}
    assert target(row,{})==('100',None)
