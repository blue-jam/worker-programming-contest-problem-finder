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

---

## 🚀 使い方

### モードA: 自動問題選定モード（推奨 🌟）

問題を自分で探す必要はありません！**AtCoder 茶色〜赤色の実力差のあるチーム戦**を想定し、簡単な問題から難しい問題まで5段階の難易度（Tier 1〜Tier 5）でCodeChefから自動取得し、参加者が誰もACしていない `SAFE` な問題を自動探索・選定します（問題プールが不足した場合はKattisからも自動補充可能）。

```bash
# 基本実行: 各難易度Tierから1問ずつ（計5問）全員未ACの問題を自動選定
uv run python check_conflicts.py --auto

# 各Tierから2問ずつ（計10問）選定し、Kattisの補充も許可する場合
uv run python check_conflicts.py --auto --count-per-tier 2 --include-kattis
```

選定された安全な問題セットは自動的に `problems.json` に保存され、`report.md` に難易度別のマトリクスが出力されます。

#### 💡 問題候補だけを素早く自動生成したい場合
衝突チェックを行わず、まずバランスの取れた候補問題セットを生成したい場合は `find_problems.py` を使用できます：
```bash
uv run python find_problems.py --count-per-tier 1 -o problems.json
```

---

### モードB: 手動問題リスト指定モード（従来仕様）

#### 1. 入力ファイルの準備

##### A. 参加者リスト (`participants.txt`)
1行に1つの AtCoder ID を記載します（`#` で始まる行はコメント）。
```text
tourist
chokudai
steve_allen
```

##### B. 候補問題リスト (`problems.json`)
Kattis の Problem ID、および CodeChef の Problem Code を JSON で定義します。
```json
{
  "codechef": [
    "FLOW001",
    "TEST",
    "MAXHAMDIST"
  ],
  "kattis": [
    "bijele",
    "quadrant"
  ]
}
```

#### 2. スクリプトの実行
```bash
# 基本実行（uv を使用）
uv run python check_conflicts.py --problems problems.json
```

---

### 3. 難易度バケット定義（AtCoder 茶色 〜 赤色）

| 階層 (Tier) | 想定レベル (AtCoder) | CodeChef レーティング | Kattis 難易度 | 特徴・用途 |
| :--- | :--- | :---: | :---: | :--- |
| **Tier 1 (Easy)** | 茶色 (400 - 799) 相当 | 1000 - 1399 | 1.8 - 2.8 | 基本実装・全探索・初級アルゴリズム |
| **Tier 2 (Medium-Low)** | 緑色 (800 - 1199) 相当 | 1400 - 1699 | 2.9 - 4.2 | 基礎DP、グラフ探索(BFS/DFS)、素数・数論 |
| **Tier 3 (Medium)** | 水色 (1200 - 1599) 相当 | 1700 - 2099 | 4.3 - 5.6 | セグ木等のデータ構造、二分探索、最短経路 |
| **Tier 4 (Hard)** | 青・黄色 (1600 - 2399) 相当 | 2100 - 2499 | 5.7 - 7.0 | 発展的DP、ゲーム木、フロー、確率・期待値 |
| **Tier 5 (Very Hard)** | 橙・赤色 (2400 - 2800+) 相当 | 2500 - 3200+ | 7.1 - 9.0 | 難問・高度アルゴリズム（チームのエース枠） |

---

### 4. 主なコマンドラインオプション

| オプション | デフォルト値 | 説明 |
| :--- | :--- | :--- |
| `--auto` | `False` | 自動問題選定モードを有効化（5段階難易度から未AC問題を自動選出） |
| `--count-per-tier` | `1` | 自動モード時、各難易度階層から選定する問題数（デフォルト1＝計5問） |
| `--include-kattis` | `False` | 自動モード時、CodeChefに加えてKattisからの補充を有効化 |
| `--save-problems` | `problems.json` | 自動モード時、選定された問題セットを保存するパス |
| `-p`, `--participants` | `participants.txt` | 参加者リストファイルのパス |
| `-q`, `--problems` | `problems.json` | 候補問題JSONファイルのパス（手動モード用） |
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
