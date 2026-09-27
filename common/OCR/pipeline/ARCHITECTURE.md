# 当前 OCR 训练代码怎么找

在 `common/OCR` 执行 [README](README.md) 的命令。唯一对外入口是 `pipeline.py`；它只分发命令，不藏训练逻辑。`environment/` 保存 v5/v6 共用 Python 依赖，`configs/` 保存本次可执行配方和素材身份，`scripts/` 保存实现，`native/` 保存与固定 MAA 发布接口对齐的探针。图片、权重和运行结果必须写到外部 `--runtime`。

| 要做的事 | 入口 | 主要实现与约束 |
|---|---|---|
| 建环境和取素材 | `setup`、`doctor`、`fetch`、`corpus` | `setup_runtime`、`source_assets`、`source_corpus`；固定第三方提交和 SHA-256，提取游戏字段时保留 JSON 指针 |
| 准备模型和数据 | `prepare-model`、`generate`、必要时 `char-rework` | `prepare_model` 映射预训练字典；`recipe_dataset`、`core_training_data`、`scene_style` 生成和重放；`training_preflight` 整份拒绝错误标签、泄漏或不可编码样本；Char 真实裁剪只进训练集 |
| 冻结并训练 | `plan`、`train` | `prepare_training_plan` 固定数据、配置、权重和发布接口；`core_trial_train`、`training_batches`、`training_state` 处理批次、恢复和资源限制 |
| 导出与交付 | `export-check`、`package` | `multilingual_verify` 比较 Paddle、PIR、ONNX 和 MAA 发布接口；`package_candidate` 只打包已选六路线 rec 模型与字典 |
| 比较指标 | `freeze-evaluation`、`evaluate` | `acceptance_cases`、`evaluation_policy` 区分真值、任务变化和响应时间；原版与候选使用同一发布库、规则和输入 |

当前会驱动训练的配置是 `recipes/refresh-v2/recipe.json`（数量、种子、路线与采样）、`training-recipe-v4.json`（模型与初始权重路线）、`sampling-policy-v1.json`（训练曝光）、`styles.json` 与 `fonts.json`（图像外观和字形）、`dataset/recipe-contract-v3.json` 与 `dataset/split-policy.json`（数据约束），以及 `resource-policy.json`（机器约束）。`ascii_keys.txt` 和 `korean_keys.txt` 是输出类别顺序，不能重新排序。

`training-recipe-v4.json` 的 `scope` 仍提到已退出正式入口的 `route-strategies.json` 审计工具。这是冻结配置中的历史说明字段，执行代码不读取该字段；为保持既有数据和模型证据中的 profile 哈希，文件原样保留。当前采样实际由 `refresh-v2/recipe.json` 指向的 `sampling-policy-v1.json` 驱动。

`dataset/word-assets.lock.json`、`dataset/scene-text-assets.lock.json`、`render-assets.lock.json` 固定本次游戏字段、字体及画面素材；`sources.lock.json`、`weights.lock.json`、`runtime.lock.json`、`tools.lock.json` 和 `native-toolchain.lock.txt` 固定第三方源码、预训练权重和发布接口。这些锁是**训练输入**，并非仅供阅读的报告。一个新游戏版本需要新的素材锁、数据审计和训练计划；同名旧工作目录里出现不同哈希会被拒绝。

当前 `word-assets.lock.json` 与 `render-assets.lock.json` 重复列出部分相同字体：重复取材只会核对同一目标文件，不会生成两份素材。为了维持本轮冻结输入哈希，没有就地改动这两个锁；下一次建立新版本素材锁时应合并重复记录，并检查所有游戏数据文件是否来自同一版本。

`configs/train-spec.example.json` 是需要复制到外部工作目录并填写路径的示例，不是本次训练的原始计划。`docs/final-training-evidence.json` 等报告记录既有候选结果，不被命令当作默认输入。旧版本配方与开发期试验代码可由 Git 历史查阅，不再与当前可执行配置混放。

在 `common/OCR` 运行 `uv run --project pipeline/environment python -m pytest tests -q` 检查代码契约与命令入口；完整数据生成、GPU 训练、Linux 原生探针及 Windows 发布集成仍需各自的实际环境。本次整理改变了源码身份，不能用旧冻结计划续训，也不把既有权重的历史报告改写成新代码的实测结果。
