# 后续维护怎么使用

先按[环境说明](README.md)建立外部 `OCR_WORK`。以下命令在 `common/OCR` 执行，统一前缀为：

```bash
ocr() { uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" "$@"; }
```

所有写出目录使用新名字，旧证据不覆盖。各命令的 `--help` 显示参数。JSON中的外部素材引用为 `{"path":"相对OCR_WORK的路径","sha256":"实际哈希"}`；评估、训练、打包spec中的路径相对spec所在目录，也可用绝对路径。

## 接收和校准新素材

```bash
ocr capture-unpack --archive captures.zip --output "$OCR_WORK/captures/unpacked-v1"
ocr capture-import --package "$OCR_WORK/captures/unpacked-v1/package-name" --output "$OCR_WORK/captures/intake-v1"
ocr review --source "$OCR_WORK/review-draft.json" --output "$OCR_WORK/review.html"
ocr review --source "$OCR_WORK/review-draft.json" --review "$OCR_WORK/ocr-reviewed.json" --output "$OCR_WORK/review-check.json"
ocr calibrate --config "$OCR_WORK/calibration.json" --output "$OCR_WORK/calibration-v1"
ocr scene --config "$OCR_WORK/scene.json" --output "$OCR_WORK/scenes-v1"
ocr scene --output "$OCR_WORK/scenes-v1" --audit-only
```

截图包包含 `images/`、`capture-index.csv`；ZIP校验另要求 `image-checksums.json`。CSV列由 `capture_intake.FIELDS` 定义，包含会话、源图组、服务器/语言、场景、主题和原图/缩放/裁剪关系。不要以OCR预测填充“已确认真值”。

复核文档包含 `source_manifest_sha256` 和 `frames`；每帧含 `id,image_uri,image_sha256,scene,theme,regions`。本工具框坐标基于1280×720的MAA输入；保留其与原始截图的关系。每个区域含 `id,box_xywh,proposed_label,review_status`，明确复核后才填写 `confirmed_label,reviewer`。复核成功不自动使材料成为独立评判集。

`calibration.json` 的 `method` 为 `font`、`template` 或 `plane`；`regions`逐项给出 `id,role,source,roi_xywh`，必须同时有 `fit` 与 `check`。`font`另提供可见 `label,polarity`、`fonts`列表和 `search`（`font_sizes,stroke_widths,render_scales,horizontal_scales`）；`template`另给每项 `template`素材引用。输出记录拟合与检查结果，不能把外观重合度解释为OCR准确率。

场景配置包含 `background,source_session,language,scene,slots,variants,profiles`。每个slot明确 `erase_xywh,donor_xywh,text_slot_xywh,foreground,style`；style使用已校准的 `font,font_size,render_scale,stroke_width,horizontal_scale`。variant中的 `labels`须与slot一一对应，含 `label,source`；profile含 `scale,blur,jpeg_quality`。取色区不平坦、字形溢出会停止，不通过缩字或截标签掩盖问题。输出总是开发数据，同时保存配置、原图来源、上下文、文字mask和逐图记录。

## 生成、字典与训练

按README生成六路线图片，再用实际采样策略审计，而不是只报磁盘图片数：

```bash
ocr audit-pool --dataset "$OCR_WORK/data/recipe-v1" --strategies pipeline/configs/recipes/refresh-v1/route-strategies.json --presentations 16000 --output "$OCR_WORK/exposure-v1.json"
# --base 指向旧数据池，可额外检查嵌套扩量与开发图不变。
```

