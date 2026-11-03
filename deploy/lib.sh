#!/usr/bin/env bash
# update.sh と rollback-binary.sh の共通部分 (docs/specs/release.md)。source して使う。

INSTALL_DIR=${INSTALL_DIR:-$HOME/work/feedgen-rs}
RELEASE_BASE_URL=${RELEASE_BASE_URL:-https://github.com/densuke/feedgen/releases}
SYSTEMCTL=${SYSTEMCTL:-sudo systemctl}
HEALTH_URL=${HEALTH_URL:-http://127.0.0.1:8001/health}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-15}
SERVICE=feedgen-rs.service

log() { printf '%s\n' "$*"; }

die() {
  printf 'エラー: %s\n' "$*" >&2
  exit 1
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# 同じディレクトリの一時名にコピーしてから mv する (途中で止まっても、半端なファイルが残らない)。
# $1=元 $2=先 $3=モード
install_file() {
  local tmp
  tmp="$(dirname "$2")/.$(basename "$2").new"
  cp "$1" "$tmp" && chmod "$3" "$tmp" && mv -f "$tmp" "$2"
}

restart_service() {
  # SYSTEMCTL は "sudo systemctl" のように複数語になるので、引用符で囲まない。
  # shellcheck disable=SC2086
  $SYSTEMCTL restart "$SERVICE"
}

# 起動後、/health が 200 を返すまで、最大 HEALTH_TIMEOUT 秒待つ。
wait_healthy() {
  local i
  for ((i = 0; i < HEALTH_TIMEOUT; i++)); do
    if curl -fsS --max-time 2 -o /dev/null "$HEALTH_URL" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# .prev を、現行に戻す。本体、CLI、VERSION のうち、.prev があるものを戻す。
restore_prev() {
  install_file "$INSTALL_DIR/feedgen-server.prev" "$INSTALL_DIR/feedgen-server" 755 || return 1
  if [ -f "$INSTALL_DIR/feedgen.prev" ]; then
    install_file "$INSTALL_DIR/feedgen.prev" "$INSTALL_DIR/feedgen" 755 || return 1
  fi
  if [ -f "$INSTALL_DIR/VERSION.prev" ]; then
    install_file "$INSTALL_DIR/VERSION.prev" "$INSTALL_DIR/VERSION" 644 || return 1
  fi
}
