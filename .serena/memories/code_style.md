## コーディング規約
- すべての公開関数/メソッドに型ヒントと日本語docstringを付与、PEP 8準拠。
- 例外や設定値は専用モジュール(`exceptions.py`, `config.py`)に集約し、責務分離を徹底。
- データモデルはPydantic(BaseModel)で定義し、時刻は`datetime`、Union型は`|`記法で記述。
- TDDを前提にpytestでテストを先行作成、機能追加時は対応テストも必須。
- Ruffで静的解析と自動フォーマット(必要に応じて)を実行、Lint警告ゼロを維持。