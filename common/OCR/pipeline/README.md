# 可复现的数据、训练与导出入口

这套入口从已有试验代码整理而来，覆盖五语言 WordOCR 和独立 Char 子集。它保留逐图来源、固定预算、断点恢复与实际 MAA 导出检查；不把合成图或开发集成绩当成完整发布验收。

代码位于本目录，所有字体、游戏资源、模型、数据和运行输出放到调用者指定的外部目录。路径不依赖原试验场，也不修改已安装的 PaddleOCR。当前实际适配并测试的是 Linux x64、NVIDIA GPU、由锁文件固定的 MAA v6.18.0 接口；Windows 用于候选部署验收，不在这里宣称训练平台兼容。

数据集契约放在 `configs/dataset/`，公开素材下载到外部运行目录的 `data/assets/`。早期实验记录中的 `s2` 是当时的工作阶段名；历史冻结清单和已训练权重保留原样，新入口不依赖该阶段目录名。

[完整维护流程](workflows.md)另列截图接收、离线复核、外观校准、数据量审计、韩文新增类别训练、冻结评判、整帧/计时及资源打包；[迁移核对](../docs/migration-audit.md)说明每项试验代码的去向。

[代码架构与配置生效范围](ARCHITECTURE.md)列出正式路径、试验路径，以及执行配置、审计输入和历史记录的区别。

## 1. 环境与固定依赖

在 `common/OCR` 目录执行。下文 `$OCR_WORK` 是你选择的外部工作目录；示例 `/path/to/ocr-runtime` 必须替换。不要将它放入 Git。

```bash
export OCR_WORK=/path/to/ocr-runtime
mkdir -p "$OCR_WORK"
export UV_PROJECT_ENVIRONMENT="$OCR_WORK/envs/train"
export UV_CACHE_DIR="$OCR_WORK/cache/uv"
uv sync --project environments/train --locked
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" setup --native
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" doctor
```

`setup` 只下载固定版本到指定目录：PaddleOCR、MAA 发布源码、MaaUtils、发布包、预训练权重；`--native` 另装固定的本地编译器，构建发布预处理、OCR 和张量探针。现有版本或哈希不匹配时停止，不覆盖现有依赖。版本与文件来源见 `configs/sources.lock.json`、`runtime.lock.json`、`weights.lock.json` 和 `native-toolchain.lock.txt`。环境采用 Paddle 3.4.0 / Paddle2ONNX 2.1.0；升级后需重验转换适配，不能只改版本号。

本轮已在新的外部运行目录中从零建立锁定环境，并完成数据生成、六路线正式训练、恢复、导出和 v6.18.0 原生接口检查。首次安装仍依赖网络、兼容驱动及发布包所需系统 ABI；精确环境和结果见[正式训练报告](../docs/final-training-report.md)。

## 2. 数据源、字体与语料

```bash
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" fetch --lock pipeline/configs/dataset/word-assets.lock.json
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" fetch --lock pipeline/configs/dataset/scene-text-assets.lock.json
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" fetch --lock pipeline/configs/render-assets.lock.json
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" corpus \
  --lock pipeline/configs/dataset/word-assets.lock.json \
  --lock pipeline/configs/dataset/scene-text-assets.lock.json \
  --fonts pipeline/configs/fonts.json --output "$OCR_WORK/corpus.jsonl"
```

`fetch --offline` 只核对已有文件。语料来自固定提交的 ArknightsAssets/ArknightsGamedata，按明确字段提取各服名称、物品、公招、基建/技能文字；每项保留文件哈希和 JSON 指针。字体覆盖不足、富文本和占位符不会偷偷截断或猜测展开。字体与图集按来源下载，代码仓库不包含这些二进制。

语料合并与模型字典合并是两件事：语料可统一管理并按语言/任务选择；v6 保留官方字符顺序，Char 按 ASCII 子集映射，韩文按实际缺失字符追加。不能将多语言 keys 排序合并后直接配给已有预训练输出层。

## 3. 准备输出层和生成数据

为通用 v6、ASCII 和韩文生成带绝对字典路径的模型配置。输出目录必须是新目录；模型准备只调整字典对应关系，不代表已经微调或证明精度。

