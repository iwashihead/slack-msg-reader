# slack-msg-reader

Slackの「Bot/APIアプリ」を作らずに、自分が既にアクセス権を持っているチャンネル・DMのメッセージを、
手動でログイン済みのブラウザにアタッチして収集し、SQLiteに蓄積するツールです。
収集後はSQLite上のデータに対して分析コマンドを実行できます。

## 前提・注意事項 (必読)

- **認証はスクリプトでは行いません。** 事前にあなた自身の手でSlackにログインしてください。このツールはそのブラウザセッションに「後から乗る」だけです。
- SlackはWebクライアントのDOM構造を予告なく変更します。`src/slack_msg_reader/scraper/selectors.py` のセレクタは執筆時点のベストエフォートです。動かない場合はまず `inspect` コマンドで確認し、DevToolsで実際のDOMを見てセレクタを調整してください。
- 過度に高速なスクロール/連続実行はアカウントに負荷をかけたり不審な挙動として扱われる可能性があります。常識的な頻度（例:1日数回のバッチ実行）での利用を想定しています。

## セットアップ

```bash
cd ~/slack-msg-reader
python3.12 -m venv .venv   # 3.10+必須 (型ヒントに `X | None` 構文を使用)
source .venv/bin/activate
pip install -e ".[analysis]"
playwright install chromium   # ブラウザ自体は使わないが、Playwright本体の動作に必要
```

## 使い方

### 1. Chromeをリモートデバッグ有効で起動し、Slackに手動ログイン

```bash
# 既存のChromeプロセスが起動中なら一度終了してから実行してください
open -a "Google Chrome" --args --remote-debugging-port=9222
```

開いたChromeで `https://app.slack.com` にアクセスし、**手動で**普段通りログインしてください。
ログイン後、そのタブ (`app.slack.com/client/...`) を開いたままにしておきます。

### 2. セレクタが合っているか確認 (初回・Slack更新後は必須)

```bash
python -m slack_msg_reader.collect inspect
```

サイドバーのチャンネル一覧が出力されればOKです。0件の場合は `scraper/selectors.py` を
DevToolsの実際のDOMに合わせて調整してください。

### 3. DB初期化 & 収集

```bash
python -m slack_msg_reader.collect init      # 初回のみ: data/slack_archive.db を作成
python -m slack_msg_reader.collect collect    # 全チャンネル/DMを収集 (2回目以降は差分収集)
```

オプション:
- `--kind channel|dm|all` : 収集対象を絞り込み
- `--name-contains <文字列>` : チャンネル名で絞り込み
- `--full-history` : 差分ではなく全履歴を再取得

2回目以降の `collect` は、各チャンネルで前回保存済みの最新メッセージ (`ts`) より新しい分だけを取得します。

### 4. 分析

```bash
python -m slack_msg_reader.analysis.cli channels     # チャンネル別メッセージ数
python -m slack_msg_reader.analysis.cli users --channel general
python -m slack_msg_reader.analysis.cli hourly        # 時間帯別の投稿量
python -m slack_msg_reader.analysis.cli weekday       # 曜日別の投稿量
python -m slack_msg_reader.analysis.cli threads       # リプライ数の多いスレッド
python -m slack_msg_reader.analysis.cli reactions     # よく使われるリアクション
python -m slack_msg_reader.analysis.cli words         # 簡易ワード頻度 (日本語は簡易分割のみ)
python -m slack_msg_reader.analysis.cli search "キーワード"
```

`src/slack_msg_reader/analysis/queries.py` の各関数はpandas DataFrameを返すので、
Jupyter等から直接importして自由に集計・可視化を組み立てることもできます。

## 既知の制約 (MVP)

- スレッド返信の本文までは取得しません（親メッセージの `reply_count` のみ）。
- ユーザーはSlackのユーザーIDではなく、表示名を正規化したキーで管理しています（表示名変更で別ユーザー扱いになります）。
- 単語頻度分析は簡易的な空白/記号区切りで、日本語の形態素解析はしていません（本格的にやるなら janome/MeCab等を追加してください）。
- パブリック/プライベートチャンネルはサイドバーのセクション見出しで大まかに判定しており、厳密な区別はしていません（`kind` は `channel` にまとめています）。

## ディレクトリ構成

```
src/slack_msg_reader/
  config.py            設定値 (DBパス、CDP接続先、スクロール設定)
  collect.py            収集用CLIエントリポイント
  util.py                共通ユーティリティ
  db/
    models.py            SQLAlchemyモデル (Channel/User/Message/Reaction)
    database.py          エンジン/セッション管理
    repository.py        upsert/insertヘルパー
  scraper/
    browser.py            CDP経由でSlackタブにアタッチ
    selectors.py          DOMセレクタ定義 (Slack更新時はここを直す)
    channel_list.py       サイドバーからチャンネル一覧を取得
    parser.py              メッセージDOMのパース
    message_scraper.py    スクロール制御・差分収集ロジック
  analysis/
    queries.py            分析用クエリ (pandas DataFrame)
    cli.py                  分析用CLI
```
