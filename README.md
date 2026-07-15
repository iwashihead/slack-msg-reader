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

### 1. 収集用Chromeを起動し、Slackに手動ログイン

`pip install -e .` すると `slack` コマンドが使えるようになります（venv を `activate` した状態で実行してください）。

```bash
slack chrome
```

普段使っているChromeとは別に、このツール専用の永続プロファイル
(`~/.slack-msg-reader/chrome-profile`) でChromeを起動します（普段のChromeウィンドウはそのままで大丈夫です）。
初回だけ、開いたウィンドウで `https://app.slack.com` に**手動で**普段通りログインしてください。
プロファイルは永続化されるので、2回目以降は基本的に再ログイン不要です。

このChromeプロセスはPCを再起動したりウィンドウを閉じたりすると終了します。`slack inspect` や
`slack collect` を実行して `ECONNREFUSED` になる場合は、まず `slack chrome` を実行してください。

### 2. セレクタが合っているか確認 (初回・Slack更新後は必須)

```bash
slack inspect
```

サイドバーのチャンネル一覧が出力されればOKです。0件の場合は `scraper/selectors.py` を
DevToolsの実際のDOMに合わせて調整してください。

サイドバーは仮想スクロール（表示範囲付近だけがDOMに存在する）なので、`inspect` は
「連続3回、件数もスクロール位置も変化しなくなるまで」自動でスクロールし続けます。
所属チャンネル数が数百件規模でも全件を検出できるよう作られていますが、実機での
大規模ワークスペース（200件超など）での網羅性はこちら側では検証できていないため、
検出件数が実際の所属数と食い違う場合は教えてください。

### 3. DB初期化 & 収集

```bash
slack init      # 初回のみ: data/slack_archive.db を作成
slack collect    # 全チャンネル/DMを収集 (2回目以降は差分収集)
```

オプション:
- `--kind channel|dm|all` : 収集対象を絞り込み
- `--name-contains <文字列>` : チャンネル名で絞り込み
- `--channel-id <ID>` : 特定チャンネルのみ収集（`slack inspect` で調べたIDを指定、複数回指定可）。
  指定すると `--kind`/`--name-contains` は無視されます
- `--full-history` : 差分ではなく全履歴を再取得
- `--since 2026-07-01` / `--until 2026-07-31` : 収集する期間を絞り込み（大きいチャンネルの
  収集に時間がかかりすぎる場合に）
- `--threads/--no-threads`（デフォルト: 有効）: スレッドの返信も個別に開いて収集するか。
  返信を追わない場合は `--no-threads` で高速化できます

2回目以降の `collect` は、各チャンネルで前回保存済みの最新メッセージ (`ts`) より新しい分だけを取得します。
`--since`/`--until` は「前回保存済みの位置」とは独立した追加の絞り込み条件で、初回の
`--full-history` 収集でも「直近30日分だけ」のように範囲を制限できます。

スレッド返信は、返信元メッセージがまだ画面に描画されている間にその場で開いて収集します
（チャンネル全体をスクロールし終えてから遡って開こうとすると、仮想スクロールで
DOMから消えてしまっている可能性があるため）。

### 4. 分析

```bash
slack analyze channels     # チャンネル別メッセージ数
slack analyze users --channel general
slack analyze hourly        # 時間帯別の投稿量
slack analyze weekday       # 曜日別の投稿量
slack analyze threads       # リプライ数の多いスレッド
slack analyze reactions     # よく使われるリアクション
slack analyze words         # 簡易ワード頻度 (日本語は簡易分割のみ)
slack analyze search "キーワード"
```

`src/slack_msg_reader/analysis/queries.py` の各関数はpandas DataFrameを返すので、
Jupyter等から直接importして自由に集計・可視化を組み立てることもできます。

### 5. AI分析用にエクスポート

外部LLM（Claude等）に読ませて分析させるためのMarkdownファイルを出力します。
チャンネルごとにまとめ、基本的には1ファイルに収めますが、`--max-chars` を超える場合は
`--max-files`（デフォルト10）を上限に自動で分割します（モデルの入力文字数制限に対応するため）。

```bash
slack export                              # 全件を1〜10ファイルに出力 (data/exports/)
slack export --channel general            # チャンネルで絞り込み
slack export --user haru                  # 送信者で絞り込み
slack export --since 2026-07-01 --until 2026-07-31   # 期間で絞り込み
slack export --max-chars 100000 --max-files 5         # 分割の閾値を調整
```

