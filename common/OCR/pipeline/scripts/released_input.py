"""Use the pinned MAA FastDeploy preprocessor without changing inference settings."""
import ctypes
from collections import defaultdict
from pathlib import Path
import numpy as np
from file_utils import sha
from workspace import RT
from workspace import RELEASE

class ReleasedInput:
    def __init__(self):
        self.path=RT/'build/libmaa_rec_input.so'
        self.lib=ctypes.CDLL(str(self.path))
        self.lib.maa_rec_input.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int)]
        self.lib.maa_rec_input.restype=ctypes.c_int
        self.lib.maa_input_free.argtypes=[ctypes.POINTER(ctypes.c_float)]
        self.lib.maa_input_error.restype=ctypes.c_char_p
    def __call__(self,path):
        data=ctypes.POINTER(ctypes.c_float)();height=ctypes.c_int();width=ctypes.c_int()
        rc=self.lib.maa_rec_input(str(Path(path).resolve()).encode(),ctypes.byref(data),ctypes.byref(height),ctypes.byref(width))
        if rc:raise ValueError(self.lib.maa_input_error().decode())
        try:
            # The native library owns this allocation. Copy before freeing it so
            # batches never retain a NumPy view into released native memory.
            return np.ctypeslib.as_array(data,shape=(3*height.value*width.value,)).reshape(3,height.value,width.value).copy()
        finally:self.lib.maa_input_free(data)
    def identity(self):
        files=[self.path,RELEASE/'libfastdeploy_ppocr.so',RELEASE/'libopencv_world4.so.412']
        return {str(p):sha(p) for p in files}

def width_groups(indices,widths):
    """Keep every sample and logical batch; never pad short rows to a long neighbor."""
    groups=defaultdict(list)
    for i in indices:groups[int(widths[int(i)])].append(int(i))
    return list(groups.values())
