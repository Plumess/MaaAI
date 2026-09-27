#!/usr/bin/env bash
MAA_OCR_PROJECT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${MAA_OCR_RUNTIME:?Set external runtime root}"
export MAA_OCR_PROJECT MAA_OCR_RUNTIME
