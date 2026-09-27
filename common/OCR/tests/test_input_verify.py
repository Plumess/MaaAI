import pytest
from input_verify import score

def test_missing_or_duplicate_results_cannot_inflate_fixed_denominator():
    rows=[{'id':'raw/a','subset':'new','scene':'item','label':'甲','expected_output':'甲'}]
    good={'id':'raw/a','results':[{'text':'甲'}]}
    for predictions in [[],[good,good],[{'id':'raw/unknown','results':[]}]]:
        with pytest.raises(ValueError):score(rows,predictions)

def test_rejected_prediction_counts_as_error_and_task_target_is_not_display_label():
    row={'id':'rules/a','subset':'new','scene':'operator','label':'Exusiai','expected_output':'能天使'}
    result,_=score([row],[{'id':'rules/a','results':[]}]);assert result['groups']['rules/new/operator']=={'count':1,'correct':0}
    result,_=score([row],[{'id':'rules/a','results':[{'text':'能天使'}]}]);assert not result['errors']

def test_visible_policy_does_not_hide_roman_numeral_or_extra_space_errors():
    row={'id':'raw/a','subset':'new','scene':'item','label':'Ⅱ','expected_output':'Ⅱ'}
    for text in ['II','ⅡI','Ⅱ ']:
        result,_=score([row],[{'id':'raw/a','results':[{'text':text}]}]);assert result['errors'][0]['literal_outputs']==[text]
