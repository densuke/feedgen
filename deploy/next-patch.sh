#!/usr/bin/env bash
# 版 (X.Y.Z) の patch を 1 つ上げて表示する (docs/specs/release.md R-3)。形式が違えば、何も出さず終了コード 1。
set -u

if [[ ${1:-} =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  # 10# は、先頭の 0 を 8 進数と解釈させないため。
  printf '%s.%s.%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$((10#${BASH_REMATCH[3]} + 1))"
else
  echo "エラー: 版の形式が X.Y.Z ではありません: ${1:-}" >&2
  exit 1
fi
