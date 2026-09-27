"""Guard label-independent foreground cleanup and geometry failures."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image,ImageDraw
from appearance import quantity_mask,stamp,crop


def test_foreground_rejects_icon_slivers_without_using_label():
    im=Image.new('RGB',(60,30),'black');d=ImageDraw.Draw(im)
    d.rectangle((10,6,19,22),fill='white');d.rectangle((25,6,34,22),fill='white')
    expected,_=quantity_mask(im)
    d.rectangle((0,0,4,20),fill='white');d.rectangle((56,24,59,29),fill='white')
    actual,trace=quantity_mask(im)
    assert trace['kept']==2 and trace['removed']==2
    assert np.array_equal(np.array(expected),np.array(actual))


def test_quantity_does_not_accept_empty_or_icon_only_mask():
    im=Image.new('RGB',(40,30),'black');ImageDraw.Draw(im).rectangle((0,0,4,20),fill='white')
    with pytest.raises(ValueError,match='foreground'):quantity_mask(im)


def test_text_overflow_fails_without_modifying_pixels():
    im=Image.new('RGB',(30,20),'black');before=im.tobytes()
    with pytest.raises(ValueError,match='overflow'):stamp(im,Image.new('L',(20,10),255),[5,5,10,10])
    assert im.tobytes()==before
    with pytest.raises(ValueError,match='outside'):crop(im,[25,5,10,10])


def test_recognition_crop_excludes_adjacent_old_price():
    im=Image.new('RGB',(50,30),'gray');ImageDraw.Draw(im).rectangle((0,3,3,23),fill='white')
    stamp(im,Image.new('L',(8,16),255),[8,4,25,20])
    rec=crop(im,[8,4,25,20]);assert not np.any(np.array(rec)[:,0]==255)
