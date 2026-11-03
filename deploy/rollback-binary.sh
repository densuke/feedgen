#!/usr/bin/env bash
# 直前の版 (.prev) に戻す (docs/specs/release.md 4 章)。恒久的な手段。
set -u -o pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib.sh
. "$HERE/lib.sh"

[ -f "$INSTALL_DIR/feedgen-server.prev" ] || die "戻す先 (feedgen-server.prev) がありません"
restore_prev || die "戻せませんでした"
log "直前の版に戻しました (版: $(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo 不明))。再起動します"
restart_service || die "再起動に失敗しました"
wait_healthy || die "戻したあとも /health が通りません"
log "起動を確認しました"
