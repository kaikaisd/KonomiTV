# 本フォクについて

このフォクは [本家 KonomiTV](https://github.com/tsukumijima/KonomiTV)と[ichigomoti](https://github.com/ichigomoti)をベースに、l3tnun様の[EPGStation](https://github.com/l3tnun/EPGStation)使用したのMirakurun録画ロジックをKononiTVに追加しました。

Telegram Bot を利用した録画完了通知機能を実装しました。録画完了時にサムネイル・番組情報・再生リンクを通知し、HTML テンプレートによるカスタマイズや設定のホットリロードにも対応しています。

ほとんどClaude Codeに作らせています(このREADME.mdも)、そのためバグも多くあります。インストールされる際はバックアップを取ることを強く推奨します。

なの、問題が発生しましたら、issueを呈してください。

作者の日本語レベルは有限ですので、できれば英語を説明してください。

何卒宜しくお願い致します。

## 追加機能の概要

### 1. Mirakurun バックエンドでの録画予約

EDCB を使わず、Mirakurun バックエンドのみで録画予約が行えるようになりました。

- **手動予約**: 番組表から番組を選択して録画予約を追加・編集・削除
- **予約一覧**: 予約済み番組の一覧表示（放送局・開始時刻・優先度・録画マージンを確認可能）
- **録画設定**: 優先度・録画開始/終了マージンをルールごとに個別設定
- **録画エンジン**: `server/app/recording/` に Mirakurun 向け録画ロジックを実装
  - 録画開始・停止・進捗管理をバックグラウンドで処理

### 2. キーワード自動予約（EPG 自動録画ルール）

キーワードや条件を指定して、マッチした番組を自動的に録画予約するルールエンジンを追加しました。

| 機能 | 説明 |
|------|------|
| **キーワード検索** | 番組名・説明文へのキーワード一致（正規表現・大小文字区別・タイトルのみ検索に対応） |
| **除外キーワード** | 指定キーワードを含む番組をルールから除外 |
| **チャンネルタイプ絞り込み** | 地デジ / BS / CS / CATV / SKY / BS4K から対象タイプを選択 |
| **ジャンル絞り込み** | ARIB 大分類ジャンルで対象番組を絞り込み（除外モードにも対応） |
| **曜日・時間帯指定** | 対象曜日と時間帯の範囲でフィルタリング（除外モードにも対応） |
| **放送種別フィルタ** | 無料放送のみ / 有料放送のみ / すべてから選択 |
| **番組長フィルタ** | 最短・最長番組長（分単位）で短すぎる/長すぎる番組を除外 |
| **重複タイトルチェック** | 同タイトルを再録画しないよう、チャンネル単位またはすべてのチャンネルで重複チェック |
| **プレビュー検索** | 保存前に条件に一致する番組を検索して件数・タイトルを確認 |

### 3. ストレージ使用量バー

ビデオページのホーム画面（録画番組一覧の上部）に、録画フォルダのディスク使用量をリアルタイムで表示するバーを追加しました。

- 録画フォルダをディスク単位にまとめて表示（同一ディスク上の複数フォルダは1エントリに集約）
- 使用量・合計容量・空き容量を人間が読みやすいサイズ形式（GB/TB）で表示
- 使用率に応じて色が変化: 通常（プライマリ）→ 75% 以上（警告黄）→ 90% 以上（エラー赤）
- `GET /api/videos/storage` エンドポイントから取得し、ページロード時に並行実行で取得

### 4. Cloudflare Access ログアウト

ボタンをクリックして、`/cdn-cgi/access/logout` をリクエストする。

### 4. Docker によるコードチェック環境

開発環境の差異（OS・Python バージョン・Node.js バージョン）に関わらず、一貫したコードチェックを実行できる Docker ベースの環境を整備しました。

```bash
# 初回のみイメージをビルド
docker compose -f docker-compose.check.yaml build

# Python (ruff + pyright) と TypeScript/Vue (eslint + vue-tsc) を一括チェック
docker compose -f docker-compose.check.yaml run --rm check
```

- Python 側: `ruff` によるリントと `pyright` による型チェックを実行
- TypeScript/Vue 側: `eslint` によるリントと `vue-tsc` による型チェックを実行
- どちらかが失敗した場合は非ゼロの終了コードで終了し、CI 等でも利用可能
- ソースコードはホストからマウントされるため、変更後に毎回リビルドする必要はない

### 5. Telegram 録画完了通知

録画が完了したときに Telegram Bot 経由でサムネイル・番組情報・再生リンクを通知する機能を追加しました。

#### 基本機能

- 録画完了時にサムネイル画像（録画ファイルから自動生成）を添付して Telegram に通知
- 番組タイトル・チャンネル名・放送時刻・番組概要・録画サイズを通知メッセージに含める
- `telegram_base_url` を設定することで、通知に「再生」ボタン（インラインキーボード）を付与可能
- Mirakurun 録画・非 Mirakurun 録画（既存録画ファイルのメタデータ解析後）の両方に対応

#### カスタムテンプレート

Telegram の **HTML モード**で送信されるメッセージ本文を自由にカスタマイズできます。

| 変数 | 内容 |
|------|------|
| `{title}` | 番組タイトル |
| `{channel}` | チャンネル名 |
| `{start_time}` | 放送開始時刻 |
| `{end_time}` | 放送終了時刻 |
| `{duration}` | 放送時間（分） |
| `{description}` | 番組概要 |
| `{file_size}` | 録画ファイルサイズ |

テンプレートは `<b>`, `<i>`, `<a href="...">` などの Telegram HTML タグを使用可能です。空欄の場合はデフォルト形式が使用されます。

#### テンプレートプレビュー

設定画面（設定 → 通知）の「テンプレートをプレビュー」ボタンから、保存前にサンプルデータで展開結果を確認できます。未知の変数名や括弧の不一致も事前に検出します。

#### config.yaml のホットリロード

`config.yaml` をエディタで直接編集した場合も、サーバーを再起動せずに設定が自動反映されます。

- `watchfiles` ライブラリによる非同期ファイル監視（`ConfigFileWatcher` クラス）
- ファイル変更検出後、約 1 秒以内にインメモリ設定が更新される
- UI 保存・手動編集の両方でホットリロードが機能する

## 追加・拡張した API

### 録画予約関連（Mirakurun バックエンド）

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/reservations` | 録画予約一覧取得 |
| POST | `/api/reservations` | 録画予約追加 |
| PUT | `/api/reservations/{reservation_id}` | 録画予約更新 |
| DELETE | `/api/reservations/{reservation_id}` | 録画予約削除 |
| GET | `/api/reservation-conditions` | 自動予約ルール一覧取得 |
| POST | `/api/reservation-conditions` | 自動予約ルール追加 |
| PUT | `/api/reservation-conditions/{condition_id}` | 自動予約ルール更新 |
| DELETE | `/api/reservation-conditions/{condition_id}` | 自動予約ルール削除 |
| POST | `/api/programs/search` | 番組検索（自動予約プレビュー・EDCB/Mirakurun 共通） |

### ストレージ関連

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/videos/storage` | 録画フォルダのディスク使用量取得（ディスク単位で重複排除） |

### Telegram 通知関連

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/settings/notification/test` | テスト通知送信（Bot トークン・チャット ID の動作確認） |
| POST | `/api/settings/notification/validate-template` | 通知テンプレート検証・サンプルデータでのプレビュー生成 |


## 変更ファイル一覧

<details>
<summary>クリックで展開</summary>

### サーバー側 (Python)

| ファイル | 変更内容 |
|---------|---------|
| `server/app/config.py` | `ConfigFileWatcher` クラス追加・`ReadCurrentConfig()` バグ修正・`SaveConfig()` のインメモリ即時反映 |
| `server/app/app.py` | `ConfigFileWatcher` の起動・停止をサーバーライフサイクルに登録 |
| `server/app/utils/TelegramNotifier.py` | **[新規]** Telegram 通知送信クラス（サムネイル添付・HTML テンプレート対応） |
| `server/app/routers/SettingsRouter.py` | Telegram テスト通知 API・テンプレート検証 API の追加 |
| `config.example.yaml` | `telegram_notification_template` フィールドの追加とコメント整備 |
| `server/app/migrations/models/10_*.py` | **[新規]** Mirakurun 録画予約 DB マイグレーション |
| `server/app/models/MirakurunReservation.py` | **[新規]** Mirakurun 録画予約モデル |
| `server/app/models/MirakurunRecordingRule.py` | **[新規]** キーワード自動予約ルールモデル |
| `server/app/recording/` | **[新規]** Mirakurun 録画エンジン（予約管理・録画開始/停止） |
| `server/app/routers/ReservationsRouter.py` | Mirakurun 録画予約 CRUD API の追加 |
| `server/app/routers/ReservationConditionsRouter.py` | **[新規]** 自動予約ルール CRUD API |
| `server/app/routers/ProgramsRouter.py` | 番組検索 API に Mirakurun バックエンド対応を追加 |
| `server/app/routers/VideosRouter.py` | `GET /api/videos/storage` エンドポイントを追加（ディスク単位重複排除・使用量集計）|
| `server/app/schemas.py` | `FolderStorageInfo`・`StorageInfo` モデルを追加 |

### クライアント側 (TypeScript / Vue)

| ファイル | 変更内容 |
|---------|---------|
| `client/src/components/Reservations/ReservationConditionEditDialog.vue` | **[新規]** キーワード自動予約ルール編集ダイアログ（チャンネル・ジャンル・曜日・プレビュー対応） |
| `client/src/components/Reservations/ReservationRecordingSettings.vue` | 録画設定コンポーネントの拡張 |
| `client/src/views/Videos/Home.vue` | ストレージ使用量バーを追加（使用率に応じた警告色変化） |
| `client/src/services/Videos.ts` | `IFolderStorageInfo`・`IStorageInfo` インターフェースと `fetchStorageInfo()` を追加 |
| `client/src/views/Settings/Notification.vue` | **[新規]** Telegram 通知設定ページ（テンプレートプレビュー UI 含む） |
| `client/src/services/Settings.ts` | `validateTelegramTemplate()` メソッド追加・通知設定フィールドの追加 |
| `client/src/services/Reservations.ts` | 録画予約 API クライアント |
| `client/src/services/ReservationConditions.ts` | 自動予約ルール API クライアント |
| `client/src/components/Navigation.vue` | 予約メニュー項目の追加 |
| `client/src/stores/VersionStore.ts` | バージョン情報ストアの更新 |

</details>

 ---
# KonomiTV Custom Fork

[本家 KonomiTV](https://github.com/tsukumijima/KonomiTV) をベースに、シリーズ管理機能の大幅拡張・キャプチャギャラリー・ログイン必須設定など、いくつかのカスタム機能を追加したフォークです。

9割以上をClaude Codeに作らせています(このRead.mdも)、そのためバグも多くあります。インストールされる際はバックアップを取ることを強く推奨します。

> **本家 KonomiTV について**: いろいろな場所とデバイスでテレビと録画を快適に見れる、モダンな Web ベースのソフトウェアです。
> 開発者: [tsukumijima](https://github.com/tsukumijima) / ライセンス: MIT

---

## 追加機能の概要

### 1. シリーズ自動グルーピング

録画番組のメタデータが解析されると、番組タイトルを自動解析してシリーズ（番組グループ）を自動的に作成します。

- **TitleParser**: 番組タイトルから作品名・話数・サブタイトルを高精度に抽出するパーサー
  - 「〇〇 第3話」「〇〇 #03 サブタイトル」「〇〇（5）」など多様なフォーマットに対応
  - 半角/全角・括弧の揺れなども正規化して正確にグルーピング
- **自動シリーズ作成**: 録画スキャン時に同一作品の番組を自動的にシリーズにまとめる
- **放送期間ごとの整理**: 同じシリーズでもチャンネルや放送期間が異なる場合は別ブロックとして表示

### 2. シリーズ手動管理

自動グルーピングで完全にまとめきれない場合に、手動でシリーズを整理できます。

| 機能 | 説明 |
|------|------|
| **シリーズ作成** | 任意の名前で空のシリーズを新規作成 |
| **シリーズ名変更** | 既存シリーズのタイトルを編集 |
| **番組追加** | 検索して任意の録画番組をシリーズに追加 |
| **番組除外** | シリーズから個別の番組を除外（録画自体は削除されない） |
| **シリーズ削除** | シリーズを削除（紐付け解除のみ、録画番組は残る） |

- 手動で編集したシリーズには `is_series_manually_edited` フラグが自動的にセットされ、次回の自動スキャンで上書きされることを防ぎます。

### 3. シリーズ結合（マージ）

分かれてしまったシリーズ同士を1つに統合できます。

- シリーズ詳細画面のマージボタンから、マージ先シリーズを検索して選択
- マージ元の全録画番組がマージ先に移動し、マージ元シリーズは自動削除
- マージ先シリーズに自動遷移

### 4. キャプチャギャラリー

テレビ視聴中・録画再生中にキャプチャした画像を一覧・検索・整理できるギャラリー機能を追加しました。

#### ギャラリー画面

- **グリッド表示**: デスクトップ 4列 / タブレット 3列 / スマートフォン 2列のレスポンシブレイアウト
- **ソート**: 新しい順 / 古い順の切り替え
- **検索**: ファイル名・番組タイトル・チャンネル名で横断検索
- **ライトボックス**: サムネイルクリックで拡大表示、メタデータ（画像サイズ・ファイルサイズ・撮影日時）も確認可能
- **ページネーション**: 1ページ36件ずつ表示

#### フォルダ管理

キャプチャを仮想フォルダで整理できます（ファイルの物理的な移動は行わず、DB 上のブックマークで管理）。

| 機能 | 説明 |
|------|------|
| **フォルダ作成** | 任意の名前でフォルダを新規作成 |
| **フォルダ名変更** | 右クリックメニューからフォルダ名を編集 |
| **フォルダ削除** | フォルダを削除（キャプチャ画像自体は残る） |
| **キャプチャ追加** | ギャラリーからキャプチャをフォルダに追加（複数選択対応） |
| **キャプチャ除外** | フォルダからキャプチャを除外（画像自体は削除されない） |
| **複数フォルダ所属** | 1つのキャプチャを複数のフォルダに入れられる（タグのような運用が可能） |

#### 一括操作

- 右クリックで選択モードに入り、複数キャプチャを一括選択
- 選択したキャプチャをまとめてフォルダに追加・フォルダから除外・削除

#### キャプチャ設定

設定画面（設定 → キャプチャ）から以下を設定可能:

- **保存モード**: ブラウザダウンロード / サーバーアップロード / 両方
- **字幕合成モード**: 映像のみ / 字幕合成 / 両方
- **ファイル名パターン**: TVTest 互換マクロ展開（`%date%`, `%channel-name%`, `%event-name%` など）
- **クリップボードコピー**: キャプチャ時にクリップボードにもコピー

#### EXIF メタデータ

キャプチャ画像の EXIF に番組情報（タイトル・チャンネル・放送日時・字幕テキストなど）が JSON 形式で埋め込まれます。ギャラリーでの検索やメタデータ表示に活用されます。

### 5. ログイン必須設定

KonomiTV にアクセスする際にログインを必須にするサーバー設定を追加しました。

- **設定画面**: サーバー設定 → 「ログインを必須にする」スイッチで ON/OFF
- **動作**: 有効時、未ログインユーザーはすべてのページでログイン画面にリダイレクトされる
- **リダイレクト対応**: ログイン後、元々アクセスしようとしていたページに自動的に戻る

### 6. テーマ機能（ライト/ダークモード・アクセントカラー）

設定画面からテーマモードとアクセントカラーを切り替えられるようになりました。

#### テーマモード
- **ダークモード**（デフォルト）: 本家と同じダークテーマ
- **ライトモード**: 背景色がニュートラルな白色（`#f5f5f5`）のライトテーマ
  - サイドバー・ナビゲーションのアクティブ項目がテーマ色に合わせて自動的に変化
  - ヘッダーの KonomiTV ロゴがライトモード用の暗色テキストに自動切り替え
  - 録画番組サムネイルのステータスバッジ（「メタデータ解析中」等）がテーマに合わせた文字色で表示

#### アクセントカラー
9種類のプリセットカラーから UI 全体のアクセントカラーを変更できます:

ピンク（デフォルト）/ レッド / オレンジ / アンバー / グリーン / ティール / ブルー / インディゴ / パープル

### 7. モバイルレスポンシブ対応

シリーズ一覧・シリーズ詳細画面をスマートフォン縦画面で快適に使えるようにレイアウトを最適化しました。

- **シリーズ詳細**: タイトルとアクションボタンが2行に分かれて表示、エピソード件数も画面内に収まる
- **シリーズ一覧**: タイトル行とアクション行が2段に折り返し、「シリーズ一覧」テキストが改行されない

---

## 追加・拡張した API

### シリーズ関連

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/series` | シリーズ一覧取得（ソート・ページネーション対応） |
| GET | `/api/series/{series_id}` | シリーズ詳細取得 |
| GET | `/api/series/search` | シリーズ検索 |
| POST | `/api/series` | シリーズ新規作成 |
| PUT | `/api/series/{series_id}` | シリーズ名変更 |
| DELETE | `/api/series/{series_id}` | シリーズ削除 |
| POST | `/api/series/{series_id}/programs/{program_id}` | シリーズに番組追加 |
| DELETE | `/api/series/{series_id}/programs/{program_id}` | シリーズから番組除外 |
| POST | `/api/series/{source_id}/merge/{target_id}` | シリーズ結合（source → target） |

### キャプチャギャラリー関連

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/captures` | キャプチャ一覧取得（ソート・ページネーション・検索対応） |
| GET | `/api/captures/{filename}` | キャプチャ画像取得（サムネイル生成対応） |
| POST | `/api/captures` | キャプチャ画像アップロード |
| DELETE | `/api/captures/{filename}` | キャプチャ画像削除 |
| GET | `/api/captures/folders` | フォルダ一覧取得 |
| POST | `/api/captures/folders` | フォルダ新規作成 |
| PUT | `/api/captures/folders/{folder_id}` | フォルダ名変更・並び順変更 |
| DELETE | `/api/captures/folders/{folder_id}` | フォルダ削除（画像は残る） |
| GET | `/api/captures/folders/{folder_id}/captures` | フォルダ内キャプチャ一覧取得 |
| POST | `/api/captures/folders/{folder_id}/captures` | フォルダにキャプチャ追加 |
| DELETE | `/api/captures/folders/{folder_id}/captures` | フォルダからキャプチャ除外 |

---

## 変更ファイル一覧

<details>
<summary>クリックで展開</summary>

### サーバー側 (Python)

| ファイル | 変更内容 |
|---------|---------|
| `server/app/config.py` | `require_login` 設定フィールドの追加 |
| `server/app/metadata/TitleParser.py` | **[新規]** 番組タイトル解析パーサー |
| `server/app/metadata/RecordedScanTask.py` | シリーズ自動グルーピングロジックの追加 |
| `server/app/models/Series.py` | シリーズモデルの拡張 |
| `server/app/models/SeriesBroadcastPeriod.py` | 放送期間モデルの拡張 |
| `server/app/models/RecordedProgram.py` | `is_series_manually_edited` フラグ追加 |
| `server/app/routers/SeriesRouter.py` | シリーズ CRUD + マージ API の追加 |
| `server/app/routers/CapturesRouter.py` | キャプチャギャラリー API の拡張（フォルダ CRUD・検索・サムネイル） |
| `server/app/models/CaptureFolder.py` | **[新規]** キャプチャフォルダモデル |
| `server/app/models/CaptureBookmark.py` | **[新規]** キャプチャブックマーク（フォルダ紐付け）モデル |
| `server/app/schemas.py` | シリーズ・キャプチャ関連スキーマの追加 |
| `server/app/migrations/models/8_*.py` | **[新規]** シリーズ関連 DB マイグレーション |
| `server/app/migrations/models/9_*.py` | **[新規]** 追加マイグレーション |

### クライアント側 (TypeScript / Vue)

| ファイル | 変更内容 |
|---------|---------|
| `client/src/views/Videos/Series.vue` | **[新規]** シリーズ一覧ページ |
| `client/src/views/Videos/SeriesDetail.vue` | **[新規]** シリーズ詳細ページ (編集・マージ UI 含む) |
| `client/src/views/Captures.vue` | **[新規]** キャプチャギャラリーページ（一覧・検索・フォルダ・ライトボックス） |
| `client/src/views/Settings/Capture.vue` | **[新規]** キャプチャ設定ページ |
| `client/src/services/Captures.ts` | キャプチャ API クライアント（アップロード・フォルダ CRUD） |
| `client/src/services/Series.ts` | シリーズ API クライアント (CRUD + マージ) |
| `client/src/services/Settings.ts` | `require_login` フィールド追加 |
| `client/src/views/Settings/General.vue` | テーマモード・アクセントカラー設定 UI の追加 |
| `client/src/views/Settings/Server.vue` | ログイン必須設定の v-switch 追加 |
| `client/src/services/player/managers/CaptureManager.ts` | EXIF メタデータ埋め込み・サーバーアップロード対応 |
| `client/src/plugins/vuetify.ts` | ライトテーマ定義・アクセントカラープリセット・動的テーマ切り替え関数 |
| `client/src/stores/SettingsStore.ts` | テーマモード・アクセントカラー設定フィールドの追加 |
| `client/src/main.ts` | テーマ初期化・設定変更時のテーマ即時反映 |
| `client/src/components/HeaderBar.vue` | テーマに応じたロゴ画像の動的切り替え |
| `client/src/components/SPHeaderBar.vue` | テーマに応じたロゴ画像の動的切り替え |
| `client/src/components/Navigation.vue` | サイドバーのアクティブ項目色をテーマ対応に変更 |
| `client/src/components/Videos/RecordedProgram.vue` | サムネイルバッジのテキスト色をテーマ対応に変更 |
| `client/src/App.vue` | テキスト選択色をテーマ変数に変更 |
| `client/public/assets/images/logo-light.svg` | **[新規]** ライトモード用ロゴ画像 |
| `client/src/router/index.ts` | キャプチャギャラリールート追加・ログイン必須 `beforeEach` ガード追加 |
| `client/src/views/Login.vue` | リダイレクト対応 |
| `client/src/components/Videos/RecordedProgramList.vue` | シリーズ向け表示対応 |

</details>

---

## ライセンス

本家 KonomiTV と同じく [MIT License](License.txt) です。

Copyright (c) 2021-2026 [tsukumijima](https://github.com/tsukumijima) (本家)
カスタム機能の追加: [ichigomoti](https://github.com/ichigomoti)
