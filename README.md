# claude-code-handover

Claude Code のコンパクション時に HANDOVER ドキュメントを自動生成するフックシステム。

[English](README.en.md)

## これは何？

Claude Code はコンテキストが溢れると会話を**コンパクション**（圧縮）します。現在の状態やユーザー発言はよく保持されますが、以下の情報は失われがちです：

- **判断の理由** — なぜ A ではなく B を選んだか、その論理展開
- **失敗した試行** — 何を試して、なぜダメだったか
- **具体例** — 実際のコードスニペット、コマンド、ファイルパス
- **ユーザーの明示的指示** — ポリシー決定や方針

**claude-code-handover** はコンパクションが落とす情報を自動で補完し、復帰後のエージェントが完全なコンテキストを取り戻せるようにします。

HANDOVER が追加するコンテキストは約4Kトークン（コンテキストウィンドウの2%）。作業領域を圧迫せずに、コンパクションで失われた判断理由・具体例・ユーザー指示を復元します。

## 仕組み

```
コンパクション発生
  → SessionStart(compact) hook 発火
  → バックグラウンドで jsonl から会話差分を抽出
  → claude -p --model sonnet でトランスクリプトを分析
  → HANDOVER-{session_id}.md を書き出し

次のユーザープロンプト
  → UserPromptSubmit hook がマーカーを検知
  → エージェントのコンテキストにファイルパスを注入
  → エージェントが HANDOVER を読み込む
```

### 2パスアーキテクチャ

同一セッションで2回目以降のコンパクションが発生した場合：

- **Pass 1**: 新しい会話差分から HANDOVER フラグメントを抽出
- **Pass 2**: 既存 HANDOVER + 新フラグメントをマージ（精製済み同士の統合）

生のトランスクリプトと精製済みコンテンツを混ぜないことで品質を保ちます。

### ステータス表示

ステータスバーに生成状況がリアルタイムで表示されます。

```
📝HANDOVER extracting        ← 抽出中
📝HANDOVER extracting (1/2)  ← 抽出中（マージ予定あり）
📝HANDOVER merging (2/2)     ← マージ中
📝HANDOVER ready             ← 完了（60秒後に自動消去）
```

## インストール

### 1. フックスクリプトをコピー

`hooks/` を `~/.claude/hooks/` にコピーします：

```bash
mkdir -p ~/.claude/hooks
cp hooks/* ~/.claude/hooks/
```

Windows:
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\hooks"
Copy-Item hooks\* "$env:USERPROFILE\.claude\hooks\"
```

### 2. フック設定を追加

`~/.claude/settings.json` に以下を追加します。ファイルがなければ新規作成してください。

既に `hooks` セクションがある場合はマージしてください：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "python -X utf8 ~/.claude/hooks/handover_generate.py"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -X utf8 ~/.claude/hooks/handover_inject.py"
          }
        ]
      }
    ]
  }
}
```

**Windows**: `~/.claude/hooks/` をフルパスに置き換えてください：
```json
"command": "python -X utf8 C:\\Users\\YourName\\.claude\\hooks\\handover_generate.py"
```

### 3. Python の確認

Python 3.10+ が必要です。追加パッケージは不要（標準ライブラリのみ使用）。

```bash
python --version
```

## ファイル構成

| ファイル | フック | 役割 |
|---------|--------|------|
| `handover_generate.py` | SessionStart (compact) | コンパクション後にバックグラウンドワーカーを起動 |
| `handover_worker.py` | —（バックグラウンド） | jsonl 解析 → sonnet 呼び出し → HANDOVER 生成 |
| `handover_inject.py` | UserPromptSubmit | マーカー検知 → ファイルパスをエージェントに注入 |

## 出力先

HANDOVER ファイルはセッションの jsonl と同じディレクトリに保存されます：

```
~/.claude/projects/{project-path}/HANDOVER-{session_id}.md
```


## 要件

- Claude Code CLI（hooks サポートあり）
- Python 3.10+
- `claude -p --model sonnet` が動作すること（有効な認証）

## コスト

生成はバックグラウンドで実行され、コンパクション時のみ sonnet を1〜2回呼び出します。通常のメッセージでは実行されません。

## ライセンス

MIT
