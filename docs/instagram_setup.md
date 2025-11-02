# Instagram認証セットアップガイド

feedgenでInstagramのフル機能版を使用するための認証設定手順です。

## 概要

Instagramフル機能版では以下が可能になります:
- 投稿の詳細情報取得(いいね数、コメント数など)
- 複数投稿の効率的な取得
- 高精度な投稿データ

認証方法は2種類あります:
1. **セッションファイル方式**(推奨): 一度認証すれば再利用可能
2. **パスワード方式**: 毎回ログインが必要

## 前提条件

- Instagramアカウントを持っていること
- Python環境が構築済みであること

## インストール

instaloaderライブラリをインストールします。

```bash
# uvを使用する場合
uv add instaloader

# pipを使用する場合
pip install instaloader
```

または、オプショナル依存として一括インストール:

```bash
uv sync --extra instagram
```

## 認証方法1: セッションファイル方式(推奨)

### 1-1. セッションファイルの作成

以下のコマンドでInstagramにログインし、セッションを保存します:

```bash
instaloader --login=あなたのユーザー名
```

パスワードを入力すると、セッションファイルが作成されます:
- `~/.config/instaloader/session-あなたのユーザー名`

### 1-2. config.yamlの設定

プロジェクトルートの`config.yaml`に以下を追加:

```yaml
instagram:
  use_full_client: true                    # フル機能版を有効化
  username: "あなたのユーザー名"
  session_file: "~/.config/instaloader/session-あなたのユーザー名"
  max_posts: 20                             # 取得する最大投稿数
```

### 1-3. 動作確認

```bash
feedgen https://www.instagram.com/ユーザー名/
```

正常に動作すれば、投稿の詳細情報を含むRSSフィードが生成されます。

## 認証方法2: パスワード方式

セッションファイルを使わず、毎回パスワードで認証する方法です。

### 2-1. config.yamlの設定

```yaml
instagram:
  use_full_client: true
  username: "あなたのユーザー名"
  max_posts: 20
  # session_fileは指定しない
```

### 2-2. プログラムでの認証

Pythonコードから使用する場合:

```python
from feedgen.core.instagram_client import InstagramFullClient

client = InstagramFullClient(username="あなたのユーザー名")
client.login(password="あなたのパスワード")

# セッションを保存する場合
client.session_file = "~/.config/instaloader/session-あなたのユーザー名"
client.login(password="あなたのパスワード")  # 自動的にセッションが保存される
```

**注意**: パスワードをコード内に直接書くのはセキュリティリスクがあります。環境変数や設定ファイルを使用してください。

## 環境変数による設定

環境変数でも認証情報を指定できます:

```bash
export INSTAGRAM_USERNAME="あなたのユーザー名"
export INSTAGRAM_SESSION_FILE="~/.config/instaloader/session-あなたのユーザー名"
```

環境変数は`config.yaml`よりも優先されます。

## セッションファイルの更新

セッションが期限切れになった場合は、再度ログインしてセッションを更新します:

```bash
instaloader --login=あなたのユーザー名
```

## トラブルシューティング

### エラー: "instaloader がインストールされていません"

**原因**: instaloaderライブラリがインストールされていない

**解決策**:
```bash
uv add instaloader
# または
pip install instaloader
```

### エラー: "ログインエラー"

**原因**:
- セッションファイルが期限切れ
- ユーザー名またはパスワードが間違っている
- Instagram側でログインがブロックされている

**解決策**:
1. セッションファイルを再作成
2. ユーザー名・パスワードを確認
3. ブラウザからInstagramにログインし、不審なアクティビティを承認

### エラー: "プロフィール投稿取得エラー"

**原因**:
- 非公開アカウントへのアクセス
- ネットワークエラー
- レート制限

**解決策**:
1. 公開アカウントか確認
2. ネットワーク接続を確認
3. しばらく待ってから再試行

## セキュリティ上の注意

### セッションファイルの保護

セッションファイルには認証トークンが含まれるため、適切に保護してください:

```bash
# パーミッションを制限
chmod 600 ~/.config/instaloader/session-*
```

### gitignoreへの追加

セッションファイルやパスワードをGitにコミットしないように:

```gitignore
# .gitignore
config.yaml
session-*
*.session
```

### 2段階認証(2FA)

Instagramで2段階認証を有効にしている場合:

1. `instaloader --login`コマンド実行時に2FAコードを入力
2. セッションファイルが作成されれば、以降は2FAコード不要

## 制限事項

### Instagramの利用規約

- 過度なリクエストは避けてください
- `max_posts`の値は適切に設定してください(推奨: 20-50)
- レート制限に注意してください

### プライベートアカウント

- 非公開アカウントの投稿は、フォローしている場合のみ取得可能
- 自分のアカウントでログインする必要があります

## 参考リンク

- [instaloader公式ドキュメント](https://instaloader.github.io/)
- [Instagram利用規約](https://help.instagram.com/581066165581870)
- [feedgen README](../README.md)
