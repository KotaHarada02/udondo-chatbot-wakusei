# うどんど Chatbot 見本の無料版

惑星のウドンドの案内役ウドンドが、店の使い方を答えるチャットの見本である。クライアントのオーナー様に見せるために作った。本番は別のリポジトリ `udondo-avatar-bot` の設計で GCP に作る。

## 構成

| 部分 | 中身 |
|---|---|
| `frontend/` | Next.js。漫画のコマの見た目の客の画面 |
| `backend/` | FastAPI。`/api/v1/t/{tenant_id}/sessions`、`/chat`、`/feedback` を持つ。形は本番の API 仕様と同じ |
| `backend/tenants/udondo/` | 店の設定。ペルソナ、緊急時の定型文、画面の文言、テーマ |
| `supabase/migrations/` | Supabase に流す SQL |

LLM は Gemini API を使う。鍵がないときは偽の LLM で動くので、画面の確認だけなら鍵は要らない。

## 無料版の注意

Gemini API の無料枠では、送った内容が Google の製品改善に使われ、人が読むこともある。お店の人が試す見本として使い、実際の客の案内には使わない。

## 手元で動かす

```bash
cp .env.example .env.local
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn src.main:app --port 8000
```

別の端末で画面を起動する。

```bash
cd frontend
npm install
npx next dev
```

http://localhost:3000 を開く。画面の `/api/v1` への通信は手元の FastAPI に転送される。バックエンドの番号を変えたときは `BACKEND_URL` で指定する。

## Supabase の準備

1. Supabase の SQL エディタで `supabase/migrations/001_bot_tables.sql` を流す
2. 知識の修正を当てるなら、店に確かめてから `002_knowledge_fixes.sql` を流す
3. `.env.local` に `NEXT_PUBLIC_SUPABASE_URL` とサービスロールの鍵 `SUPABASE_SERVICE_ROLE_KEY` を入れる

サービスロールの鍵はサーバーだけが使う。画面のコードには渡さない。

## テスト

```bash
cd backend
.venv/bin/python -m pytest
```

外部の API は呼ばない。
