# OCR 更新工具的维护边界

本目录保留六路线数据准备、训练、导出和 MAA 原接口验证。正式执行路径为 `pipeline.py` 子命令；图片、字体、权重与运行结果都在显式指定的外部 `--runtime` 下。源码提交中的结果数字只说明已验证的候选，不意味着运行一次命令就批准发布。

| 职责 | 正式入口与代码 | 输入、输出和边界 |
|---|---|---|
| 素材与数据 | `fetch`、`corpus`、`generate`；`source_assets`、`recipe_dataset`、`core_training_data`、`scene_style` | 锁定素材和字典，按真实字段及显式语法生成图文配对；逐图保存来源、参数、像素哈希，整份数据经过 `training_preflight` 审计才可入计划。`scene` 重建完整画面仅用于开发，不自动成为训练集。 |
| 数据契约 | `dataset_contract`、`label_contract`、`text_targets` | `split` 和 `text_partition` 必须一致且只为 `train/dev`；预留、真实验收图不能被训练入口接纳。审计、计划、训练消费同一契约。 |
| 训练 | `plan`、`train`；`prepare_training_plan`、`core_trial_train`、`training_batches`、`training_state`、`machine_resources` | 计划锁定数据、配方、权重、代码及发布库；训练入口负责编排和有限步数循环，批次预处理/开发评分、资源策略、原子恢复分开维护。驻留内存的输入张量在加载前给出估算；实际峰值还包含临时副本。 |
| 导出和选版 | `export-check`；`multilingual_verify`、`checkpoint_select`、`repair_onnx_attributes` | 每次评估独占模型目录；旧 pack 只链接到该次评估的产物并记录 ONNX 哈希。PIR 属性修复只有 `pipeline/scripts/repair_onnx_attributes.py` 一份实现；旧 `scripts/model/` 入口是兼容转发。最终仍须比较 eager、PIR、ORT 和发布运行库。 |
| MAA 验收 | `freeze-evaluation`、`evaluate`、`package`；`acceptance_cases`、`evaluation_policy` | 业务真值、分析器成功状态和原始识别分开判断。`evaluation_policy` 只接受收集好的结果，不加载 Paddle 或 MAA。打包只收六条路线的 ONNX/字典，保留逐文件哈希。 |

`file_utils`、`case_io`、`dataset_contract`、`evaluation_policy` 可在没有 GPU、Paddle、MAA 运行目录的环境中导入和测试。`asset_utils` 才负责字体覆盖和素材哈希；原 `rendering.py` 未进入正式生成链的字形图集实现已移到 `experimental/`，不会因存放在仓库里就自动参与训练。历史 `raw/final`、`raw/v3`、`raw/real` 来源推断集中在 `evidence_provenance`，新清单必须显式写 `evidence_kind`。

## 配置是否真正生效

| 文件 | 读取者 | 地位 |
|---|---|---|
| `configs/recipes/refresh-v2/recipe.json` | `generate`、`plan`，训练读取冻结后的路径 | **执行配置**：种子、场景数量、路线模型、采样策略及其文件路径。基础集 Char 为 10,000 张训练图，再按显式扩量命令形成 20,000 张正式训练图；计划按正式数量验收。`refresh-v1` 留存旧权重历史哈希，不作为新计划入口。生成记录配方哈希，计划校验数量、模型、采样和字典，再锁定解析结果。改动要新建版本并重新生成计划；现有权重不因此自动更新。 |
| `configs/training-recipe-v4.json` | `generate` 默认读取；`plan` 读取 spec 中的 profile 路径 | **执行配置**：新配方的模型、字典和字体映射；模型与字体选择沿用历史 v3，更新版本和配方说明。`training-recipe-v3.json` 保留历史权重的哈希依据。 |
| `configs/sampling-policy-v1.json` | `recipe_sampling`，由上述配方指定路径 | **执行配置**：实际训练曝光比例，和保存的图片数量分离。 |
| `configs/dataset/split-policy.json` | `dataset_contract` | **执行配置**：文字哈希分区；审计与训练还核对清单两个分区字段相同。 |
| `configs/resource-policy.json` | 训练和韩文字典预热；正式计划锁定文件哈希 | **执行配置**：GPU 编号、显存/温度/磁盘阈值。先核对物理 GPU 数量，再查询训练卡；当前只支持单卡、无 CUDA 设备重映射的环境。 |
| 个人 `train-spec.json` | `plan` | **执行输入**：训练步数、学习率、batch、初始权重、guard 和发布接口评估。Char 定向返工的 2e-6 属于此处，不由基础配方暗改。 |
| `configs/recipes/refresh-v1/route-strategies.json` | 显式执行 `audit-pool --strategies` 时读取 | **审计输入**：记录路线取舍；不影响 `generate` 或 `train` 的默认行为。 |
| `configs/recipes/refresh-v1/decision-record.json` | 无自动消费者 | **历史结论**：原 `final-training-v1.json` 改名；更改它不会影响生成或训练。 |

## 发布接口和验证层级

原生探针适配锁定的 **MAA v6.18.0 Linux x64 ABI**、其 FastDeploy/ORT 与任务资源；`runtime.lock.json` 固定发布源码、动态库和预训练权重身份。新 MAA 版本需重新编译并验证原生适配、任务规则、资源路径与输出，不可只改 release tag。Windows 候选部署验证是另一层，不由 Linux 单元测试替代。

在 `common/OCR` 运行 `uv run --project environments/train python -m pytest tests -q` 是 CPU 代码与入口检查；包括分区冲突、整帧失败、同名训练目录导出隔离，以及命令加载。正式数据生成、GPU 微调、发布库原生探针、Windows GUI/发布包按 README 和 `workflows.md` 另行执行。历史冻结计划包含旧源码和绝对路径哈希；代码整理后必须重建新计划，不能对旧计划悄悄续训。历史权重和原始证据保持不变。
