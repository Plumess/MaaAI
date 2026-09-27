import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
from patch_text_renderer import replace_method
from train_test_split import train_test_split


def test_split_keeps_repeated_text_together_across_sources_and_order():
    rows=[f'{i} scene {i % 100}\n' for i in range(500)]
    a,b=train_test_split(rows)
    assert set(a)==set(train_test_split(rows[::-1])[0])
    assert {r.partition(' ')[2] for r in a}.isdisjoint({r.partition(' ')[2] for r in b})
    assert a and b
    assert bool(train_test_split(['1 café\n'])[0]) == bool(train_test_split(['2 cafe\u0301\n'])[0])


@pytest.mark.parametrize('rows', [['invalid\n'], ['1 \n'], ['1 a\n','1 b\n']])
def test_bad_labels_fail_before_writing(rows):
    with pytest.raises(ValueError):train_test_split(rows)


def test_pillow_ink_bounds_do_not_subtract_bearing_twice(tmp_path):
    from patch_text_renderer import patch
    root=tmp_path/'renderer';(root/'textrenderer').mkdir(parents=True)
    source='from tenacity import retry\nclass Renderer:\n    @retry\n    def get_word_size(self,font,word):\n        return font.getsize(word)\n    def draw_text_with_random_space(self,*args):\n        pass\n'
    (root/'textrenderer/renderer.py').write_text(source)
    (root/'main.py').write_text('from tenacity import retry\n@retry\ndef run():\n    pass\n')
    patch(root/'textrenderer/renderer.py')
    result=(root/'textrenderer/renderer.py').read_text()
    namespace={};exec(result,namespace)
    renderer=namespace['Renderer']()
    font=SimpleNamespace(getbbox=lambda _: (-2,7,20,25))
    assert renderer.get_word_size(font,'A')==(22,18)
    with pytest.raises(ValueError):renderer.get_word_size(font,' ')
    patch(root)
    assert result==(root/'textrenderer/renderer.py').read_text()
    assert 'stop_after_attempt(8)' in (root/'main.py').read_text()


def test_renderer_budget_reports_failure_and_timeout():
    import sys, subprocess
    from run_renderer import run
    assert run([sys.executable, '-c', 'pass'], 5) == 0
    with pytest.raises(subprocess.CalledProcessError):
        run([sys.executable, '-c', 'raise SystemExit(7)'], 5)
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, '-c', 'import time; time.sleep(60)'], .1)


def test_label_conversion_preserves_spaces_and_repeated_runs(tmp_path):
    import subprocess, sys
    source=tmp_path/'render';source.mkdir()
    (source/'train.txt').write_text('0001 Senior Operator\n',encoding='utf-8')
    (source/'test.txt').write_text('0002 12 345\n',encoding='utf-8')
    out=tmp_path/'labels'
    script=Path(__file__).resolve().parents[1]/'utils/rename_for_ppocr.py'
    command=[sys.executable,str(script),str(source),str(out),'en_US']
    subprocess.run(command,cwd=tmp_path,check=True)
    expected=(out/'rec_gt_train.txt').read_text()
    assert expected==str(source/'0001.jpg')+'\tSenior Operator\n'
    subprocess.run(command,cwd=tmp_path,check=True)
    assert (out/'rec_gt_train.txt').read_text()==expected
