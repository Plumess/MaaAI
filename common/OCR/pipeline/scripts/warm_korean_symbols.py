"""Fit only the three new CTC columns; original feature extractor and classes remain bit-identical."""

import argparse, copy, json, sys, time
from pathlib import Path
import cv2, numpy as np, paddle, yaml
from file_utils import sha
from workspace import ROOT, RT
from core_trial_train import write, read
from machine_resources import (
    gpu_status,
    load_policy,
    require_training_capacity,
    require_safe_temperature,
)
from label_contract import load_encoder
from training_state import acquire_training_lock

sys.path.insert(0, str(RT / "vendor/PaddleOCR"))
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import build_post_process
from ppocr.data.imaug.rec_img_aug import resize_norm_img
from ppocr.losses.rec_ctc_loss import CTCLoss


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--steps", type=int, default=400)
    p.add_argument("--learning-rate", type=float, default=0.0001)
    a = p.parse_args()
    lock = acquire_training_lock(RT)
    resource_policy = load_policy()
    status = require_training_capacity(RT, resource_policy)
    if not 1 <= a.steps <= 800:
        raise ValueError("warmup budget exceeded")
    base = a.model.resolve()
    audit = json.loads((a.dataset / "audit.json").read_text())
    if not audit.get("passed") or audit.get("manifest_sha256") != sha(
        a.dataset / "manifest.jsonl"
    ):
        raise ValueError("dataset is not audited")
    a.output.mkdir(parents=True, exist_ok=False)
    cfg = yaml.safe_load((base / "model.yml").read_text())
    encoder, meta = load_encoder("v5-korean", 64, base / "keys.txt")
    # Paddle's parameter-level L2 would otherwise change masked old columns after backward.
    for head_cfg in cfg["Architecture"]["Head"]["head_list"]:
        if "CTCHead" in head_cfg:
            head_cfg["CTCHead"].setdefault("Head", {})["fc_decay"] = 0.0
    paddle.set_device(f"gpu:{resource_policy['gpu_index']}")
    paddle.seed(20260922)
    np.random.seed(20260922)
    cv2.setNumThreads(1)
    model = build_model(copy.deepcopy(cfg["Architecture"]))
    initial = paddle.load(str(base / "initial.pdparams"))
    model.set_state_dict(initial)
    model.eval()
    post = build_post_process(cfg["PostProcess"], cfg["Global"])
    for parameter in model.parameters():
        parameter.stop_gradient = True
    head = model.head.ctc_head
    weight = head.fc.weight
    bias = head.fc.bias
    weight.stop_gradient = False
    bias.stop_gradient = False
    ids = {c: encoder.ctc_encode.dict[c] for c in "★《》"}
    w = weight.numpy().copy()
    b = bias.numpy().copy()
    for new, old in {"★": "*", "《": "«", "》": "»"}.items():
        ni = ids[new]
        oi = encoder.ctc_encode.dict[old]
        w[:, ni] = w[:, oi]
        b[ni] = b[oi] - 0.5
    weight.set_value(w)
    bias.set_value(b)
    wm = np.zeros(w.shape, "float32")
    wm[:, list(ids.values())] = 1
    bm = wm[0]
    wm = paddle.to_tensor(wm)
    bm = paddle.to_tensor(bm)
    rows = {
        part: read(a.dataset / "ko" / part / "manifest.jsonl")
        for part in ["train", "dev"]
    }
    for part in rows:
        # Include ordinary examples to train rejection of false new symbols.
        special = [r for r in rows[part] if set(r["label"]) & set(ids)]
        normal = [r for r in rows[part] if not set(r["label"]) & set(ids)]
        if not special or not normal:
            raise ValueError(
                "symbol warmup requires both new-symbol and ordinary samples"
            )
        rows[part] = special + normal[: len(special)]
        for row in rows[part]:
            if sha(Path(row["image"])) != row["sha256"]:
                raise ValueError("warmup image changed")
    cache = {}

    def batch(rs):
        arrays = []
        labels = []
        lengths = []
        for r in rs:
            if r["id"] not in cache:
                im = cv2.imread(r["image"])
                norm, _ = resize_norm_img(im, [3, 48, 480])
                label = encoder({"label": r["label"], "image": None})
                cache[r["id"]] = (norm, label["label_ctc"], label["length"])
            x, y, z = cache[r["id"]]
            arrays.append(x)
            labels.append(y)
            lengths.append(z)
        return [
            paddle.to_tensor(np.stack(arrays)),
            paddle.to_tensor(np.stack(labels)),
            paddle.to_tensor(np.stack(lengths)),
        ]

    def evaluate():
        model.eval()
        out = []
        with paddle.no_grad():
            for i in range(0, len(rows["dev"]), 16):
                out.extend(x[0] for x in post(model(batch(rows["dev"][i : i + 16])[0])))
        groups = {}
        errors = []
        for r, text in zip(rows["dev"], out, strict=True):
            k = "new_symbols" if set(r["label"]) & set(ids) else "ordinary"
            v = groups.setdefault(k, {"count": 0, "correct": 0})
            v["count"] += 1
            v["correct"] += text == r["label"]
            if text != r["label"]:
                errors.append({"id": r["id"], "label": r["label"], "prediction": text})
        return {"groups": groups, "errors": errors}

    before = evaluate()
    write(a.output / "before.json", before)
    rng = np.random.default_rng(20260922)
    optim = paddle.optimizer.Adam(
        learning_rate=a.learning_rate,
        parameters=[weight, bias],
        grad_clip=paddle.nn.ClipGradByGlobalNorm(5),
    )
    loss_fn = CTCLoss()
    history = []
    started = time.monotonic()
    for step in range(1, a.steps + 1):
        model.eval()
        head.train()
        idx = rng.integers(len(rows["train"]), size=16)
        bch = batch([rows["train"][i] for i in idx])
        loss = loss_fn(model(bch[0]), bch)["loss"]
        value = float(loss.item())
        if not np.isfinite(value):
            raise ValueError("nonfinite loss")
        loss.backward()
        weight.grad.set_value(weight.grad * wm)
        bias.grad.set_value(bias.grad * bm)
        optim.step()
        optim.clear_grad()
        if step == 1 or step % 100 == 0 or step == a.steps:
            metrics = evaluate()
            status = gpu_status(resource_policy)
            history.append({"step": step, "loss": value, "dev": metrics, "gpu": status})
            write(a.output / "history.json", history)
            print(
                json.dumps(
                    {
                        "step": step,
                        "loss": value,
                        "groups": metrics["groups"],
                        "gpu": status,
                    }
                ),
                flush=True,
            )
            require_safe_temperature(status, resource_policy)
            if (
                metrics["groups"].get("ordinary", {}).get("correct", 0)
                < before["groups"].get("ordinary", {}).get("correct", 0) * 0.8
            ):
                raise RuntimeError("ordinary decoding collapsed; stop warmup")
    final = model.state_dict()
    unchanged = {}
    keep = [i for i in range(w.shape[1]) if i not in ids.values()]
    for name, old in initial.items():
        new = final[name]
        if name == "head.ctc_head.fc.weight":
            same = np.array_equal(old.numpy()[:, keep], new.numpy()[:, keep])
        elif name == "head.ctc_head.fc.bias":
            same = np.array_equal(old.numpy()[keep], new.numpy()[keep])
        else:
            same = np.array_equal(old.numpy(), new.numpy())
        if not same:
            raise ValueError("original parameter changed: " + name)
    model.eval()
    paddle.save(final, str(a.output / "initial.pdparams"))
    (a.output / "keys.txt").write_bytes((base / "keys.txt").read_bytes())
    cfg["Global"]["character_dict_path"] = str((a.output / "keys.txt").resolve())
    cfg["Global"]["pretrained_model"] = str((a.output / "initial").resolve())
    (a.output / "model.yml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    result = {
        "source_checkpoint_sha256": sha(base / "initial.pdparams"),
        "source_config_sha256": sha(base / "model.yml"),
        "steps": a.steps,
        "batch": 16,
        "learning_rate": a.learning_rate,
        "only_new_ctc_columns_changed": True,
        "ctc_parameter_l2_disabled": True,
        "new_symbols": ids,
        "before": before,
        "after": history[-1]["dev"],
        "seconds": time.monotonic() - started,
        "gpu_peak_allocated_bytes": paddle.device.cuda.max_memory_allocated(),
        "checkpoint_sha256": sha(a.output / "initial.pdparams"),
        "dictionary_sha256": meta["dictionary_sha256"],
        "dataset_audit_sha256": sha(a.dataset / "audit.json"),
        "script_sha256": sha(Path(__file__)),
        "formal_acceptance": False,
    }
    write(a.output / "audit.json", result)
    print("warmup completed", flush=True)


if __name__ == "__main__":
    main()
