# 企業プログラミングコンテスト 既AC・競合調査ツール (`worker-programming-contest-problem-finder`)

企業プログラミングコンテスト等の問題選定において、参加者リスト（AtCoder ID）をもとに、**Kattis** および **CodeChef** 上で「同名または類似アカウントが存在するか」「候補問題がすでにAC（正解）されていないか」を自動判定・突合するツールです。

---

## 🌟 主な特徴

1. **類似アカウント名（Fuzzy ID）探索エンジン**:
   - AtCoder ID から他サービスで使われがちな派生IDの候補セットを自動生成
   - 完全一致（大文字/小文字正規化）
   - 前後の記号付加・削除（例: `user`, `_user`, `user_`, `user-dev`）
   - 末尾の数字追加・削除・変動（例: `user1`, `user0`）
   - レーベンシュタイン距離 1〜2 以内のタイポ・文字入れ替え・欠落バリエーション
   - 類似度スコア（0.0〜1.0）の自動計算

2. **堅牢なスクレイピング & レート制限対策**:
   - 各サービスへの負荷やIP制限を避けるため、適切な `User-Agent` とジッター付き待機（1〜2秒）を標準搭載
   - 同一実行セッション内でのメモリキャッシュにより、重複リクエストを完全防止
   - **Kattis**: 404チェック、ユーザープロフィールのパースに加え、問題統計ページ（`/problems/{problem_id}/statistics`）からのソルバー逆引きクロスチェックを実装し、公開プロフィール制限時にも確実にACを検知
   - **CodeChef**: 404/リダイレクト検知、`problems-solved` セクションの静的パースに加え、`recent/user` 提出APIからAC（100点）済みの Problem Code を高精度抽出

3. **3段階の危険度判定**:
   - 🟢 `SAFE`: どの参加者（および類似ID）も解いていない（選定推奨）
   - 🟡 `SUSPICIOUS`: 類似IDが解いている（該当アカウント名・類似度・元IDを出力）
   - 🔴 `COLLISION`: 参加者本人（完全一致ID）がすでに解いている（選定非推奨・衝突）

4. **マルチフォーマット出力**:
   - ターミナル上のリッチなカラーサマリー表示（`rich`）
   - 機械可読な `result.json`
   - そのまま閲覧・共有可能な `report.md`

---

## 🛠️ 必要要件・インストール手順

本プロジェクトではパッケージ管理・実行ツールとして **`uv`** を使用します。

### 1. `uv` のインストール（未導入の場合）
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 仮想環境作成と依存ライブラリのインストール
```bash
# 仮想環境を作成して依存パッケージをインストール
uv venv
uv pip install -r requirements.txt

# またはプロジェクトとして同期
uv sync
```

---

## 🚀 使い方

### 1. 入力ファイルの準備

#### A. 参加者リスト (`participants.txt`)
1行に1つの AtCoder ID を記載します（`#` で始まる行はコメント）。
```text
tourist
chokudai
steve_allen
```

#### B. 候補問題リスト (`problems.json`)
Kattis の Problem ID、および CodeChef の Problem Code を JSON で定義します。
```json
{
  "kattis": [
    "bijele",
    "quadrant",
    "cold",
    "secret_prob_999"
  ],
  "codechef": [
    "FLOW001",
    "TEST",
    "MAXHAMDIST",
    "FLOW999_SAFE"
  ]
}
```

### 2. スクリプトの実行
```bash
# 基本実行（uv を使用）
uv run python check_conflicts.py

# オプション指定の例
uv run python check_conflicts.py \
  --participants participants.txt \
  --problems problems.json \
  --delay 1.0 \
  --max-candidates 15 \
  --output-json result.json \
  --output-report report.md
```

### 3. 主なコマンドラインオプション

| オプション | デフォルト値 | 説明 |
| :--- | :--- | :--- |
| `-p`, `--participants` | `participants.txt` | 参加者リストファイルのパス |
| `-q`, `--problems` | `problems.json` | 候補問題JSONファイルのパス |
| `-d`, `--delay` | `1.2` | リクエスト間の基準待機秒数（ジッターが自動加算されます） |
| `--max-candidates` | `25` | 参加者1人あたりに生成・探索する類似候補IDの最大数 |
| `--output-json` | `result.json` | 結果JSONの出力先 |
| `--output-report` | `report.md` | レポートMarkdownの出力先 |
| `--skip-kattis-solvers-check` | `False` | Kattis問題統計ページによるソルバー逆引きチェックをスキップ |
| `-v`, `--verbose` | `False` | 詳細なデバッグログを表示 |

---

## 🧪 テストの実行

```bash
uv run pytest
```
Fuzzy ID 生成エンジン、判定ロジック、パーサーモックのテストが実行されます。

---

## 📊 出力成果物

- **`report.md`**: Markdown 形式のマトリクス表と詳細サマリー
- **`result.json`**: 構造化された突合結果データ（CI/CD連携やシステム連携向け）