分割は必ずメッセージの区切り・チャンネルの区切りで行われ、1メッセージの途中で
ファイルが切れることはありません。1チャンネルの内容だけで `--max-chars` を超える場合は、
そのチャンネル内でメッセージ単位に分割し、続きのファイルにも同じ見出しを
`(continued)` 付きで繰り返します。

### 6. 特定の人を中心にしたレポート生成（週報などの分析用）

「今週〇〇さんがSlackで何をしていたか」のような分析をしたいとき向けの機能です。
`--user` で指定した人が**発言したチャンネル/DM**を洗い出し、その中の**全員の発言**
（指定した人の発言だけでなく、会話相手の発言も含む）を期間で絞り込んでMarkdown出力します。
片側の発言だけでは会話の文脈が分からないため、あえて相手側の発言も含めています。

同時に、AIチャットボットに投げるための分析用プロンプト（`report_prompt.txt`）も生成します。
プロンプトは「今回の期間中にやったこと」「新たに発生したタスク」「期限」
「良くなかったコミュニケーション」「返信漏れ・未対応の案件」の5観点で分析するよう
指示する内容になっています。

**このツール自体はAI APIを一切呼び出しません。** 出力された `report_conversations*.md` と
`report_prompt.txt` を、自分が使っているAIチャットボット（Claude等）に手動で渡してください。

```bash
slack report --user haru --this-week                  # 今週(月曜〜現在)のharuの会話を分析用に出力
slack report --user haru --since 2026-07-01 --until 2026-07-31
slack report --user haru --this-week --output-dir ./weekly_report
```

出力先はデフォルトで `data/reports/` です。分割の挙動（`--max-chars` / `--max-files`）は
`slack export` と同じロジックを共有しています。

### 7. GUIアプリ

CLIの代わりにデスクトップGUI（PySide6/Qt製、Mac/Windows両対応）からも操作できます。
「Chrome & Collect」「Export」「Report」「Analyze」の4タブで、これまでのCLIコマンドと
同じ機能をすべてカバーしています。Playwright/CDPを使う処理（Chrome起動・Inspect・Collect）は
バックグラウンドスレッドで実行され、ログはGUI内にリアルタイム表示されます。
Reportタブにはユーザー選択（既知のユーザー一覧から選択可）・「今週」ワンクリック指定・
生成したプロンプトのクリップボードコピーボタンがあります。
Chrome & Collectタブの「Inspect」欄はチャンネルごとにチェックボックスがあり、特定の
チャンネルだけにチェックを入れて「Collect」すればそれらだけを収集できます（Select all /
Select noneで一括切り替え）。何もチェックしなければ従来通りKind/Name containsの絞り込みが
使われます。「Collect」欄にはSince/Until（期間指定）と「スレッド返信も収集する」チェックボックスも
あります。

```bash
pip install -e ".[gui]"
slack-gui
# もしくは
python -m slack_msg_reader.gui.app
```

#### 配布用アプリ（.app / .exe）のビルド

```bash
pip install -e ".[build]"
pyinstaller packaging/SlackMsgReader.spec --distpath packaging/dist --workpath packaging/build
```

- **Mac**: `packaging/dist/SlackMsgReader.app` が生成されます。実際にビルドし、
  Chrome起動・Inspect・Collect・Export・Analyzeの全機能が実データに対して動作することを
  確認済みです。
- **Windows**: 同じ `.spec` ファイルでビルドできます（`BUNDLE`はmacOS専用ステップのため
  Windows実行時は自動的にスキップされます）。`.github/workflows/windows-gui-smoke-test.yml`
  により、GitHub Actionsの `windows-latest`（実機のWindows環境）上でビルド・起動・
  Chrome連携までを継続的に検証しています。

#### CIでのビルド済み配布物のダウンロード

GitHub Actionsの `.github/workflows/build-artifacts.yml` を手動実行（Actionsタブ →
「Build distributable artifacts」→ Run workflow）すると、以下がワークフローの
Artifacts として生成されます。バージョンタグ（`v*`）をpushした場合も自動実行されます。

- `SlackMsgReader-macOS`: `SlackMsgReader.dmg`（Applicationsフォルダへドラッグインストール可能）
- `SlackMsgReader-Windows`: `SlackMsgReaderSetup.exe`（Inno Setup製インストーラー）

Actionsの実行結果ページの「Artifacts」欄からダウンロードできます（GitHubの仕様上、
Artifactsは既定で90日間保持されます）。

