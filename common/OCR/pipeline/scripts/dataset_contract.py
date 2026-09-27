"""One record contract for generated and reviewed OCR training examples."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / "configs/dataset/split-policy.json"


@lru_cache(maxsize=1)
def split_policy():
    """读取固定的文字分区与主题留出规则。"""
    return json.loads(POLICY.read_text())


def split(label):
    """按文字哈希稳定分配训练或开发分区。"""
    bucket = int(hashlib.sha256(label.encode()).hexdigest()[:8], 16) % 10
    for name, assigned in split_policy()["hash_text_split"].items():
        if bucket in assigned:
            return "reserved" if name == "eval" else name
    raise ValueError("split policy does not cover the text hash bucket")


def training_partition(row):
    """要求训练器与审计器对样本的训练／开发分区判断一致。"""
    partition = row.get("text_partition")
    if partition not in {"train", "dev"} or row.get("split") != partition:
        raise ValueError("split and text_partition must match train or dev")
    return partition
