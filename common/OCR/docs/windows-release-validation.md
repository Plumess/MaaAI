# Windows 与发布集成验证指南

这份指南记录交给 Windows 端 GPT/执行者的验收口径。formal-v2 已于 2026-09-27 按该口径完成 Char 增量验证，结论为 `pass_cn_integration`；执行结果见 [Windows formal-v2 增量验证结果](windows-formal-v2-result.md)。formal-v1 的全量资源隔离、业务回放和性能记录继续作为历史对照。全过程只做离线图片分析和资源加载，不执行购物、作战或账号修改。

## 1. 固定输入

准备以下文件并先核对 SHA-256：

| 文件 | SHA-256 |
|---|---|
| 官方 `MAA-v6.18.0-win-x64.zip` | `02347e3a589d8030562e693feb2cb063a2c76e0880b6553b4aa94ed327956ca3` |
| `candidate-recognition-resources.zip` | `e32dad96ef88a452b339a51a6ae7bc0e5548a5d115e5f3c7ac2ea5b3f1a4f964` |
| 候选 `asset-index.json` | 以交接包内文件为准，并与 `final-training-evidence.json` 的 `candidate_package` 对照 |

PowerShell：

```powershell
Get-FileHash .\MAA-v6.18.0-win-x64.zip -Algorithm SHA256
Get-FileHash .\candidate-recognition-resources.zip -Algorithm SHA256
```

哈希不符时停止，不自行重新压缩或混用 nightly/dev 构建。

formal-v2 相对已验证的 formal-v1 只允许下列文件变化：

```text
resource/PaddleCharOCR/rec/inference.onnx
SHA-256: 27547490f5232685c0e67d485168ff482a502b9d8f1b6fde4d6c0185e1f21106
```

Char 字典和五条 WordOCR 模型/字典必须与 formal-v1 逐字节一致。

## 2. formal-v2 增量验收

1. 从官方 v6.18.0 解压一份新的候选目录并覆盖 formal-v2 资源；与官方比较时仍只能有索引列出的 12 个识别资源变化。
2. 再与已验证的 formal-v1 候选比较；只能有上面列出的 Char ONNX 一项变化。
3. 复跑 `0-1` 原始裁剪和完整 `StageDropsImageAnalyzer`，必须返回 `0-1`；复跑 `OF-F4`、`10-3`、`10-16`、费用 `0`，必须保持正确。
4. 重放原 10 项国服业务案例；不得出现新增真值错误或业务输出变化。
5. 两侧均从全新进程成功加载资源。无需重复 12,000 次性能测试；沿用 formal-v1 的记录，并标明 formal-v2 未重测性能。

通过条件：资源差异符合 12 项/1 项两层白名单，核心场景全部正确，10 项业务无新增差异。否则返回 `needs_fix`。

## 3. 完整 A/B 目录建立方法（仅在不能复用 formal-v1 证据时）

1. 将官方 ZIP 解压两次为 `maa-official` 和 `maa-candidate`。
2. 将候选 ZIP 解到单独的 `candidate-staging`；只把其中 `resource\...` 覆盖到 `maa-candidate`，不要复制顶层 `asset-index.json`。
3. 两边使用独立的用户目录和日志目录，避免模型缓存或设置互相污染。
4. 用 `asset-index.json` 生成允许替换路径清单。递归比较两个 MAA 目录：**变化只能出现在索引列出的 12 个识别模型/字典路径中**。检测模型、任务 JSON、DLL、模板和其他资源只要变化就判定准备失败。
5. 分别记录两边 12 个目标文件的实际 SHA-256。候选侧必须逐项等于索引值。

本候选的语言布局是：简中、繁中、英文、日文使用各自 PP-OCRv6 small 权重；韩文使用 Korean PP-OCRv5 mobile；Char 使用 PP-OCRv6 small ASCII 子集。不要把五条 Word 路线合并成一份权重，也不要给韩文换成 v6。

## 4. 先做加载与资源检查

分别从全新进程启动 A/B：

