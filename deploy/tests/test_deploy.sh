#!/usr/bin/env bash
# deploy スクリプトのテスト (docs/specs/release.md R-3, R-5, R-6, 4 章)。
# 実ネットワークと実 systemd は使わない。127.0.0.1 の偽リリースサーバーと偽の systemctl を使う。
# 実行: bash deploy/tests/test_deploy.sh
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
DEPLOY=$(dirname "$HERE")
FAILED_CASES=()
TOTAL=0

sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi
}

# ---- 道具 ----------------------------------------------------------------

new_case() {
  T=$(mktemp -d)
  R=$T/release
  I=$T/install
  S=$T/bin
  mkdir -p "$R/download" "$I" "$S" "$T/tmp"
  : >"$T/calls.log"
  : >"$T/fails"
  # 偽の systemctl: restart のたびに記録し、インストール済みの本体が BROKEN を含めば不健康にする。
  cat >"$S/fake-systemctl" <<EOF
#!/bin/sh
echo "\$*" >> "$T/calls.log"
if [ "\$1" = restart ]; then
  if grep -q BROKEN "$I/feedgen-server" 2>/dev/null; then rm -f "$R/healthy"; else touch "$R/healthy"; fi
fi
EOF
  chmod +x "$S/fake-systemctl"
  python3 "$HERE/fake_release.py" "$R" &
  SERVER_PID=$!
  for _ in $(seq 50); do
    [ -s "$R/port" ] && break
    sleep 0.1
  done
  PORT=$(cat "$R/port")
}

end_case() {
  kill "$SERVER_PID" 2>/dev/null
  wait "$SERVER_PID" 2>/dev/null
  rm -rf "$T"
}

# 条件を確かめる。失敗したら、ケースの失敗として記録する。
ok() {
  local description=$1
  shift
  if ! "$@"; then echo "  NG: $description" | tee -a "$T/fails"; fi
}

has() { grep -q -- "$2" "$1" 2>/dev/null; }
lacks() { ! grep -q -- "$2" "$1" 2>/dev/null; }
equals() { [ "$1" = "$2" ]; }
missing() { [ ! -e "$1" ]; }
restarts() { grep -c '^restart' "$T/calls.log"; }

# 現行の版を、インストール済みにする。
install_current() {
  local v=$1
  printf '#!/bin/sh\n# marker %s\n' "$v" >"$I/feedgen-server"
  printf '#!/bin/sh\n# marker %s cli\n' "$v" >"$I/feedgen"
  chmod +x "$I/feedgen-server" "$I/feedgen"
  echo "$v" >"$I/VERSION"
  touch "$R/healthy"
}

# 偽のリリースを作る。variant: ok / broken / badsum / extra / missing / traversal / absolute
make_release() {
  local v=$1 variant=${2:-ok}
  local d=$T/stage-$v name=feedgen-x86_64-unknown-linux-musl-$v.tar.gz
  local dir=$R/download/v$v
  rm -rf "$d"
  mkdir -p "$d" "$dir"
  local mark="# marker $v"
  [ "$variant" = broken ] && mark="$mark BROKEN"
  printf '#!/bin/sh\n%s\n' "$mark" >"$d/feedgen-server"
  printf '#!/bin/sh\n# marker %s cli\n' "$v" >"$d/feedgen"
  chmod +x "$d/feedgen-server" "$d/feedgen"
  case $variant in
    extra)
      echo x >"$d/extra.txt"
      tar -czf "$dir/$name" -C "$d" feedgen-server feedgen extra.txt
      ;;
    missing)
      tar -czf "$dir/$name" -C "$d" feedgen-server
      ;;
    traversal | absolute)
      python3 - "$dir/$name" "$d" "$variant" <<'PY'
import io
import sys
import tarfile

out, stage, variant = sys.argv[1:4]
with tarfile.open(out, "w:gz") as archive:
    archive.add(f"{stage}/feedgen-server", arcname="feedgen-server")
    archive.add(f"{stage}/feedgen", arcname="feedgen")
    info = tarfile.TarInfo("../evil_out" if variant == "traversal" else "/tmp/feedgen_abs_evil_out")
    payload = b"evil"
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))
PY
      ;;
    *)
      tar -czf "$dir/$name" -C "$d" feedgen-server feedgen
      ;;
  esac
  if [ "$variant" = badsum ]; then
    printf '%064d  %s\n' 0 "$name" >"$dir/$name.sha256"
  else
    (cd "$dir" && sha "$name" >"$name.sha256")
  fi
  echo "$v" >"$R/LATEST"
}