```bash
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" prepare-model \
  --config "$OCR_WORK/vendor/PaddleOCR/configs/rec/PP-OCRv6/PP-OCRv6_small_rec.yml" \
  --checkpoint "$OCR_WORK/weights/PP-OCRv6_small_rec_pretrained.pdparams" \
  --dictionary "$OCR_WORK/vendor/PaddleOCR/ppocr/utils/dict/ppocrv6_dict.txt" --output "$OCR_WORK/models/word"
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" prepare-model \
  --config "$OCR_WORK/vendor/PaddleOCR/configs/rec/PP-OCRv6/PP-OCRv6_small_rec.yml" \
  --checkpoint "$OCR_WORK/weights/PP-OCRv6_small_rec_pretrained.pdparams" \
  --dictionary pipeline/configs/ascii_keys.txt --output "$OCR_WORK/models/char"
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" prepare-model \
  --config "$OCR_WORK/vendor/PaddleOCR/configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml" \
  --checkpoint "$OCR_WORK/weights/korean_PP-OCRv5_mobile_rec_pretrained.pdparams" \
  --dictionary pipeline/configs/korean_keys.txt --output "$OCR_WORK/models/ko"
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" generate \
  --recipe-config pipeline/configs/recipes/refresh-v2/recipe.json \
  --style-recipe pipeline/configs/styles.json --corpus "$OCR_WORK/corpus.jsonl" \
  --output "$OCR_WORK/data/pilot" --pilot
```

先生成 pilot：六路线、各六类、训练/开发各 10 张，共 720 张；逐图重放、来源/标签/字典/分组检查全部通过才写 `audit.json`。正式数据分两次生成：

```bash
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" generate \
  --recipe-config pipeline/configs/recipes/refresh-v2/recipe.json \
  --style-recipe pipeline/configs/styles.json --corpus "$OCR_WORK/corpus.jsonl" \
  --output "$OCR_WORK/data/base"
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" generate \
  --recipe-config pipeline/configs/recipes/refresh-v2/recipe.json \
  --style-recipe pipeline/configs/styles.json --corpus "$OCR_WORK/corpus.jsonl" \
  --expansion-base "$OCR_WORK/data/base" --expansion-route char \
  --output "$OCR_WORK/data/formal"
```

基础集每条 Word 路线与 Char 各有 10,000 训练图 + 2,000 开发图，共 72,000 张；只扩 Char 后共 82,000 张，Char 为 20,000 + 2,000。正式 Char 计划要求扩量后的数量；扩量只是本次冻结配方的选型，不代表任意扩量都有收益。训练曝光比例由配方指定的 `sampling-policy-v1.json` 控制。
`refresh-v1` 与 `training-recipe-v3` 保留为既有权重的历史哈希依据；前者把 Char 基础数量误写为扩量后数量。新生成和新冻结计划使用修正后的 `refresh-v2` 与 `training-recipe-v4`，后者的模型、字体映射与 v3 相同。不能拿新配置哈希冒充历史训练记录。

`styles.json` 是从校准结果中提取的字体/字号/形状及公开背景引用，不包含私人截图。外服字体/主题外观仍需实际画面对照。照片、原图组件替换用独立的 `scene --config ... --output ...`：配置明确背景来源、擦除/取色区、文本槽、字形样式、文字来源、缩放模糊参数；这类输出始终为开发数据，不能混入训练或独立评判集。配置格式由 `scripts/scene_dataset.py:build` 定义，拒绝文本溢出和无来源标签。

## 4. 冻结计划后再训练

复制 `configs/train-spec.example.json` 到自己的工作目录，填写真实路径和路线。必须提供：已校验的数据集、训练 profile、初始模型与模型配置、保留能力样本清单，以及同一评判清单下旧发布模型/当前候选的原生预测。不可拿待训练模型的答案当真值，也不能为空缺材料自动生成“通过”。

