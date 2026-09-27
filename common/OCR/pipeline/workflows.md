# 训练之后如何验收与交付

先按 [训练 README](README.md) 建立环境与数据。以下命令在 `common/OCR` 执行，`OCR_WORK` 是仓库外工作目录：

```bash
ocr() { uv run --project pipeline/environment python pipeline/pipeline.py --runtime "$OCR_WORK" "$@"; }
```

若独立真实截图揭示 CharOCR 的明确错误，复核可见文字、原图哈希及 MAA 的 ROI／阈值后，才用 `char-rework` 把裁剪及有限变体加入**训练**数据。命令要求已审计的冻结基础集和写明 `reviewer`、`review_status`、`source_revision`、`variants` 的来源 spec；输出的图都禁止作为独立验收真值。

```bash
ocr char-rework --base "$OCR_WORK/data/formal" \
  --spec "$OCR_WORK/char-rework/source-spec.json" \
  --output "$OCR_WORK/data/char-rework"
```

需要开发集选版时，用 `freeze-evaluation` 固定图像、真值、来源类别和哈希，再用 `evaluate` 将候选与官方发布资源作同接口配对比较。新来源必须明确 `evidence_kind`：合成图为 `synthetic`，已复核实图为 `reviewed_real`；不能让训练图进入独立验收。

```bash
ocr freeze-evaluation --spec "$OCR_WORK/eval-inputs.json" --output "$OCR_WORK/frozen-eval"
ocr evaluate --spec "$OCR_WORK/evaluation.json" --output "$OCR_WORK/evaluation-result"
```

`evaluation.json` 可分别指定 `frames`、`recognition`、`timing`；整帧案例包含图片、SHA-256、路线、任务模式和人工真值。原版与候选必须使用同一批图片、MAA 发布库、任务规则和线程设置。正式计时采用固定预算并报告 P95 **响应时间比率**；当前 `timing_policy: record_only` 只记录速度，不将其设为模型质量否决项。业务输出若改变而没有明确真值或经复核的例外，评估应失败。

六条路线的 ONNX 与字典选定后，用 `package` 按逐文件 SHA-256 生成交接包；它不改变本地 MAA 安装，也不代表发布审批。

```bash
ocr package --spec "$OCR_WORK/package.json" --output "$OCR_WORK/handoff"
```

来源更新时依次新建素材锁、核对抽取字段／字典／字体、生成新数据、审计场景覆盖、建立新训练计划，再按上述方式比较官方发布版。不要改写旧冻结证据。旧版本结果与当前候选哈希见[正式训练报告](../docs/final-training-report.md)和[机器证据](../docs/final-training-evidence.json)。