パッケージ版（.app / .exe）実行時のデータ（SQLite DB等）は `~/.slack-msg-reader/data/` に
保存されます（ソースから `slack` CLIで動かす場合は従来通り `data/` プロジェクト直下）。
パッケージ版はアプリバンドル自身の場所に書き込もうとすると、マウントした `.dmg` から
直接起動した場合や権限次第で失敗するため、ホームディレクトリ配下に固定しています。

## セキュリティ

依存パッケージは [pip-audit](https://github.com/pypa/pip-audit) で監査しています（PyPI Advisory DB / OSV の
両方に対してクロスチェック）。`.github/workflows/security.yml` により、`main` へのpush・PR・
毎週月曜（新規CVEはコード変更なしでも発生するため）に自動実行されます。

手元で同じ監査を再現する場合:

```bash
pip install -e ".[build]"   # 実際に配布される依存関係一式（core + gui + build extras）
pip install pip-audit
pip-audit --local --desc -s pypi
pip-audit --local --desc -s osv
```

依存関係の宣言は `pyproject.toml` のみを正としています（過去にあった `requirements.txt` は
内容が古くなっていた＝GUI/ビルド用の依存が漏れていたため削除しました）。

## 既知の制約 (MVP)

- スレッド返信も収集します（`--no-threads` で無効化可）。返信は `thread_ts` に親メッセージの
  `ts` を持つ形でDBに保存され、`reply_count` は親メッセージ側にのみ記録されます。
- ユーザーはSlackのユーザーIDではなく、表示名を正規化したキーで管理しています（表示名変更で別ユーザー扱いになります）。
- 単語頻度分析は簡易的な空白/記号区切りで、日本語の形態素解析はしていません（本格的にやるなら janome/MeCab等を追加してください）。
- パブリック/プライベートチャンネルは区別せずどちらも `kind=channel` として扱っています（DM/group DMは `kind=dm`）。
- Slackは同じ送信者の連続投稿をグルーピングして送信者名を省略表示します。DOM上も省略された投稿には送信者情報が一切残らないため、直前に送信者名が確認できたメッセージから forward-fill（前方補完）しています。まれに、差分収集の境界（前回収集の最後のメッセージと今回の最初のメッセージ）でDB側の直前送信者を参照できないと `unknown` になることがあります。
- サイドバーのチャンネル列挙（`inspect`/`collect`）は、少人数の小規模ワークスペースで動作確認していますが、数百チャンネル規模の実ワークスペースでの網羅性はこちら側では検証できていません。検出数が実際の所属数と合わない場合はお知らせください。

## ディレクトリ構成

```
src/slack_msg_reader/
  config.py            設定値 (DBパス、CDP接続先、スクロール設定)
  cli.py                 統合CLIエントリポイント (`slack` コマンド本体、export含む)
  collect.py            収集コマンド群 (init/inspect/collect)
  export.py             AI分析用Markdownエクスポート (フィルタ・チャンネル単位分割)
  report.py              特定ユーザーの文脈込み会話出力 + AI分析プロンプト生成
  util.py                共通ユーティリティ
  db/
    models.py            SQLAlchemyモデル (Channel/User/Message/Reaction)
    database.py          エンジン/セッション管理
    repository.py        upsert/insertヘルパー
  scraper/
    browser.py            CDP経由でSlackタブにアタッチ
    chrome_launcher.py    収集用Chrome(専用プロファイル)の起動・待機
    selectors.py          DOMセレクタ定義 (Slack更新時はここを直す)
    channel_list.py       サイドバーからチャンネル一覧を取得
    parser.py              メッセージDOMのパース
    message_scraper.py    スクロール制御・差分収集ロジック
  analysis/
    queries.py            分析用クエリ (pandas DataFrame)
    cli.py                  分析用CLI
  gui/
    app.py                  GUIエントリポイント (`slack-gui`)
    main_window.py         3タブ構成のメインウィンドウ
    chrome_tab.py           Chrome起動・Inspect・Collectタブ
    export_tab.py           Exportタブ
    report_tab.py           Reportタブ
    analyze_tab.py          Analyzeタブ
    workers.py              Playwright呼び出し等をバックグラウンドスレッド化
    log_handler.py          logging→GUIログ表示のブリッジ
    models.py               QTableView用のpandas DataFrameモデル
packaging/
  run_gui.py              PyInstaller用エントリポイントスクリプト
  SlackMsgReader.spec     PyInstallerビルド設定
.github/workflows/
  security.yml            pip-auditによる依存パッケージ脆弱性チェック (push/PR/週次)
```
