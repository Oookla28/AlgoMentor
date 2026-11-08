#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
VENV_PYTHON="${VENV_PYTHON:-/Volumes/半岛铁盒/实验室/.venv/bin/python}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-/Volumes/半岛铁盒/实验室/runtime}"
CHROMA_PATH="${CHROMA_PATH:-/tmp/algomentor-deploy-chroma}"

export PYTHONPATH="${PYTHONPATH_RUNTIME}${PYTHONPATH:+:$PYTHONPATH}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-tfidf}"
export CHROMA_PATH
export RAG_MIN_SCORE="${RAG_MIN_SCORE:-0.2}"

cd "$DEPLOY_DIR"
"$VENV_PYTHON" scripts/evaluate_evidence_rag.py
"$VENV_PYTHON" scripts/evaluate_platform.py
"$VENV_PYTHON" manage.py evaluate_workbench --username "${DEMO_USERNAME:-demo_student}"

echo "评测结果："
echo "  $DEPLOY_DIR/tests/evaluation/evidence_rag_results.json"
echo "  $DEPLOY_DIR/tests/evaluation/platform_results.json"
echo "  $DEPLOY_DIR/tests/evaluation/workbench_results.json"