run_script() { # $1=スクリプト名。標準出力と標準エラーは out.log、終了コードは RC。
  INSTALL_DIR=$I RELEASE_BASE_URL="http://127.0.0.1:$PORT" SYSTEMCTL="$S/fake-systemctl" \
    HEALTH_URL="http://127.0.0.1:$PORT/health" HEALTH_TIMEOUT=2 TMPDIR="$T/tmp" \
    bash "$DEPLOY/$1" >"$T/out.log" 2>&1
  RC=$?
}

unchanged() { # $1=版。本体、CLI、VERSION が、その版のまま。
  has "$I/feedgen-server" "marker $1\$" && has "$I/feedgen" "marker $1 cli" && equals "$(cat "$I/VERSION" 2>/dev/null)" "$1"
}

only_expected_files() {
  local f
  for f in "$I"/* "$I"/.[!.]*; do
    [ -e "$f" ] || continue
    case $(basename "$f") in
      feedgen-server | feedgen | VERSION | feedgen-server.prev | feedgen.prev | VERSION.prev) ;;
      *) echo "  想定外のファイル: $f"; return 1 ;;
    esac
  done
}

run_case() {
  TOTAL=$((TOTAL + 1))
  echo "== $1"
  new_case
  "$1"
  if [ -s "$T/fails" ]; then
    FAILED_CASES+=("$1")
    echo "  --- out.log"
    sed 's/^/  | /' "$T/out.log" 2>/dev/null
  fi
  end_case
}

# ---- update.sh (R-5, R-6) -----------------------------------------------

t_same_version_does_nothing() {
  install_current 0.1.0
  make_release 0.1.0
  run_script update.sh
  ok "終了コード 0" equals "$RC" 0
  ok "再起動しない" equals "$(restarts)" 0
  ok "版が変わらない" unchanged 0.1.0
  ok ".prev を作らない" missing "$I/feedgen-server.prev"
}

t_upgrade_replaces_and_keeps_prev() {
  install_current 0.1.0
  make_release 0.1.1
  run_script update.sh
  ok "終了コード 0" equals "$RC" 0
  ok "新しい版に置き換わる" unchanged 0.1.1
  ok "旧本体が .prev にある" has "$I/feedgen-server.prev" "marker 0.1.0"
  ok "旧 CLI が .prev にある" has "$I/feedgen.prev" "marker 0.1.0 cli"
  ok "VERSION.prev が旧版" equals "$(cat "$I/VERSION.prev" 2>/dev/null)" 0.1.0
  ok "再起動は 1 回" equals "$(restarts)" 1
  ok "再起動の対象" has "$T/calls.log" "restart feedgen-rs.service"
  ok "本体が実行可能" test -x "$I/feedgen-server"
  ok "CLI が実行可能" test -x "$I/feedgen"
  ok "余計なファイルが残らない" only_expected_files
}

t_second_upgrade_rotates_prev() {
  install_current 0.1.0
  make_release 0.1.1
  run_script update.sh
  make_release 0.1.2
  run_script update.sh
  ok "終了コード 0" equals "$RC" 0
  ok "最新に置き換わる" unchanged 0.1.2
  ok ".prev は直前の版" has "$I/feedgen-server.prev" "marker 0.1.1"
  ok "VERSION.prev は直前の版" equals "$(cat "$I/VERSION.prev" 2>/dev/null)" 0.1.1
}

t_first_install_without_version_file() {
  make_release 0.1.0
  run_script update.sh
  ok "終了コード 0" equals "$RC" 0
  ok "インストールされる" unchanged 0.1.0
  ok ".prev はない (戻す先がない)" missing "$I/feedgen-server.prev"
}

t_checksum_mismatch_changes_nothing() {
  install_current 0.1.0
  make_release 0.1.1 badsum
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "再起動しない" equals "$(restarts)" 0
  ok ".prev を作らない" missing "$I/feedgen-server.prev"
  ok "余計なファイルが残らない" only_expected_files
}

t_path_traversal_archive_is_rejected() {
  install_current 0.1.0
  make_release 0.1.1 traversal
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "展開先の外に書かれない" missing "$T/tmp/evil_out"
  ok "インストール先にも書かれない" missing "$I/evil_out"
  ok "再起動しない" equals "$(restarts)" 0
}

t_absolute_path_archive_is_rejected() {
  install_current 0.1.0
  make_release 0.1.1 absolute
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "絶対パスに書かれない" missing /tmp/feedgen_abs_evil_out
  ok "再起動しない" equals "$(restarts)" 0
}

t_archive_with_extra_file_is_rejected() {
  install_current 0.1.0
  make_release 0.1.1 extra
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "再起動しない" equals "$(restarts)" 0
}

t_archive_missing_a_binary_is_rejected() {
  install_current 0.1.0
  make_release 0.1.1 missing
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "再起動しない" equals "$(restarts)" 0
}

t_unhealthy_after_restart_rolls_back() {
  install_current 0.1.0
  make_release 0.1.1 broken
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "旧版に戻る" unchanged 0.1.0
  ok "BROKEN が残らない" lacks "$I/feedgen-server" BROKEN
  ok "再起動は 2 回 (新版、戻したあと)" equals "$(restarts)" 2
  ok "戻したあとは健康" test -e "$R/healthy"
  ok "戻したことをログに出す" has "$T/out.log" "ロールバック"
  ok "余計なファイルが残らない" only_expected_files
}

t_download_failure_changes_nothing() {
  install_current 0.1.0
  make_release 0.1.1
  rm "$R/download/v0.1.1/feedgen-x86_64-unknown-linux-musl-0.1.1.tar.gz"
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "再起動しない" equals "$(restarts)" 0
}

t_missing_checksum_file_changes_nothing() {
  install_current 0.1.0
  make_release 0.1.1
  rm "$R/download/v0.1.1/feedgen-x86_64-unknown-linux-musl-0.1.1.tar.gz.sha256"
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
}

t_latest_version_unavailable_changes_nothing() {
  install_current 0.1.0
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
  ok "再起動しない" equals "$(restarts)" 0
}

t_server_down_changes_nothing() {
  install_current 0.1.0
  make_release 0.1.1
  kill "$SERVER_PID"
  wait "$SERVER_PID" 2>/dev/null
  run_script update.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.0
}

# ---- rollback-binary.sh (4 章) ------------------------------------------

install_prev() {
  printf '#!/bin/sh\n# marker %s\n' "$1" >"$I/feedgen-server.prev"
  printf '#!/bin/sh\n# marker %s cli\n' "$1" >"$I/feedgen.prev"
  chmod +x "$I/feedgen-server.prev" "$I/feedgen.prev"
  echo "$1" >"$I/VERSION.prev"
}

t_rollback_binary_restores_prev() {
  install_current 0.1.1
  install_prev 0.1.0
  run_script rollback-binary.sh
  ok "終了コード 0" equals "$RC" 0
  ok "旧版に戻る" unchanged 0.1.0
  ok "再起動は 1 回" equals "$(restarts)" 1
  ok "本体が実行可能" test -x "$I/feedgen-server"
}

t_rollback_binary_without_prev_fails() {
  install_current 0.1.1
  run_script rollback-binary.sh
  ok "終了コード 1" equals "$RC" 1
  ok "版が変わらない" unchanged 0.1.1
  ok "再起動しない" equals "$(restarts)" 0
}

t_rollback_binary_reports_unhealthy() {
  install_current 0.1.1
  install_prev 0.1.0
  printf '#!/bin/sh\n# marker 0.1.0 BROKEN\n' >"$I/feedgen-server.prev"
  run_script rollback-binary.sh
  ok "戻したあとも不健康なら終了コード 1" equals "$RC" 1
}

# ---- next-patch.sh (R-3) --------------------------------------------------

t_next_patch_table() {
  local input expected out
  while read -r input expected; do
    out=$(bash "$DEPLOY/next-patch.sh" "$input" 2>/dev/null)
    ok "next-patch $input -> $expected" equals "$out" "$expected"
  done <<'EOF'
0.1.0 0.1.1
1.2.3 1.2.4
0.1.9 0.1.10
10.20.30 10.20.31
EOF
}

t_next_patch_rejects_invalid_versions() {
  local bad out
  for bad in "0.1" "a.b.c" "1.2.3-rc1" "" "1.2.3.4" "v1.2.3" "1.2.x"; do
    out=$(bash "$DEPLOY/next-patch.sh" "$bad" 2>/dev/null)
    ok "終了コード 1: '$bad'" test $? -ne 0
    ok "標準出力は空: '$bad'" equals "$out" ""
  done
}

# ---- 実行 -------------------------------------------------------------------

for case_name in $(declare -F | awk '{print $3}' | grep '^t_'); do
  run_case "$case_name"
done

echo
echo "ケース: $TOTAL、失敗: ${#FAILED_CASES[@]}"
if [ "${#FAILED_CASES[@]}" -gt 0 ]; then
  printf '失敗したケース: %s\n' "${FAILED_CASES[@]}"
  exit 1
fi