- 确认 MAA 版本显示 v6.18.0，目标架构为 x64。
- 确认没有模型加载、字典长度、输出维度、ONNX 算子或 DLL 错误。
- 保存完整日志，并记录 Windows 版本、CPU、内存、GPU、MAA UI/核心版本、所选推理设备和线程数。
- 若使用 MAA 开发版承载截图工具，核心与资源必须仍固定为 v6.18.0；任何额外代码差异都写入 `environment.json`。

## 5. 国服必测场景

A/B 必须读取**完全相同的原始 1280×720 图片**，不重新截图、不改变缩放。优先复用交接的 8 张独立国服截图，再补当前版本新截图。至少覆盖：

| 场景 | 必查结果 |
|---|---|
| 公招标签 | 五个标签文字、重复/缺失、分析是否成功 |
| 仓库材料，两页以上 | 每个已返回物品的数量；“全部”页双方共同失败要单列，不能算通过 |
| 信用商店 | 商品名称、重复名称、白名单/黑名单后的顺序和数量 |
| 战斗费用 | 小数字、`0/O` 易混、任务区域是否命中 |
| 关卡结算 | 关卡号、难度、三星、掉落 ID/数量/类型 |
| 当前 UI 主题或皮肤 | 相同文字在不同背景/主题下是否仍可读 |
| 长名称、标点和空格 | 原始识别与 MAA 替换后的业务结果都要保留 |

真值来自画面可见文字和任务语义。旧模型输出只能作对照，不能当标签。记录四类结果：候选修复、候选新增错误、双方都正确、双方都错误。只有“候选无新增真值错误且所有国服必测项正确”才写国服通过。

推荐使用本分支的 `maa_acceptance_probe.cpp` 构建 Windows 小工具。它的调用契约是：

```text
maa_acceptance_probe.exe RELEASE_DIR CLIENT CHAR_PACK WORD_PACK cases.jsonl output.json
```

它调用 v6.18.0 的 `RecruitImageAnalyzer`、`DepotImageAnalyzer`、`CreditShopImageAnalyzer`、`StageDropsImageAnalyzer` 和 `RegionOCRer`，不会创建控制器或执行游戏动作。若直接使用 MAA 开发版功能，也必须导出等价的逐案例 JSON，而不是只写“看起来正常”。

## 6. 外服验证

繁中、英文、日文、韩文仍需要真实客户端图片。每个可用客户端先覆盖公招、关卡号、数量/费用、长名称、标点/空格和至少一种不同主题。没有某服账号时直接标记 `not_tested`，不要用国服换语言文本或合成图代替。

外服结果不会推翻已经独立通过的国服结论，但在对应语言实图通过前，不能宣称整套多语言资源已完成发布验收。

## 7. 性能只记录，不设硬门槛

固定同一台机器、同一后端、线程数和图片顺序，A/B 交替执行：每轮预热 30 次，再测 1,000 次，共 3 轮；另各起 10 个新进程记录模型加载和首次识别。返回每次原生 OCR 调用耗时，并汇总冷启动、首次调用、热 P50/P95、峰值内存和候选/官方响应时间比率。

本轮不使用 1.05 作为阻塞条件，也不为得到更好数字挑选轮次。若工具测到的是整个进程或整项任务耗时，明确写出，不能标成单次 OCR 响应时间。DirectML/WebGPU 等新后端另开一组对照，不与本次 CPU 模型替换混算。

## 8. 必须交回的目录

```text
windows-char-delta-v2/
  environment.json
  file-hashes.json
  cases.jsonl
  captures/                 # 原图；公开前自行去除隐私
  official-output.json
  candidate-output.json
  timing-raw.json
  summary.md
  logs/
```

`summary.md` 只需写：环境、已测场景、候选改善、候选新增错误、双方共同错误、未覆盖项、性能记录、最终判断。最终判断只能是：

- `pass_cn_integration`：国服加载与业务通过；外服按实际状态另列。
- `needs_fix`：候选新增错误、加载失败或出现非 OCR 资源差异。
- `incomplete`：材料、真值或场景不足，不能判断。

把整个目录打包，另附压缩包 SHA-256。不要把账号截图、用户配置或日志直接提交到公开 PR；PR 只引用摘要和可核对哈希。
