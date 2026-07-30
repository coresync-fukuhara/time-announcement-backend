# タイムアナウンスメント

`src/main.py` は、曜日×時間のスケジュール（`settings/schedules.json`）に従って `.wav` を再生します。

## 前提

- Python 3.10+
- 音声出力できる環境（Linux では PortAudio が必要な場合あり）

## セットアップ

```bash
uv sync
```

## DB とマイグレーション

このプロジェクトは SQLite + SQLAlchemy で楽曲メタ情報を管理します。

- DBファイル: `db/music.sqlite3`
- テーブル:
  - `wav_tracks`（楽曲名・ファイルパス）
  - `audio_types`（タイプマスタ）
  - `track_audio_types`（楽曲とタイプの紐づけ）

### マイグレーション実行

```bash
uv run python scripts/migrate_music_db.py
```

マイグレーション内容:

1. テーブル作成
2. `schedules_models.AudioType` を `audio_types` に登録（description は `None`）
   - 現在対応しているタイプ: `DEFAULT`, `NOTIFICATION`, `ALARM`
3. `sounds/default/*.wav` を `wav_tracks` に登録
   - 全曲に `DEFAULT`
   - `*notify.wav` は `NOTIFICATION` も追加
4. `sounds/user/*.wav` を `wav_tracks` に登録
   - 曲ごとにタイプを対話入力

既にテーブルがある場合:

- `y`: テーブルをクリーンして再マイグレーション
- `n`: 現在のテーブル状態を表示して終了

### 楽曲名の扱い

- DBに保存する楽曲名は `*.wav` の拡張子を除いた名前です
  - 例: `sample.wav` → `sample`

## スケジュール設定

- 設定ファイル: `settings/schedules.json`
- 形式: `monday` 〜 `sunday`（任意で `holiday`）

基本形:

```json
{ "hour": 9, "minutes": [0, 30] }
```

`minute_settings` で分ごとの詳細指定ができます。

```json
{
  "hour": 9,
  "minutes": [0, 30],
  "minute_settings": {
    "0": {
      "sound_file_name": "sample.wav"
    },
    "30": {
      "sound_types": ["NOTIFICATION"]
    }
  }
}
```

## 選曲ルール（main.py）

`minute_settings` の処理は次の優先順位です。

1. `sound_file_name` がある場合
   - 最優先で使用
   - `.wav` が付いていてもトリムしてDBの楽曲名で検索
   - 見つからなければエラー（`FileNotFoundError`）
   - このとき `sound_types` は無視

2. `sound_file_name` がない場合
   - `sound_types` からランダムに1曲選択
   - `sound_types` 未指定なら `ALARM` をデフォルトタイプとして扱う
   - 見つからなければエラー（`FileNotFoundError`）

## 実行

```bash
uv run python src/main.py
```

## Docker でのデプロイ

方式の詳細・決定理由は [docs/catchup/docker_deployment_survey.md](docs/catchup/docker_deployment_survey.md) を参照。

- 毎分の起動: コンテナ内蔵の [supercronic](https://github.com/aptible/supercronic) が担う（外部 cron 不要）
- 音声出力: ホストの PulseAudio/PipeWire-pulse ソケットを bind mount して共有
- 永続化データ（`db/`, `settings/`, `sounds/user/`）: 別リポジトリのフロントエンドと共有する named volume

### 1. named volume を作成（初回のみ）

```bash
docker volume create time-announcement-db
docker volume create time-announcement-settings
docker volume create time-announcement-sounds-user
```

### 2. 環境変数を設定

```bash
cp .env.example .env
# PULSE_SOCKET_PATH: 対象ホストで `pactl info` 等を実行して実際のソケットパスを確認して設定
# PUID/PGID: ホストの音声出力ユーザー（上記ソケットの所有者）の UID/GID に合わせる
```

### 3. 起動

```bash
docker compose up -d --build
```

`settings/schedules.json` が未配置の場合、イメージに焼き込まれた `sample_schedules.json` の内容が named volume の初期化時にコピーされ、サンプル設定のまま起動する。

### 4. DB マイグレーション（初回・対話式）

```bash
docker compose run --rm -it app uv run python scripts/migrate_music_db.py
```

## 補足

- スキーマ定義: `settings/schema.json`
- 生成モデル: `src/schedules_models.py`
