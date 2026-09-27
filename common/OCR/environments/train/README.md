# 经试验的 v5/v6 共用环境

Linux x86_64、Python 3.12、Paddle GPU 3.4.0（CUDA 12.9 wheel）、Paddle2ONNX 2.1.0。
同一环境完成过 v5 韩文与 v6 small 训练、保存/恢复和导出检查；不需要两套 Paddle 环境。
锁文件来自验证环境。需要支持 CUDA 12.9 的 NVIDIA 驱动；本机验证设备为 RTX 4060 Ti 16 GB。
这不是 Windows 训练或 MAA 部署环境；MAA 部署继续使用它自己的运行库。

```bash
cd common/OCR/environments/train
uv sync --locked
# PaddleOCR 源码需单独固定，不使用浮动 main；在任意合适位置执行：
git clone https://github.com/PaddlePaddle/PaddleOCR.git
git -C PaddleOCR checkout b03f46425e8ff4442b268ce449e3eef758146cd4
uv run python -m pytest ../../tests -q
```

本目录提供 v5/v6 共用依赖锁和兼容性测试。六路线的数据生成、训练、导出与验收入口已移入
[便携流程](../../pipeline/README.md)，新工作请从该入口建立外部运行目录和固定依赖。
官方 main 的四份 v3 配置及原有目录仍保留；它们没有自动升级为 Paddle 3 配置，
旧流程继续使用原依赖。新字典必须先按字符映射调整预训练输出层，不能直接替换 keys。

Paddle 3 PIR 导出时发现过 LayerNorm epsilon 属性转换异常。
`../../scripts/model/repair_onnx_attributes.py` 是旧命令的薄转发；唯一实现位于 `../../pipeline/scripts/repair_onnx_attributes.py`，按源参数身份与轴逐层恢复属性，拒绝未知映射；
修复后仍必须比较 Paddle 与 ONNX 输出、解码及实际 MAA 行为，不能把 ONNX checker 通过当作数值一致。

```bash
uv run python ../../scripts/model/repair_onnx_attributes.py \
  --pir /path/to/inference.json --onnx /path/to/raw.onnx \
  --output /path/to/repaired.onnx --report /path/to/repair.json
```

输入要求是带 LayerNormalization 的 ONNX（opset ≥17）；不要把此工具自动套在旧 opset 11 的 v5 导出上。
它是受限兼容工具，保留原始 ONNX，不修改转换容差或统一覆盖成某个 epsilon。
