#!/usr/bin/env bash
# e2 の feedgen-rs を、最新のタグ付きリリースに置き換える (docs/specs/release.md R-5, R-6)。
# 検証に失敗したら何も置き換えず、起動後の /health が通らなければ、直前の版に自動で戻す。
set -u -o pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib.sh
. "$HERE/lib.sh"

TARGET=x86_64-unknown-linux-musl

WORK=$(mktemp -d) || die "作業ディレクトリを作れません"
# trap から呼ばれる (shellcheck の版により、指摘が SC2317 か SC2329 になる)。
# shellcheck disable=SC2317,SC2329
cleanup() {
  rm -rf "$WORK"
  rm -f "$INSTALL_DIR"/.*.new
}
trap cleanup EXIT

# 1. 最新のタグ付きリリースの版。/latest は、最新の (プレリリースでない) リリースへ転送される。
latest=$(curl -fsS --max-time 30 -o /dev/null -w '%{redirect_url}' "$RELEASE_BASE_URL/latest") ||
  die "最新の版を取得できません"
version=${latest##*/tag/v}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "最新の版を解釈できません: $latest"

current=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || true)
if [ "$current" = "$version" ]; then
  log "最新です (版: $version)。何もしません"
  exit 0
fi
log "更新します: ${current:-なし} -> $version"

# 2. 取得とチェックサムの検証
name=feedgen-$TARGET-$version.tar.gz
base=$RELEASE_BASE_URL/download/v$version
curl -fsS --max-time 120 -o "$WORK/$name" "$base/$name" || die "アーカイブを取得できません"
curl -fsS --max-time 30 -o "$WORK/$name.sha256" "$base/$name.sha256" || die "チェックサムを取得できません"
expected=$(awk 'NR==1 {print $1}' "$WORK/$name.sha256")
actual=$(sha256_of "$WORK/$name")
[[ $expected =~ ^[0-9a-f]{64}$ && $expected == "$actual" ]] || die "チェックサムが一致しません"

# 3. 中身の検証。期待する 2 つのバイナリ (通常のファイル) だけを許す。`..` や絶対パスは、これで弾かれる。
entries=$(tar -tzf "$WORK/$name") || die "アーカイブを読めません"
[ "$(printf '%s\n' "$entries" | sort)" = "$(printf 'feedgen\nfeedgen-server')" ] ||
  die "アーカイブの中身が想定と違います"
if tar -tvzf "$WORK/$name" | cut -c1 | grep -qv '^-$'; then
  die "アーカイブに通常のファイル以外が含まれています"
fi
mkdir "$WORK/x" || die "展開先を作れません"
tar -xzf "$WORK/$name" -C "$WORK/x" || die "アーカイブを展開できません"

# 4. 置き換え。現行を .prev に退避してから、新しい版を入れる。
had_current=false
rollback_and_exit() {
  log "$1 ロールバックします"
  [ "$had_current" = true ] || die "戻す先がありません"
  restore_prev || die "ロールバックに失敗しました"
  restart_service || log "再起動に失敗しました。手動で確認してください"
  if wait_healthy; then
    log "ロールバックしました (版: ${current:-不明})"
  else
    log "ロールバック後も /health が通りません。手動で確認してください"
  fi
  exit 1
}

if [ -f "$INSTALL_DIR/feedgen-server" ]; then
  had_current=true
  install_file "$INSTALL_DIR/feedgen-server" "$INSTALL_DIR/feedgen-server.prev" 755 || die "退避に失敗しました"
  if [ -f "$INSTALL_DIR/feedgen" ]; then
    install_file "$INSTALL_DIR/feedgen" "$INSTALL_DIR/feedgen.prev" 755 || die "退避に失敗しました"
  fi
  if [ -f "$INSTALL_DIR/VERSION" ]; then
    install_file "$INSTALL_DIR/VERSION" "$INSTALL_DIR/VERSION.prev" 644 || die "退避に失敗しました"
  fi
fi

printf '%s\n' "$version" >"$WORK/VERSION"
if ! { install_file "$WORK/x/feedgen-server" "$INSTALL_DIR/feedgen-server" 755 &&
  install_file "$WORK/x/feedgen" "$INSTALL_DIR/feedgen" 755 &&
  install_file "$WORK/VERSION" "$INSTALL_DIR/VERSION" 644; }; then
  rollback_and_exit "置き換えに失敗しました。"
fi
log "置き換えました。再起動します"

# 5. 再起動と、起動の確認
if restart_service && wait_healthy; then
  log "起動を確認しました (版: $version)"
  exit 0
fi
rollback_and_exit "起動を確認できません。"
