#!/bin/bash
# コードチェックスクリプト
# Python (ruff + pyright) と TypeScript/Vue (eslint + vue-tsc) の両方をチェックし、
# どちらかでエラーが出た場合は非ゼロの終了コードで終了する

set -euo pipefail

PYTHON_EXIT=0
CLIENT_EXIT=0

# ============================================================
# Python lint: ruff + pyright
# ============================================================
echo "================================================================"
echo " Python lint: ruff check --fix + pyright"
echo "================================================================"
cd /code/server
if ! poetry run task lint; then
    PYTHON_EXIT=1
fi

echo ""

# ============================================================
# TypeScript/Vue lint: eslint + vue-tsc
# ============================================================
echo "================================================================"
echo " Client lint: eslint"
echo "================================================================"
cd /code/client
if ! yarn lint; then
    CLIENT_EXIT=1
fi

echo ""
echo "================================================================"
echo " Client typecheck: vue-tsc"
echo "================================================================"
if ! yarn typecheck; then
    CLIENT_EXIT=1
fi

# ============================================================
# 結果サマリ
# ============================================================
echo ""
echo "================================================================"
echo " Summary"
echo "================================================================"
if [ "$PYTHON_EXIT" -eq 0 ]; then
    echo " [PASS] Python (ruff + pyright)"
else
    echo " [FAIL] Python (ruff + pyright)"
fi
if [ "$CLIENT_EXIT" -eq 0 ]; then
    echo " [PASS] Client (eslint + vue-tsc)"
else
    echo " [FAIL] Client (eslint + vue-tsc)"
fi
echo "================================================================"

# どちらかが失敗していれば非ゼロで終了
if [ "$PYTHON_EXIT" -ne 0 ] || [ "$CLIENT_EXIT" -ne 0 ]; then
    exit 1
fi
exit 0
