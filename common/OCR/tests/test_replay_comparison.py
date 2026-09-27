from copy import deepcopy
import pytest
from compare_replays import compare


def document():
    return {'client':'Official','release':'v6.17.5','predictions':[
        {'id':'shop','mode':'credit_shop','analyze_ok':True,'results':[{'text':'A','score':.9},{'text':'B','score':.8}]}]}


def test_only_confidence_is_ignored_not_selection_order_or_counts():
    a=document();b=deepcopy(a);b['predictions'][0]['results'][0]['score']=.1
    assert compare(a,b)[0]['business_equal_excluding_scores']
    b['predictions'][0]['results'].reverse()
    assert not compare(a,b)[0]['business_equal_excluding_scores']
    b=deepcopy(a);b['predictions'][0]['results'].append({'text':'A','score':.9})
    assert not compare(a,b)[0]['business_equal_excluding_scores']


def test_equal_failures_are_not_reported_as_success():
    a=document();a['predictions'][0]['analyze_ok']=False
    row=compare(a,a)[0]
    assert row['business_equal_excluding_scores'] and not row['candidate_analyze_ok']


@pytest.mark.parametrize('mutation',['missing','duplicate','release'])
def test_incomplete_or_incompatible_replays_rejected(mutation):
    a=document();b=deepcopy(a)
    if mutation=='missing':b['predictions']=[]
    elif mutation=='duplicate':b['predictions']*=2
    else:b['release']='other'
    with pytest.raises(ValueError):compare(a,b)
