"""Regressions for the contracts that failed the independent maintainer review."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from acceptance_cases import compare_cases
from dataset_contract import training_partition
from evaluation_policy import evaluation_failed
from file_utils import sha
from machine_resources import gpu_status, load_policy
from PIL import Image
from recipe_settings import check_plan_recipe, check_profile, load_recipe
from training_preflight import audit_rows


class _AEncoder:
    ctc_encode = SimpleNamespace(dict={"A": 0}, character=["A"])
    gtc_encode = SimpleNamespace(character=["", "A"])

    def __call__(self, _row):
        return {"length": 1, "label_ctc": [0], "label_gtc": [0, 1]}


def test_train_dev_disagreement_is_rejected_by_audit_and_consumer(
    tmp_path, monkeypatch
):
    import training_preflight

    monkeypatch.setattr(training_preflight, "RT", tmp_path)
    Image.new("RGB", (8, 4), "white").save(tmp_path / "sample.png")
    (tmp_path / "source.json").write_text('{"text":"A"}')
    base = {
        "label": "A",
        "language": "en",
        "route": "WordOCR",
        "scene": "item_name",
        "image": "sample.png",
        "sha256": sha(tmp_path / "sample.png"),
        "source": {
            "path": "source.json",
            "sha256": sha(tmp_path / "source.json"),
            "json_pointer": "/text",
        },
        "text_partition": "train",
    }
    rows = [dict(base, id="train", split="train"), dict(base, id="dev", split="dev")]
    report, _checked = audit_rows(rows, tmp_path, {"v6": _AEncoder()})
    assert not report["passed"]
    assert report["issue_counts"]["split_partition_mismatch"] == 1
    with pytest.raises(ValueError, match="must match"):
        training_partition(rows[1])


def test_same_pixels_cannot_cross_train_and_dev(tmp_path, monkeypatch):
    import training_preflight

    monkeypatch.setattr(training_preflight, "RT", tmp_path)
    Image.new("RGB", (8, 4), "white").save(tmp_path / "same.png")
    (tmp_path / "source.json").write_text('{"text":"A"}')
    row = {
        "id": "train", "label": "A", "language": "en", "route": "WordOCR",
        "scene": "item_name", "image": "same.png", "sha256": sha(tmp_path / "same.png"),
        "source": {"path": "source.json", "sha256": sha(tmp_path / "source.json"),
                   "json_pointer": "/text"},
        "split": "train", "text_partition": "train",
    }
    report, _ = audit_rows([row, dict(row, id="dev", split="dev", text_partition="dev")],
                           tmp_path, {"v6": _AEncoder()})
    assert not report["passed"]
    assert report["issue_counts"]["identical_pixels_cross_partition"] == 1


def test_full_analyzer_failure_is_a_quality_regression_even_with_correct_text():
    cases = [
        {
            "id": "case",
            "route": "zh-CN",
            "mode": "recruit",
            "source_scope": "fixture",
            "truth": {"texts": ["A"]},
        }
    ]
    official = [
        {
            "id": "case",
            "mode": "recruit",
            "analyze_ok": True,
            "results": [{"text": "A"}],
        }
    ]
    candidate = [dict(official[0], analyze_ok=False)]
    frames = compare_cases(cases, official, candidate)
    assert frames["new_truth_regressions"] == []
    assert frames["new_analyzer_failures"] == ["case"]
    summary = {"failed_timing_routes": [], "frames": frames, "recognition": {}}
    assert evaluation_failed({"purpose": "evaluation"}, summary)
    assert not evaluation_failed({"purpose": "integration"}, summary)


def test_gpu_status_queries_only_the_training_device(monkeypatch):
    import machine_resources

    seen = []

    def reply(command, **_kwargs):
        seen.append(command)
        if "--query-gpu=index" in command:
            return SimpleNamespace(stdout="0\n")
        return SimpleNamespace(stdout="0, GPU-example, 2, 15947, 36, 0\n")

    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("NVIDIA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setattr(machine_resources.subprocess, "run", reply)
    assert gpu_status(load_policy())["uuid"] == "GPU-example"
    assert "--id=0" in seen[1]
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(RuntimeError, match="unremapped"):
        gpu_status(load_policy())
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES")
    monkeypatch.setattr(
        machine_resources.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout="0, GPU-a, 2, 15947, 36, 0\n1, GPU-b, 2, 15947, 36, 0\n"
        ),
    )
    with pytest.raises(RuntimeError, match="exactly one"):
        gpu_status(load_policy())


def test_unasserted_depot_change_needs_exact_reviewed_exception():
    from acceptance_cases import business_digest

    case = {"id": "x", "route": "zh-CN", "mode": "depot", "source_scope": "fixture",
            "truth": {"texts": ["A"]}}
    official = {"id": "x", "mode": "depot", "analyze_ok": True,
                "results": [{"text": "A", "quantity": 1}]}
    candidate = {"id": "x", "mode": "depot", "analyze_ok": True,
                 "results": [{"text": "A", "quantity": 2}]}
    summary = {"failed_timing_routes": [], "recognition": {}}
    summary["frames"] = compare_cases([case], [official], [candidate])
    assert summary["frames"]["new_truth_regressions"] == []
    assert summary["frames"]["unreviewed_business_changes"] == ["x"]
    assert evaluation_failed({"purpose": "evaluation"}, summary)
    case["approved_business_change"] = {
        "reason": "Manually checked quantity in source screenshot",
        "candidate_canonical_sha256": business_digest(candidate),
    }
    summary["frames"] = compare_cases([case], [official], [candidate])
    assert summary["frames"]["unreviewed_business_changes"] == []
    assert not evaluation_failed({"purpose": "evaluation"}, summary)
    summary["frames"] = compare_cases([case], [official], [official])
    assert summary["frames"]["unreviewed_business_changes"] == ["x"]
    assert evaluation_failed({"purpose": "evaluation"}, summary)
    candidate["results"][0]["quantity"] = 3
    summary["frames"] = compare_cases([case], [official], [candidate])
    assert summary["frames"]["unreviewed_business_changes"] == ["x"]


def test_export_artifacts_belong_to_each_attempt(tmp_path, monkeypatch):
    import multilingual_verify as exporter

    release = tmp_path / "release"
    monkeypatch.setattr(exporter, "RELEASE", release)
    keys = tmp_path / "keys.txt"
    keys.write_text("A\n")
    config = tmp_path / "model.yml"
    config.write_text(yaml.safe_dump({"Global": {"character_dict_path": str(keys)}}))
    checkpoint = tmp_path / "model.pdparams"
    checkpoint.write_bytes(b"fixed-weights")

    def fake_run(command, _log, timeout=600):
        command = list(map(str, command))
        if "--output" in command:
            output = Path(command[command.index("--output") + 1])
            if command[1].endswith("export_model.py"):
                output.mkdir()
            elif command[1].endswith("repair_onnx_attributes.py"):
                output.write_bytes(checkpoint.read_bytes())
        if "--save_file" in command:
            Path(command[command.index("--save_file") + 1]).write_bytes(b"converter")

    monkeypatch.setattr(exporter, "run", fake_run)
    packs = []
    for branch in ("a", "b"):
        attempt = tmp_path / branch / "run-01" / "attempt-01"
        attempt.mkdir(parents=True)
        pack, report = exporter.export(
            checkpoint,
            config,
            "run-01-500-attempt-01",
            attempt,
            [{"id": "case", "scene": "item_name", "label": "A"}],
        )
        assert report["passed"]
        packs.append(pack)
    assert packs[0].resolve() != packs[1].resolve()
    assert (
        packs[0].joinpath("rec/inference.onnx").resolve()
        != packs[1].joinpath("rec/inference.onnx").resolve()
    )
    assert packs[0].joinpath("rec/inference.onnx").read_bytes() == b"fixed-weights"
    with pytest.raises(FileExistsError, match="reuse"):
        exporter.export(
            checkpoint,
            config,
            "run-01-500-attempt-01",
            packs[0].parent,
            [{"id": "case", "scene": "item_name", "label": "A"}],
        )


def test_versioned_recipe_matches_frozen_route_and_profile():
    recipe = load_recipe()
    assert recipe["base_seed"] == 20260922
    assert recipe["expansion_seed"] == 20260925
    assert sum(recipe["pool_per_scene"]["word"].values()) == 10000
    assert sum(recipe["pool_per_scene"]["char"].values()) == 10000
    profile = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "pipeline/configs/training-recipe-v4.json"
        ).read_text()
    )
    check_profile(recipe, profile)
    rows = [
        {"route": "WordOCR", "language": "en", "split": "train"} for _ in range(10000)
    ]
    check_plan_recipe(recipe, "en", "historical", rows, formal=True)
    with pytest.raises(ValueError, match="sampling"):
        check_plan_recipe(recipe, "en", "balanced", rows, formal=True)
    with pytest.raises(ValueError, match="count"):
        check_plan_recipe(recipe, "en", "historical", rows[:-1], formal=True)
    assert recipe["routes"]["char"]["base_train_images"] == 10000
    assert recipe["routes"]["char"]["formal_train_images"] == 20000
    base_char = [{"route": "CharOCR", "split": "train"}] * 10000
    with pytest.raises(ValueError, match="count"):
        check_plan_recipe(recipe, "char", "historical", base_char, formal=True)
    check_plan_recipe(recipe, "char", "historical", base_char * 2, formal=True)


@pytest.mark.parametrize(
    "command",
    [
        "fetch",
        "corpus",
        "generate",
        "scene",
        "prepare-model",
        "plan",
        "train",
        "export-check",
        "doctor",
        "capture-unpack",
        "capture-import",
        "calibrate",
        "audit-pool",
        "evaluate",
        "package",
        "freeze-evaluation",
        "inspect-rules",
        "review",
    ],
)
def test_public_entry_loads_and_displays_help(command, tmp_path):
    entry = Path(__file__).resolve().parents[1] / "pipeline/pipeline.py"
    result = subprocess.run(
        [sys.executable, str(entry), "--runtime", str(tmp_path), command, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (command, result.stderr)
    assert "usage:" in result.stdout
