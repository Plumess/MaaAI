"""Inspect the chosen training GPU and versioned resource limits."""

import json
import os
import shutil
import subprocess
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / "configs/resource-policy.json"
FIELDS = ("index", "uuid", "used_mib", "free_mib", "temperature_c", "utilization_percent")


def load_policy(path=POLICY):
    policy = json.loads(Path(path).read_text())
    if policy.get("version") != 1 or not isinstance(policy.get("gpu_index"), int):
        raise ValueError("unknown GPU resource policy")
    return policy


def gpu_status(policy=None):
    policy = policy or load_policy()
    device = policy["gpu_index"]
    # nvidia-smi uses physical indices while Paddle uses CUDA-visible ordinals.
    # The reviewed training profile is one unremapped GPU; reject other layouts
    # rather than silently checking a different device from the one trained on.
    if (device != 0 or "CUDA_VISIBLE_DEVICES" in os.environ
            or os.environ.get("NVIDIA_VISIBLE_DEVICES") not in (None, "all")):
        raise RuntimeError("training requires one unremapped physical GPU at index 0")
    inventory = subprocess.run(
        ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    if inventory != ["0"]:
        raise RuntimeError("training requires exactly one physical GPU")
    command = [
        "nvidia-smi", f"--id={device}",
        "--query-gpu=index,uuid,memory.used,memory.free,temperature.gpu,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()
    rows = output.splitlines()
    if len(rows) != 1:
        raise RuntimeError("expected exactly one selected GPU from nvidia-smi")
    values = [value.strip() for value in rows[0].split(",")]
    if len(values) != len(FIELDS):
        raise RuntimeError("unexpected nvidia-smi field count")
    result = dict(zip(FIELDS, values, strict=True))
    for key in FIELDS:
        if key != "uuid":
            result[key] = int(result[key])
    if result["index"] != device:
        raise RuntimeError("GPU query returned a different device")
    return result


def require_training_capacity(runtime, policy=None):
    policy = policy or load_policy()
    status = gpu_status(policy)
    if (status["used_mib"] > policy["maximum_existing_gpu_memory_mib"] or
            status["free_mib"] < policy["minimum_free_gpu_memory_mib"]):
        raise RuntimeError("selected GPU does not meet the training memory policy")
    if shutil.disk_usage(runtime).free < policy["minimum_free_runtime_disk_gib"] * 1024**3:
        raise RuntimeError("runtime disk does not meet the training space policy")
    return status


def require_safe_temperature(status, policy=None):
    policy = policy or load_policy()
    if status["temperature_c"] >= policy["maximum_gpu_temperature_c"]:
        raise RuntimeError("selected GPU exceeds the temperature policy")
