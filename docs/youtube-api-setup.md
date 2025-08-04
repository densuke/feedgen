# YouTube Data API v3 セットアップガイド

このガイドでは、feedgenでYouTube検索結果をRSS化するために必要なYouTube Data API v3のAPI Keyを取得する手順を説明します。

## 📋 前提条件

- Googleアカウントが必要
- クレジットカード登録は**不要**（無料枠内での利用）
- 1日の利用上限: 10,000クォータ（検索100回相当）

## 🔧 API Key取得手順

### ステップ1: Google Cloud Consoleにアクセス

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. Googleアカウントでログイン

### ステップ2: 新しいプロジェクトを作成

1. 画面右上の「プロジェクトを選択」をクリック
2. 「新しいプロジェクト」をクリック
3. プロジェクト名を入力（例: `feedgen-youtube`）
4. 組織は空白のままでOK
5. 「作成」をクリック

### ステップ3: YouTube Data API v3を有効化

1. 左側メニューから「APIとサービス」→「ライブラリ」を選択
2. 検索バーに「YouTube Data API v3」と入力
3. 「YouTube Data API v3」を選択
4. 「有効にする」をクリック

### ステップ4: API認証情報を作成

1. 「APIとサービス」→「認証情報」を選択
2. 「認証情報を作成」→「APIキー」をクリック
3. APIキーが生成されるので、**安全な場所にコピー**して保存

### ステップ5: APIキーを制限（推奨）

1. 生成されたAPIキーの横の「編集」アイコンをクリック
2. 「アプリケーションの制限」で適切な制限を設定:
   - **なし**（テスト用）
   - **IPアドレス**（本番用・推奨）
3. 「APIの制限」で「キーを制限」を選択
4. 「YouTube Data API v3」のみチェック
5. 「保存」をクリック

## ⚙️ feedgenでの設定方法

### 方法1: 設定ファイルで指定

`config.yaml`を作成して以下を記述:

```yaml
# フィード生成の基本設定
max_items: 20
cache_duration: 3600
user_agent: "feedgen/1.0"

# Web API設定（URL生成機能用） 
api_base_url: https://my-feedgen.example.com

# YouTube Data API v3設定
youtube_api_key: "YOUR_API_KEY_HERE"
```

### 方法2: 環境変数で指定

```bash
# Linux/macOS
export YOUTUBE_API_KEY="YOUR_API_KEY_HERE"

# Windows
set YOUTUBE_API_KEY=YOUR_API_KEY_HERE
```

## 🚀 使用例

API Key設定後、以下のようにYouTube検索結果をRSS化できます:

```bash
# コマンドライン使用
feedgen "https://www.youtube.com/results?search_query=AI+開発"

# Web API使用
curl "http://localhost:8000/feed?url=https%3A%2F%2Fwww.youtube.com%2Fresults%3Fsearch_query%3DAI%2B%E9%96%8B%E7%99%BA"
```

## 📊 クォータ管理

### クォータ使用量の確認

1. Google Cloud Consoleで該当プロジェクトを選択
2. 「APIとサービス」→「クォータ」を選択
3. 「YouTube Data API v3」でフィルタリング

### クォータ消費量

| 操作 | 消費クォータ |
|------|-------------|
| 検索リクエスト | 100単位 |
| 動画詳細取得 | 1単位 |
| チャンネル情報取得 | 1単位 |

### 個人利用での実用性

- **1日の検索回数**: 最大100回（10,000 ÷ 100）
- **RSSリーダー更新**: 1-2時間に1回でも十分余裕
- **複数検索クエリ**: 10個の検索を1日中更新しても問題なし

## ⚠️ 注意事項

### セキュリティ

- **APIキーは秘匿情報**として扱う
- GitHubなどの公開リポジトリにコミットしない
- 本番環境では必ずIP制限を設定する

### 制限事項

- 1日のクォータを超過すると追加料金が発生（$1/1000単位）
- 検索結果は最大50件まで
- 古い動画の情報は取得できない場合がある

### トラブルシューティング

**「APIキーが無効」エラー**:
- APIキーの制限設定を確認
- YouTube Data API v3が有効になっているか確認

**「クォータ超過」エラー**:
- Google Cloud Consoleでクォータ使用量を確認
- 翌日0時（太平洋時間）にリセット

## 🔗 参考リンク

- [YouTube Data API v3 公式ドキュメント](https://developers.google.com/youtube/v3)
- [Google Cloud Console](https://console.cloud.google.com/)
- [API使用量の監視](https://console.cloud.google.com/apis/dashboard)

---

この手順でAPI Keyを取得後、feedgenのYouTube検索機能をご利用いただけます。