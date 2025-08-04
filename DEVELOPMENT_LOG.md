# feedgenプロジェクト開発記録

## プロジェクト概要
URL-to-RSS feed generation tool の完全実装（2025-08-04完了）
- Python + uv環境、TDD手法でのライブラリファースト開発
- 既存フィード検出・代理取得機能を含む高機能RSSフィード生成ツール

## 完了した主要機能

### 1. コアライブラリ（feedgen.core）
- **FeedGenerator**: メインの生成クラス
- **FeedDetector**: 既存フィード検出・代理取得（linkタグ+一般パス検出）
- **HTMLParser**: 多戦略HTML解析（見出し/カード/コンテンツブロック戦略）
- **Models**: RSSFeed, RSSItem pydanticモデル
- **Exceptions**: FeedGenerationError, ParseError

### 2. CLI版（feedgen.cli）
- 基本オプション: --config, --output, --max-items, --user-agent
- フィード検出: --use-feed（代理取得）, --feed-first（優先検出）
- ConfigManager: YAML設定ファイル対応

### 3. テスト・品質管理
- 51テスト（TDD実践）、全テスト通過
- Ruff品質チェック通過（352個の問題を自動修正済み）
- 型ヒント完備、PEP8準拠

## 技術的特徴

### 多戦略HTML解析
TailwindCSS等モダンサイト対応のカード要素解析
- 見出しタグ戦略（h1〜h6内のリンク）
- カード要素戦略（TailwindCSS等対応）
- コンテンツブロック戦略（フォールバック）

### 既存フィード検出
HTML linkタグ + 一般パス(/feed, /rss等)チェック
- RSS 2.0, Atom, JSON Feed対応
- 代理取得機能

### 実用性
- 重複排除: タイトルベースでの記事重複除去
- 実サイト動作確認: teckura.com/jobs等で検証済み

## 完了コミット履歴
```
108d0c5 [style] Ruffによるコード品質改善
4dd72b8 [feat] 既存フィード検出・代理取得機能の実装  
3e7a793 [feat] HTML解析ロジックの大幅改善
8e171b0 initial import
```

## ドキュメント状況
- **spec.md**: EARS表記法による完全仕様（既存フィード検出機能追加済み）
- **README.md**: 使用方法とインストール手順（フィード検出オプション記載済み）
- **task.md**: 開発要件（TDD、ライブラリファースト等）

## 使用ライブラリ
- **実行**: requests, beautifulsoup4, feedgenerator, pydantic, click, pyyaml
- **開発**: pytest, ruff（品質管理）

## 継続作業時の注意
- Web API版は未実装（spec.mdで将来実装として記載済み）
- 全機能完成、高品質、本格運用可能な状態
- mainブランチでの開発完了、ワークツリー利用可能

## 使用例
```bash
# 既存フィード代理取得（推奨）
feedgen --use-feed https://example.com

# フィード検出優先
feedgen --feed-first https://example.com

# HTML解析のみ
feedgen https://example.com
```