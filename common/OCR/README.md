# MAA OCR 识别模型训练

本目录用于生成明日方舟 OCR 训练数据，微调五条 WordOCR 路线与 CharOCR，导出可交给 MAA 的识别模型和指标。简中、繁中、英文、日文及 Char 使用 PP-OCRv6 small；韩文使用 Korean PP-OCRv5 mobile。目录中的旧版 v3 配置和脚本是上游遗留，不是这次训练的入口。

从 [训练流程](pipeline/README.md) 开始：在 Linux x64 上创建独立工作目录，安装 [同一套 v5/v6 环境](pipeline/environment/pyproject.toml)，按固定来源获取游戏文字、字体和预训练权重；生成数据后冻结训练计划，训练、导出并检查与 MAA 当前发布接口的一致性。所有下载素材、图片、检查点、ONNX、日志和完整评估结果都写到仓库外，不提交 Git。

| 目录 | 用途 |
|---|---|
| [pipeline](pipeline/README.md) | 当前可执行的数据准备、训练、导出与交付流程；配置和环境锁都在此处 |
| [docs](docs/final-training-report.md) | 已完成候选的结果、证据与已知验证边界 |
| `scripts/`、`utils/`、`raw_keys/`、旧 yml 与 Dockerfile | 上游 v3 旧流程；不参与 v5/v6 正式入口 |

本轮候选基于 MAA v6.18.0 验证。国服实图与 Windows 发布集成已有记录；外服实图仍需补充。历史数字及权重哈希见[正式训练报告](docs/final-training-report.md)和[机器证据](docs/final-training-evidence.json)。新的游戏数据、模型或 MAA 版本应建立新的素材锁、数据与训练计划，并按同一接口重新评估，不能直接沿用旧结果。