- `guard_manifest` 每行包含 `id,image,sha256,label,scene`；若为 ASCII 字面样本，保留 `literal_ascii`。
- `evaluation.manifest` 每行另含 `mode,expected_output,subset`，任务模式需 `task_name`；图像路径为绝对路径，由原生探针读取。
- 两份参考预测是发布接口探针的 `{"predictions":[...]}` 输出，案例 ID 必须与评判清单完全一致。
- 新评判清单的原文案例必须携带 `evidence_kind`：合成图为 `synthetic`，已复核真实图为 `reviewed_real`。旧 `raw/final/`、`raw/v3/`、`raw/real/` 清单按原前缀兼容；其它未标来源的案例会被拒绝。
- 路线选 `zh-CN/zh-TW/en/ja/ko/char`；初始配置分别使用 word/ko/char 的 `model.yml`。自己的材料位置和预算全部写进新 spec，不修改旧冻结证据。

```bash
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" plan \
  --spec "$OCR_WORK/train-spec.json" --output "$OCR_WORK/plan.json"
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" train \
  --plan "$OCR_WORK/plan.json" --output "$OCR_WORK/runs/train-01" --print-command
# 审阅冻结输入后，去掉 --print-command 才真正开始；中断后加 --resume。
```

计划会锁定数据、代码、权重、字典、发布规则、运行库与参考结果。正式计划要求原生 MAA 评估及失败停止，不允许通过关闭检查来宣称正式训练。训练设置有限步数、GPU 互斥、空闲显存/磁盘和温度检查；保存两份恢复点、随机状态、采样位置与优化器。GPU 后续计算不保证逐位一致，恢复完整性与质量门槛分开判断。

若真实失败来自 CharOCR，可先用 `scripts/char_rework_dataset.py` 在冻结 Char 数据上加入已复核的真实关卡裁剪。spec 必须记录原图哈希、可见真值、MAA ROI/阈值、复核人和训练变体数；程序只接收 `verified_real_crop` 的训练样本，并强制 `formal_evaluation_eligible=false`。返工仍需新建冻结计划，并把失败裁剪加入原生接口开发评估；不能用训练图冒充独立准确率。完整实例见 [Char 返工结果](../docs/char-rework-result.md)。

本轮正式候选已从官方预训练权重按冻结 spec 完成六路线训练。精确数据、计划、权重和候选哈希见[正式训练证据](../docs/final-training-evidence.json)；外部材料不进入 Git。新一轮训练应重新生成计划并保留新的哈希，不覆盖本轮记录。

## 5. 导出和候选检查

```bash
uv run --project environments/train python pipeline/pipeline.py --runtime "$OCR_WORK" export-check \
  --checkpoint "$OCR_WORK/runs/train-01/recovery/step-0001000/model.pdparams" \
  --config "$OCR_WORK/runs/train-01/model.yml" --manifest "$OCR_WORK/evaluation.jsonl" \
  --kind word --output "$OCR_WORK/runs/export-01"
```

Char 使用 `--kind char`。入口依次导出、按源 PIR 修复属性、执行必要的标准 ONNX 变换、比较 eager/PIR/Python ORT/发布库输出；失败返回非零。`export` 子命令仅导出 Paddle 模型，中间产物不能直接当已验收的 ONNX。训练检查点也调用同一套导出/实际接口检查。

本入口不更换检测器、任务替换规则、MaaDeps 或 DirectML/WebGPU。Windows 资源隔离、发布核心资源注册、国服 A/B 回放和性能记录已经完成，结果见[Windows 验证复核](../docs/windows-validation-review.md)。formal-v2 已在 Linux 和 Windows 原生接口关闭 Char `0/O` 回归，Windows 国服发布集成通过；官方发布版 GUI 已在未修改核心上完成国服公招与仓库识别；发布 DLL 的离线图片内部 OCR 无公开直调接口，外服实图仍需补齐；操作口径见[Windows 与发布集成指南](../docs/windows-release-validation.md)。性能在本轮只记录，不设硬门槛。

正式整帧验收除已标注真值和分析成功状态外，还逐例比较任务输出；未标注的数量、顺序等业务变化默认阻止通过。若人工确认某一处变化正确，可在冻结案例写入 `approved_business_change: {"reason": "复核依据", "candidate_canonical_sha256": "该候选规范化业务输出的 SHA-256"}`。哈希由 `acceptance_cases.business_digest()` 计算；候选输出再变或例外不再适用时必须重新复核。只变置信分数不算业务变化。
