# AI面接システム（AI RECOMEN）

FastAPI + SQLite + Claude API で構築したAI面接管理システムです。

## 機能

| 画面 | 機能 |
|---|---|
| ① 企業情報管理 | 企業の登録・編集・無効化 |
| ② 企業アカウント管理 | 企業担当者のアカウント管理 |
| ③ 求人情報管理 | 求人登録 + **AI面接内容の設定**（ペルソナ・質問・評価基準） |
| ④ 応募者管理 | 応募者登録・詳細・面接リンク発行 |
| ⑤ 面接履歴管理 | 面接会話ログ・AI評価スコア・推薦結果 |
| ⑥ プライバシーポリシー管理 | 面接同意画面に表示するポリシー管理 |

## ローカル起動

```bash
# 1. 依存関係インストール
pip install -r requirements.txt

# 2. 環境変数設定
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を設定

# 3. 起動
uvicorn main:app --reload --port 8000

# 4. ブラウザでアクセス
# 管理画面: http://localhost:8000/admin
# 初期ログイン: admin@example.com / Admin1234!
```

## Render へのデプロイ

1. GitHubにリポジトリをプッシュ
2. Render Dashboard → "New Web Service"
3. リポジトリを選択
4. `render.yaml` が自動検出される
5. 環境変数を設定:
   - `ANTHROPIC_API_KEY`: AnthropicのAPIキー
   - `ADMIN_PASSWORD`: 管理者パスワード（必ず変更）
   - `SECRET_KEY`: ランダムな文字列
6. Deploy

### Disk（永続ストレージ）設定
`render.yaml` に Disk 設定が含まれています（`/mnt/data` に10GB）。
面接履歴・アップロードファイルはすべてこのディスクに保存されます。

## AI面接の仕組み

```
管理者が求人に設定
  ├── AI面接官ペルソナ（システムプロンプト）
  ├── 挨拶メッセージ
  ├── 面接質問リスト（カテゴリ・重要度付き）
  └── 評価基準（評価項目・ウェイト）
         ↓
管理者が応募者に面接URLを発行
         ↓
応募者がURLにアクセス → プライバシーポリシー同意
         ↓
AI面接開始（Claude APIによるリアルタイム会話）
         ↓
面接完了後に自動評価
  ├── 総合スコア（0-100点）
  ├── AI推薦（採用推薦/要検討/不採用推薦）
  ├── 評価基準ごとのスコア
  ├── 強み・懸念点
  └── 総合サマリー
```

## ディレクトリ構成

```
ai_interview/
├── main.py              # FastAPI アプリ本体
├── models.py            # SQLAlchemy モデル
├── database.py          # DB設定
├── auth.py              # 認証ユーティリティ
├── requirements.txt
├── render.yaml          # Render デプロイ設定
├── routers/
│   ├── companies.py     # ① 企業管理
│   ├── accounts.py      # ② アカウント管理
│   ├── jobs.py          # ③ 求人・AI設定管理
│   ├── applicants.py    # ④ 応募者管理
│   ├── interviews.py    # ⑤ 面接履歴管理
│   ├── privacy.py       # ⑥ プライバシーポリシー管理
│   └── interview_session.py  # AI面接セッション処理
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── admin/           # 管理画面テンプレート
│   └── interview/       # 応募者向け面接画面
└── static/
    ├── css/style.css    # 管理画面CSS
    └── css/interview.css # 面接画面CSS
```
