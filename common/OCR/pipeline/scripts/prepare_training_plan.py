"""Freeze explicit inputs for one bounded run; never starts training."""

import argparse, json
from pathlib import Path
from file_utils import sha
from workspace import ROOT, RT
from workspace import RELEASE
from routes import CLIENT
from recipe_settings import (
    DEFAULT_RECIPE,
    check_plan_recipe,
    check_profile,
    load_recipe,
)
from dataset_contract import training_partition


def prepare(spec_path, output):
    spec = json.loads(spec_path.read_text())
    route = spec["route"]
    if route not in CLIENT:
        raise ValueError("unknown route")

    def path(key):
        return (spec_path.parent / spec[key]).resolve()

    dataset = path("dataset")
    profile = path("profile")
    checkpoint = path("checkpoint")
    model = path("model_config")
    guard = path("guard_manifest")
    audit = json.loads((dataset / "audit.json").read_text())
    if (
        not audit["passed"]
        or audit["manifest_sha256"] != sha(dataset / "manifest.jsonl")
        or audit["recipe_sha256"] != sha(dataset / "recipe.json")
    ):
        raise ValueError("dataset not ready or changed")
    recipe_path = (
        (spec_path.parent / spec["recipe_config"]).resolve()
        if spec.get("recipe_config")
        else DEFAULT_RECIPE
    )
    recipe = load_recipe(recipe_path)
    profile_data = json.loads(profile.read_text())
    check_profile(recipe, profile_data)
    dataset_recipe = json.loads((dataset / "recipe.json").read_text())
    if dataset_recipe.get("executable_recipe_sha256") and dataset_recipe[
        "executable_recipe_sha256"
    ] != sha(recipe_path):
        raise ValueError("dataset and training plan use different executable recipes")
    steps = spec.get("steps", 1000)
    every = spec.get("eval_every", 500)
    batch = spec.get("batch", 16)
    if not 1 <= every <= steps <= 5000 or not 1 <= batch <= 32:
        raise ValueError("invalid finite budget")
    policy = spec["sampling"]
    purpose = spec.get("purpose", "formal_training")
    if policy not in {"historical", "balanced"} or purpose not in {
        "formal_training",
        "readiness_probe",
        "data_scale_comparison",
    }:
        raise ValueError("unknown policy/purpose")
    dataset_rows = [
        json.loads(line)
        for line in (dataset / "manifest.jsonl").read_text().splitlines()
        if line
    ]
    for row in dataset_rows:
        if row.get("route") in {"WordOCR", "CharOCR"}:
            training_partition(row)
    check_plan_recipe(
        recipe, route, policy, dataset_rows, formal=purpose == "formal_training"
    )
    evaluation = {
        key: str((spec_path.parent / spec["evaluation"][key]).resolve())
        for key in ["manifest", "official", "current"]
    }
    evaluation["manifest_sha256"] = sha(Path(evaluation["manifest"]))
    files = [
        spec_path,
        profile,
        checkpoint,
        model,
        guard,
        recipe_path,
        ROOT / "configs/resource-policy.json",
        dataset / "manifest.jsonl",
        dataset / "recipe.json",
        dataset / "audit.json",
        ROOT / recipe["sampling_policy"],
        *[Path(evaluation[k]) for k in ["manifest", "official", "current"]],
    ]
    # Pin every guard/evaluation image, not merely its JSON container.
    for mp in [guard, Path(evaluation["manifest"])]:
        rows = [json.loads(l) for l in mp.read_text().splitlines() if l]
        if not rows:
            raise ValueError("empty guard/evaluation manifest")
        for row in rows:
            image = (mp.parent / row["image"]).resolve()
            if sha(image) != row["sha256"]:
                raise ValueError("guard/evaluation image changed")
            if mp != guard and not Path(row["image"]).is_absolute():
                raise ValueError(
                    "evaluation native probe requires absolute image paths"
                )
            files.append(image)
    predids = []
    for key in ["official", "current"]:
        predictions = json.loads(Path(evaluation[key]).read_text())["predictions"]
        ids = [r["id"] for r in predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate reference predictions")
        predids.append(set(ids))
    truthids = [
        json.loads(l)["id"]
        for l in Path(evaluation["manifest"]).read_text().splitlines()
        if l
    ]
    if len(truthids) != len(set(truthids)) or any(
        ids != set(truthids) for ids in predids
    ):
        raise ValueError("reference IDs differ from evaluation")
    for p in (RELEASE / "resource").rglob("*.json"):
        files.append(p)
    files.extend(
        RT / p
        for p in [
            "build/maa_ocr_probe",
            "build/fd_tensor_probe",
            "build/libmaa_rec_input.so",
            str(RELEASE.relative_to(RT) / "libMaaCore.so"),
            str(RELEASE.relative_to(RT) / "libfastdeploy_ppocr.so"),
            str(RELEASE.relative_to(RT) / "libonnxruntime.so.1"),
        ]
    )
    # Freeze code and training library identity, including files affecting label encoders.
    files.extend((ROOT / "scripts").glob("*.py"))
    files.append(ROOT / "../environments/train/uv.lock")
    files.extend((RT / "vendor/PaddleOCR/ppocr").rglob("*.py"))
    import yaml

    cfg = yaml.safe_load(model.read_text())
    dictionary = Path(cfg["Global"]["character_dict_path"])
    if not dictionary.is_absolute():
        raise ValueError("prepared model config must use an absolute dictionary path")
    model_kind = recipe["routes"][route]["model"]
    encoder_meta = dataset_recipe.get("encoder_metadata", {}).get(model_kind)
    if encoder_meta and sha(dictionary) != encoder_meta["dictionary_sha256"]:
        raise ValueError("prepared model dictionary differs from admitted data encoder")
    files.append(dictionary)
    files.append(ROOT / json.loads(profile.read_text())["contract"])
    result = {
        "version": 3,
        "route": route,
        "purpose": purpose,
        "dataset": str(dataset),
        "profile": str(profile),
        "checkpoint": str(checkpoint),
        "model_config": str(model),
        "guard_manifest": str(guard),
        "steps": steps,
        "max_steps": steps,
        "batch": batch,
        "eval_every": every,
        "learning_rate": spec.get("learning_rate", 5e-6),
        "sampling": policy,
        "input_policy": "legacy" if route == "char" else "released",
        "seed": spec.get("seed", 20260920),
        "random_policy": "step_seed_v1",
        "learning_rate_schedule": "constant",
        "actual_maa_evaluation": True,
        "stop_on_gate_failure": purpose == "formal_training",
        "automatic_start": False,
        "allow_training": True,
        "not_release_approval": True,
        "dataset_manifest_sha256": sha(dataset / "manifest.jsonl"),
        "profile_sha256": sha(profile),
        "checkpoint_sha256": sha(checkpoint),
        "recipe_config": str(recipe_path),
        "recipe_config_sha256": sha(recipe_path),
        "resolved_recipe": {
            "id": recipe["id"],
            "model": model_kind,
            "sampling": policy,
            "training_rows": len(
                [
                    r
                    for r in dataset_rows
                    if r["split"] == "train"
                    and (
                        r["route"] == "CharOCR"
                        if route == "char"
                        else r["route"] == "WordOCR" and r["language"] == route
                    )
                ]
            ),
            "base_train_images": recipe["routes"][route]["base_train_images"],
            "formal_train_images": recipe["routes"][route].get(
                "formal_train_images", recipe["routes"][route]["base_train_images"]
            ),
        },
        "evaluation": evaluation,
        "files": {str(p.resolve()): sha(p) for p in files},
    }
    if output.exists():
        raise ValueError("refuse to replace a frozen plan")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    prepare(a.spec.resolve(), a.output.resolve())
    print("Plan frozen; no training started")