[路线策略](configs/recipes/refresh-v1/route-strategies.json)保留已选方案：简中/日文/韩文按用途，繁中/英文保留历史长度配比，Char保留关卡/费用/ASCII的已胜出配比。Char其它场景仍生成并评估，不谎称所有图片都被训练抽到。1万/2万实验的意义及限制见[历史结果](../docs/final-training-report.md#数据量为什么停在这里)。新任务允许重新验证后调整配比，不将旧设计当定理。

韩文先 `prepare-model`，生成数据后按需执行已有验证过的新增类别准备：

```bash
ocr warm-symbols --model "$OCR_WORK/models/ko" --dataset "$OCR_WORK/data/recipe-v1" --steps 400 --output "$OCR_WORK/models/ko-warm-v1"
```

这条命令**会训练**；只针对★《》三个新CTC列，保留普通样本抑制误触发，关闭会改变旧列的L2衰减；输出前检查旧参数逐项不变。它不是完整微调或验收。后续韩文spec使用该目录的 `initial.pdparams/model.yml`，不得将新增字典直接配给旧输出头。ASCII继续按token映射，不改成v5英文基底。

真实 Char 失败样本可在复核后建立定向返工集：

```bash
MAA_OCR_RUNTIME="$OCR_WORK" uv run --project environments/train python pipeline/scripts/char_rework_dataset.py \
  --base "$OCR_WORK/data/final-dataset-v1" --spec "$OCR_WORK/char-rework/source-spec.json" \
  --output "$OCR_WORK/data/char-rework-v2"
```

spec 中每张图必须固定原图哈希、可见标签、发布任务 ROI/二值阈值、复核状态和训练变体数。输出保留真实来源会话，只允许已确认且明确 `training_eligible` 的训练图；所有派生图禁止进入独立验收。

正式训练仍使用显式 `plan → train`。步数、batch、学习率、初始权重、保留能力集及评估清单以冻结spec为准；生成profile不隐式决定训练预算。原模型已有合格候选时不为执行流程而重训。

## 冻结评判和执行原接口检查

`freeze-evaluation`的spec格式如下，可加入其它路线/旧开发保留能力清单：

```json
{"routes":{"ko":[{"manifest":"data/recipe-v1/ko/dev/manifest.jsonl","prefix":"v3","subset":"new_recipe","evidence_kind":"synthetic","selection":"scene-hash-and-length"}]}}
```

`scene-hash-and-length`每场景取哈希排序前30张及最长10张并去重；`all`保留整份已有清单。每个新来源要声明 `evidence_kind`：合成开发图为 `synthetic`，经复核的真实裁剪为 `reviewed_real`。只有已冻结的 `final`、`v3` 和 `real` 旧前缀允许沿用原分类；其余缺失来源类型会直接拒绝，避免真实图因编号变化失去回归保护。明确拒绝训练集及预留测试集被这个开发选样入口消费。原文真值保持可见文字；干员名按固定官方角色ID映射为内部名称，数量单位单列任务规则目标。

```bash
ocr freeze-evaluation --spec "$OCR_WORK/eval-inputs.json" --output "$OCR_WORK/frozen-dev-v1"
ocr inspect-rules --route ko --input "$OCR_WORK/rule-cases.json" --output "$OCR_WORK/rules-v1"
ocr evaluate --spec "$OCR_WORK/evaluation.json" --output "$OCR_WORK/evaluation-v1"
```

规则输入是JSON列表，每项为 `id,task,raw`，可提供 `required`。调用的是发布库本身的继承、trim、replace和required检查；不更新任务JSON。

评估spec示例：

```json
{
  "purpose": "evaluation",
  "timing_policy": "record_only",
  "packs": {"zh-CN":"models/cn-pack", "char":"models/char-pack"},
  "frames": "frames.jsonl",
  "recognition": {"zh-CN":"frozen-dev-v1/zh-CN.jsonl"},
  "timing": {"zh-CN":"timing-cn.jsonl"}
}
```

三种工作负载可独立选择；整帧需要对应语言和Char两套候选。每个pack包含 `rec/inference.onnx,rec/keys.txt,det/inference.onnx`，检测文件必须与原发布版一致。原版pack由程序依官方语言覆盖路径解析；同一运行库、规则、模板、图片和线程配对比较，冻结文件前后核验。

整帧案例为 `id,image,sha256,route,mode,truth,source_scope`；mode支持 `stage_drops,recruit,credit_shop,depot,task_region`。`truth`按实际检查项提供 `stage_code,analyze_ok,texts`或带框数量 `fields`；商店顺序与重名不能丢弃。`task_region`另需 `task_name`。只跑离线分析器，不点击游戏、不购买或上报。

正式计时固定3轮、每轮各预热30次/测1000次、各10个冷进程，返回原生单次时间、P95响应时间比率和内存。`purpose: integration`允许显式缩小 `budget`检查工具，但结果标记为不适用正式速度门槛。本轮正式评估使用 `timing_policy: record_only`：保留 P95 与超过 1.05 倍的诊断记录，但仅任务/识别质量回归返回非零。以后确需恢复速度否决时，显式选择 `enforce`；两种模式都不改变配对计时预算。完成运行不等于批准发布。Windows CPU/ONNX Runtime 的国服发布集成已按[代验说明](../docs/windows-release-validation.md)完成；外服实图仍需补测。

## 给验证者打包

```bash
ocr package --spec "$OCR_WORK/package.json" --output "$OCR_WORK/handoff-v1"
```

spec含全部六路线 `packs`，以及 `expected_sha256`（键为MAA最终资源相对路径，值为已选文件哈希）。只输出模型/字典12个文件及索引；不修改本地MAA安装，也不夹带检测模型、任务JSON或运行库。打包不是发布审批，原候选文件哈希须与[当前资源索引](../docs/final-training-evidence.json)核对。

代码回归：`uv run --project environments/train python -m pytest tests -q`。完整测试用合成固定样例检查契约，不需要游戏账号/GPU/实验目录；原生衔接检查需要README中的固定发布依赖。
