
# タイムアナウンスメント

`src/main.py` は、曜日×時間のスケジュール（[settings/schedules.json](settings/schedules.json)）に従って、正時（分=0）に `sounds/` 配下の `.wav` をランダムに1曲再生します。

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

- `sounds/` 配下の `.wav` を対象にします。
- 実行時にその中からランダムに1つ選び再生します。

### スケジュール

- 設定ファイル: [settings/schedules.json](settings/schedules.json)
- 形式: 「7要素（曜日）」×「各曜日は時間設定の配列」
- 曜日インデックスは Python の `datetime.weekday()` と同じです。
	- `0=月, 1=火, ..., 5=土, 6=日`

各時間設定は `{ "hour": 0-23 }` のオブジェクトです。
スキーマは [settings/schema.json](settings/schema.json) にあります。

例（毎日 9時と18時だけ鳴らす）:

```json
[
	[{"hour": 9}, {"hour": 18}],
	[{"hour": 9}, {"hour": 18}],
	[{"hour": 9}, {"hour": 18}],
	[{"hour": 9}, {"hour": 18}],
	[{"hour": 9}, {"hour": 18}],
	[{"hour": 9}, {"hour": 18}],
	[{"hour": 9}, {"hour": 18}]
]
```

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

