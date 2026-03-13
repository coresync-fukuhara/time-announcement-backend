
# タイムアナウンスメント

`src/main.py` は、曜日×時間のスケジュール（[settings/schedules.json](settings/schedules.json)）に従って、指定されたタイミングで `sounds/` 配下の `.wav` を再生します。

## 前提

- Python 3.10+（`zoneinfo` を使用）
- 音声出力できる環境（Linux では PortAudio が必要なことがあります）

## セットアップ

依存パッケージをインストールします。

```bash
pip install -r requirements.txt
```

Linux で `sounddevice` のロードに失敗する場合は、PortAudio 系のパッケージが不足している可能性があります（環境によりパッケージ名が異なります）。

## 設定

### 音源

- デフォルト音源として `sounds/default/` 配下に `.wav` が同梱されています（例: `sounds/default/sample.wav`）。
- ユーザーは `sounds/user/` 配下に `.wav` ファイルを追加できます。
  - `sounds/user/` に1つ以上の `.wav` がある場合は、**その中からランダムに1つ**選んで再生します。
  - `sounds/user/` に `.wav` がない場合は、**`sounds/default/` 配下の `.wav` をランダムに1つ**再生します。

### スケジュール

- 設定ファイル: [settings/schedules.json](settings/schedules.json)
- 形式: **曜日キー（`monday` 〜 `sunday`）** を持つオブジェクト

各時間設定（各曜日の配列要素）は基本的に次のようなオブジェクトです。

```json
{ "hour": 0-23, "minutes": [0-59, ...] }
```

- **`minutes`**: その時間帯で鳴らす分のリストです。
  - 例: `{"hour": 9, "minutes": [0, 30]}` → 9:00 と 9:30 に鳴る
  - 例: `{"hour": 17, "minutes": [0]}` → 17:00 のみ鳴る
- **省略時の挙動**: `minutes` を省略した場合は「**0分のみ**」有効として扱われます（実装側でそう解釈します）。

さらに、分ごとに詳細設定を付けたい場合は、任意で `minute_settings` を追加できます。

```json
{
  "hour": 9,
  "minutes": [0, 30],
  "minute_settings": {
    "0": {
      "sound_file_name": "morning.wav"
    },
    "30": {
      "sound_file_name": "break.wav"
    }
  }
}
```

- **`minute_settings`**: キーは「分」を文字列化したもの（例: `"0"`, `"30"`）です。
- **`sound_file_name`**: 使用したい `.wav` ファイル名（一致する部分文字列）です。
  - 実際には `sounds/user/` と `sounds/default/` を走査し、パスの中にこの文字列を含むファイルを探します。
  - 見つかった場合はそのファイルを優先的に再生します。
  - 見つからない、または `minute_settings` 自体がない場合は、候補リストからランダムに1つ選んで再生します。

スキーマ定義は [settings/schema.json](settings/schema.json) を参照してください。

#### 例1（毎日 9時と18時の **0分のみ** 鳴らす）

```json
{
  "monday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }],
  "tuesday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }],
  "wednesday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }],
  "thursday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }],
  "friday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }],
  "saturday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }],
  "sunday": [{ "hour": 9, "minutes": [0] }, { "hour": 18, "minutes": [0] }]
}
```

#### 例2（毎日 9時と17時の **0分と30分** に鳴らす）

```json
{
  "monday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }],
  "tuesday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }],
  "wednesday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }],
  "thursday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }],
  "friday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }],
  "saturday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }],
  "sunday": [{ "hour": 9, "minutes": [0, 30] }, { "hour": 17, "minutes": [0, 30] }]
}
```

※ 現在の実装は **曜日キー形式のみ** を前提にしています（`monday`〜`sunday` のキーが必要です）。

## 実行方法

`src/main.py` は `from schedules_models import ...` の形で import しているため、`src/` をカレントディレクトリにして実行するのが簡単です。

```bash
cd src
python main.py
```

### 実行条件（鳴るタイミング）

- タイムゾーンは `Asia/Tokyo` 固定です。
- 実行した時刻の **分が 0** のときのみ鳴ります（正時のみ）。
- その曜日のスケジュールに、現在の `hour` が含まれているときのみ鳴ります。

つまり、このスクリプトを「毎分」などで定期実行しておき、正時だけ鳴らす運用を想定しています。

## よくあるトラブル

- `.wav` が見つからない: `sounds/` 配下に `.wav` があるか確認してください。
- 音が出ない/デバイスエラー: OS 側の音声出力デバイス設定、PortAudio、実行権限（コンテナ内など）を確認してください。
- JSON が壊れている: [settings/schedules.json](settings/schedules.json) が JSON として正しい形式か確認してください。

