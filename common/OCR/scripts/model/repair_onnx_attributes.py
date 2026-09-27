"""Compatibility entry for the single maintained OCR export repair implementation."""

import sys
from pathlib import Path

PIPELINE_SCRIPTS = Path(__file__).resolve().parents[2] / "pipeline/scripts"
sys.path.insert(0, str(PIPELINE_SCRIPTS))
from repair_onnx_attributes import main  # noqa: E402


if __name__ == "__main__":
    main()
