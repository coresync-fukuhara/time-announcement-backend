# テスト設計書 — タイムアナウンスメント

| 項目 | 内容 |
| --- | --- |
| 対象システム | タイムアナウンスメント (time-announcement-backend) 0.1.0 |
| 対象実装 | `src/main.py`, `src/music_db.py`, `scripts/migrate_music_db.py` |
| 関連文書 | [概要設計書](./design_overview.md) |
| 作成日 | 2026-07-29 |
| 現状 | **テストコード未実装**。本書は既存実装に対して作成すべきテストの設計 |

---

## 1. テスト方針

### 1.1 基本方針

- **ロジックの分岐網羅を単体テストで担保する**。本システムのバグ混入リスクは「スケジュール解決の分岐」と「楽曲解決の優先順位」に集中しており、ここを重点的に検証する。
- **外部依存はモック／実体差し替えで排除する**。
  - `sounddevice`（音声デバイス）: CI に音声デバイスが無いため必ずモック。
  - `datetime.now`: 現在時刻を注入可能な形にして固定値でテスト。
  - `jpholiday`: 実ライブラリをそのまま使用（実日付を用いる）。祝日判定そのものは外部ライブラリの責務。
  - `random.shuffle` / `func.random()`: シード固定またはモックで決定化。
- **DB は実 SQLite（インメモリまたは tmp ファイル）を使用する**。ORM のマッピング・制約・カスケードは実 DB でなければ検証価値が無いため、モックしない。
- 対話入力（`input()`）は `monkeypatch` で差し替える。

### 1.2 テストレベル

| レベル | 対象 | 目的 |
| --- | --- | --- |
| UT（単体） | 関数単位 | 分岐網羅・境界値・異常系 |
| IT（結合） | `main.py` × `music_db.py` × 実 SQLite | モジュール間の受け渡しとデータ整合 |
| ST（システム） | エントリポイント一括実行 | セットアップ〜再生までの通し確認 |

### 1.3 品質目標

| 指標 | 目標 |
| --- | --- |
| 行カバレッジ | `src/` 90% 以上 |
| 分岐カバレッジ | `src/main.py` の分岐 100%（音声再生部を除く） |
| 異常系 | 設計書 6章に記載の既知課題に対応するケースを全て保持 |

---

## 2. テスト環境

### 2.1 必要な追加依存

現状 `pyproject.toml` にテスト依存が無いため、以下の追加が前提。

```toml
[dependency-groups]
dev = [
    "ruff",
    "pytest",
    "pytest-cov",
]
```

### 2.2 ディレクトリ構成（提案）

```
tests/
├── conftest.py              # 共通フィクスチャ
├── unit/
│   ├── test_main_schedule.py    # スケジュール解決
│   ├── test_main_resolve.py     # 楽曲解決
│   ├── test_main_helpers.py     # 正規化・抽出ヘルパ
│   └── test_music_db.py         # ORM・検索API
├── integration/
│   ├── test_main_flow.py
│   └── test_migrate_music_db.py
└── fixtures/
    ├── schedules_valid.json
    ├── schedules_broken.json
    └── silence.wav          # 極小の無音 wav
```

`src/` は import パス上にないため、`conftest.py` で `sys.path` に追加するか `pyproject.toml` に `[tool.pytest.ini_options] pythonpath = ["src"]` を設定する。

### 2.3 共通フィクスチャ

| 名称 | 内容 |
| --- | --- |
| `engine` | `create_sqlite_engine(tmp_path/"test.sqlite3")` + `init_db()` |
| `session` | 上記エンジンからのセッション（テストごとにロールバック） |
| `seeded_db` | `AudioType` 3種 + 楽曲数件（実在する tmp ファイルパス付き）を投入済みの DB |
| `no_audio` | `sounddevice.play` / `wait` をモック |
| `frozen_now` | `datetime.datetime(2026, 7, 29, 9, 30, tzinfo=ZoneInfo("Asia/Tokyo"))` 等の固定時刻 |
| `reset_db_factory` | `main._DB_SESSION_FACTORY = None` に戻す（**グローバルキャッシュのリーク防止に必須**） |

> `main._DB_SESSION_FACTORY` はモジュールグローバルにキャッシュされるため、リセットしないとテスト間で状態が汚染される。全テストに自動適用（`autouse=True`）とすること。

---

## 3. テスト観点一覧

| 観点 ID | 観点 | 対象 |
| --- | --- | --- |
| V-01 | 楽曲名の正規化（trim / 拡張子除去 / 大文字小文字） | `_normalize_track_name` |
| V-02 | 設定値の抽出（dict / Pydantic 両対応、空文字、不正値） | `_extract_sound_file_name` / `_extract_sound_types` |
| V-03 | 設定ファイル読込の異常系 | `load_schedule` |
| V-04 | 祝日 / 曜日の切替とフォールバック | `get_minute_setting` |
| V-05 | 時・分のマッチング（`minutes` 省略時の全分扱いを含む） | `get_minute_setting` |
| V-06 | 「再生しない(None)」と「既定で再生({})」の区別 | `get_minute_setting` |
| V-07 | 楽曲解決の優先順位（名前 > タイプ > ALARM 既定） | `get_sound_file` |
| V-08 | DB 未構築・ファイル欠損時の挙動 | `_resolve_track_path_by_*` |
| V-09 | ORM 制約（UNIQUE / FK / CASCADE） | `music_db` |
| V-10 | 検索クエリの正当性（タイプ絞り込み・除外・ランダム） | `music_db` |
| V-11 | マイグレーションの冪等性と分岐（y/n） | `migrate_music_db` |
| V-12 | 対話入力のバリデーション | `migrate_music_db` |
| V-13 | 音声再生の呼出し（副作用のモック検証） | `play_sound` |

---

## 4. 単体テストケース

### 4.1 `_normalize_track_name`（V-01）

| ID | 入力 | 期待結果 |
| --- | --- | --- |
| UT-N-01 | `"sample.wav"` | `"sample"` |
| UT-N-02 | `"  sample.wav  "` | `"sample"` |
| UT-N-03 | `"sample.WAV"` | `"sample"`（大文字小文字非依存） |
| UT-N-04 | `"sample"` | `"sample"`（拡張子なしはそのまま） |
| UT-N-05 | `"my.wav.file"` | `"my.wav.file"`（末尾一致のみ除去） |
| UT-N-06 | `""` | `""` |
| UT-N-07 | `".wav"` | `""`（境界値） |

### 4.2 `_extract_sound_file_name`（V-02）

| ID | 入力 | 期待結果 |
| --- | --- | --- |
| UT-F-01 | `{"sound_file_name": "a.wav"}` | `"a.wav"` |
| UT-F-02 | `MinuteSettings(sound_file_name="a.wav")` | `"a.wav"`（Pydantic モデル経路） |
| UT-F-03 | `{}` | `None`（キー無し） |
| UT-F-04 | `{"sound_file_name": None}` | `None` |
| UT-F-05 | `{"sound_file_name": "   "}` | `None`（空白のみ→None） |
| UT-F-06 | `{"sound_file_name": "  a.wav "}` | `"a.wav"`（trim される） |

### 4.3 `_extract_sound_types`（V-02）

| ID | 入力 | 期待結果 |
| --- | --- | --- |
| UT-T-01 | `{"sound_types": None}` | `[]` |
| UT-T-02 | `{}` | `[]` |
| UT-T-03 | `{"sound_types": ["ALARM"]}` | `["ALARM"]` |
| UT-T-04 | `{"sound_types": [AudioType.NOTIFICATION]}` | `["NOTIFICATION"]`（Enum 経路） |
| UT-T-05 | `{"sound_types": ["ALARM", "NOTIFICATION"]}` | `["ALARM", "NOTIFICATION"]`（順序保持） |
| UT-T-06 | `{"sound_types": ["ALARM", "ALARM"]}` | `["ALARM"]`（重複除去） |
| UT-T-07 | `{"sound_types": ["UNKNOWN"]}` | `[]`（不正値は黙って除外） |
| UT-T-08 | `{"sound_types": ["ALARM", "UNKNOWN", "DEFAULT"]}` | `["ALARM", "DEFAULT"]` |
| UT-T-09 | `{"sound_types": ["", "  "]}` | `[]`（空文字はスキップ） |
| UT-T-10 | `{"sound_types": ["alarm"]}` | `[]`（**大文字小文字は区別される**＝現仕様の確認） |

### 4.4 `load_schedule`（V-03）

| ID | 前提 | 期待結果 |
| --- | --- | --- |
| UT-L-01 | 正常な JSON | 読み込んだ dict がそのまま返る |
| UT-L-02 | 壊れた JSON | `{}` が返る（例外を送出しない） |
| UT-L-03 | 空ファイル | `{}` が返る |
| UT-L-04 | ファイル不在 | `FileNotFoundError` が送出される（**課題 6.3 の現仕様を固定するテスト**） |
| UT-L-05 | UTF-8 日本語を含む JSON | 文字化けせず読み込める |

### 4.5 `_find_hour_settings` / `_is_japanese_holiday`

| ID | 内容 | 期待結果 |
| --- | --- | --- |
| UT-H-01 | `hour=9` の要素が存在 | 該当 dict を返す |
| UT-H-02 | `hour=9` が存在しない | `None` |
| UT-H-03 | `hour` が重複して複数存在 | **先頭の要素**を返す |
| UT-H-04 | スケジュールが `[]` | `None` |
| UT-H-05 | `hour` が `9.0`（float） | `9` と一致し該当 dict を返す（JSON の number 型対応） |
| UT-H-06 | 2026-01-01（元日） | `_is_japanese_holiday` が `True` |
| UT-H-07 | 2026-07-29（平日） | `_is_japanese_holiday` が `False` |

### 4.6 `get_minute_setting`（V-04 / V-05 / V-06）

前提: `now = 2026-07-29(水) 09:30 JST`（平日）／祝日ケースは `2026-01-01(木)` を使用。

| ID | 観点 | スケジュール | 期待結果 |
| --- | --- | --- | --- |
| UT-M-01 | 平日・時分一致 | `wednesday: [{hour:9, minutes:[0,30]}]` | `{}`（空設定＝既定再生） |
| UT-M-02 | 平日・分が非該当 | `wednesday: [{hour:9, minutes:[0]}]` | `None` |
| UT-M-03 | 時が非該当 | `wednesday: [{hour:10, minutes:[30]}]` | `None` |
| UT-M-04 | 曜日キーが存在しない | `{}` | `None` |
| UT-M-05 | `minutes` 省略 | `wednesday: [{hour:9}]` | `{}`（**全分が対象**） |
| UT-M-06 | `minutes` が空配列 | `wednesday: [{hour:9, minutes:[]}]` | `{}`（全分が対象） |
| UT-M-07 | `minute_settings` に該当分あり | `minute_settings: {"30": {"sound_file_name":"a.wav"}}` | 該当の設定 dict |
| UT-M-08 | `minute_settings` に該当分なし | `minute_settings: {"0": {...}}` | `{}` |
| UT-M-09 | `minute_settings` が `null` | `minute_settings: null` | `{}`（**回帰: commit f941307 の修正内容**） |
| UT-M-10 | 祝日・holiday 定義あり | `holiday: [{hour:9, minutes:[30]}]` | holiday 側が採用される |
| UT-M-11 | 祝日・holiday が空配列 | `holiday: []`, `thursday: [{hour:9,minutes:[30]}]` | **曜日側にフォールバック**して `{}` |
| UT-M-12 | 祝日・holiday キー無し | `holiday` 未定義 | 曜日側にフォールバック |
| UT-M-13 | 祝日・holiday に該当時刻なし | `holiday: [{hour:12}]` | `None`（曜日側にはフォールバックしない） |
| UT-M-14 | 境界値 | `hour:0, minutes:[0]`, `now=00:00` | `{}` |
| UT-M-15 | 境界値 | `hour:23, minutes:[59]`, `now=23:59` | `{}` |

> UT-M-11 と UT-M-13 の差（「holiday が空なら曜日へ、holiday に時刻が無ければ None」）が現仕様の要注意点。

### 4.7 `_resolve_track_path_by_name`（V-08）

| ID | 前提 | 期待結果 |
| --- | --- | --- |
| UT-R-01 | DB ファイル不在 | `None`（例外を出さない） |
| UT-R-02 | 楽曲あり・実ファイルあり | `file_path` を返す |
| UT-R-03 | 楽曲あり・実ファイル無し | `None` |
| UT-R-04 | 楽曲なし | `None` |
| UT-R-05 | `"sample.wav"` で検索、DB には `"sample"` | ヒットする（正規化の連携確認） |
| UT-R-06 | 2回連続呼出し | セッションファクトリが 1 回だけ生成される（キャッシュ確認） |

### 4.8 `_resolve_track_path_by_types`（V-08）

| ID | 前提 | 期待結果 |
| --- | --- | --- |
| UT-Y-01 | DB ファイル不在 | `None` |
| UT-Y-02 | 単一タイプ・該当曲あり | そのパスを返す |
| UT-Y-03 | 複数タイプ・1つ目該当なし・2つ目該当あり | 2つ目のパスを返す |
| UT-Y-04 | 全タイプ該当なし | `None` |
| UT-Y-05 | 該当曲はあるが実ファイル欠損 | `None`（次タイプがあればそちらを探索） |
| UT-Y-06 | `random.shuffle` をモックで固定 | 探索順が期待どおり |
| UT-Y-07 | 空リスト `[]` | `None` |

### 4.9 `get_sound_file`（V-07）

| ID | 入力 | 期待結果 |
| --- | --- | --- |
| UT-S-01 | `None` | `ValueError` |
| UT-S-02 | `{"sound_file_name": "sample.wav"}`（DB に存在） | 該当パス |
| UT-S-03 | `{"sound_file_name": "missing.wav"}` | `FileNotFoundError`、メッセージに正規化後の名前 `missing` を含む |
| UT-S-04 | `{"sound_file_name": "sample.wav", "sound_types": ["NOTIFICATION"]}` | **名前が優先**され、タイプ検索は呼ばれない（モックで呼出し回数 0 を確認） |
| UT-S-05 | `{"sound_types": ["NOTIFICATION"]}` | NOTIFICATION の楽曲パス |
| UT-S-06 | `{}` | **ALARM** で検索される（既定タイプ） |
| UT-S-07 | `{"sound_file_name": "  "}` | 空扱い → タイプ検索へフォールバック（ALARM） |
| UT-S-08 | `{"sound_types": ["ALARM"]}`（該当なし） | `FileNotFoundError`、メッセージにタイプ名を含む |
| UT-S-09 | `{"sound_types": ["UNKNOWN"]}` | 不正値除外の結果空 → ALARM にフォールバック |

### 4.10 `play_sound`（V-13）

| ID | 前提 | 期待結果 |
| --- | --- | --- |
| UT-P-01 | 有効な wav パス（`sounddevice` はモック） | `sd.play` と `sd.wait` が各1回呼ばれる |
| UT-P-02 | `wavfile.read` の戻り（fs, data）を検証 | `sd.play(data, fs)` の引数順が正しい |
| UT-P-03 | 存在しないパス | `FileNotFoundError`（`wavfile.read` 由来） |

### 4.11 `music_db`（V-09 / V-10）

| ID | 内容 | 期待結果 |
| --- | --- | --- |
| UT-D-01 | `init_db` 実行 | `wav_tracks` / `audio_types` / `track_audio_types` の3テーブルが作成される |
| UT-D-02 | `create_sqlite_engine` に未作成ディレクトリのパス | 親ディレクトリが自動生成される |
| UT-D-03 | FK 有効化確認 | `PRAGMA foreign_keys` が `1` |
| UT-D-04 | `wav_tracks.name` 重複 INSERT | `IntegrityError` |
| UT-D-05 | `wav_tracks.file_path` 重複 INSERT | `IntegrityError` |
| UT-D-06 | `audio_types.name` 重複 INSERT | `IntegrityError` |
| UT-D-07 | 同一 (track_id, audio_type_id) の重複 | `IntegrityError`（`uq_track_audio_type`） |
| UT-D-08 | 存在しない `track_id` で中間テーブルに INSERT | `IntegrityError`（FK 違反） |
| UT-D-09 | `wav_tracks` の行を DELETE | 中間テーブルの該当行も削除される（CASCADE） |
| UT-D-10 | `audio_types` の行を DELETE | 中間テーブルの該当行も削除される（CASCADE） |
| UT-D-11 | `created_at` / `updated_at` の自動設定 | INSERT 時に UTC 時刻が入る |
| UT-D-12 | 既存行の UPDATE | `updated_at` のみ更新される |
| UT-D-13 | `get_track_by_name` 一致 | 該当 1 件、`types` が eager load 済み（セッション外でもアクセス可） |
| UT-D-14 | `get_track_by_name` 不一致 | `None` |
| UT-D-15 | `get_random_track_by_type` 該当あり | 指定タイプを持つ曲のみが返る（100回試行しても他タイプは出ない） |
| UT-D-16 | `get_random_track_by_type` 該当なし | `None` |
| UT-D-17 | `exclude_track_names` 指定 | 除外した曲は返らない |
| UT-D-18 | `exclude_track_names` で全件除外 | `None` |
| UT-D-19 | ランダム性 | 同一タイプに複数曲がある場合、多数回試行で 2 種類以上が出現する |
| UT-D-20 | 多対多の双方向 | `track.types` / `audio_type.tracks` が整合する |

---

## 5. 結合テストケース

### 5.1 `main()` 通し（V-06 / V-07 / V-13）

前提: 実 SQLite（シード済み）、`sounddevice` はモック、時刻固定。

| ID | シナリオ | 期待結果 |
| --- | --- | --- |
| IT-01 | 該当時刻・`minute_settings` なし | ALARM から 1 曲選ばれ `sd.play` が 1 回呼ばれる |
| IT-02 | 該当時刻・`sound_file_name` 指定 | 指定曲のパスで `sd.play` が呼ばれる |
| IT-03 | 該当時刻・`sound_types` 指定 | 該当タイプの曲で `sd.play` が呼ばれる |
| IT-04 | 非該当時刻 | `sd.play` が呼ばれない（`get_minute_setting` が `None`） |
| IT-05 | 該当時刻だが DB 未構築 | `FileNotFoundError` が送出される |
| IT-06 | 該当時刻だが DB の `file_path` が実在しない | `FileNotFoundError` |
| IT-07 | 祝日 | holiday スケジュールに従って再生される |
| IT-08 | `schedules.json` が壊れている | `{}` として扱われ、`sd.play` が呼ばれない |
| IT-09 | `sample_schedules.json` をそのまま使用 | 09:00 / 09:30 / 10:00 等で再生され、09:15 では再生されない |
| IT-10 | 相対パス依存 | CWD をリポジトリルート以外にして実行した場合の挙動を確認（**課題 6.8 の検証**） |

### 5.2 `scripts/migrate_music_db.py`（V-11 / V-12）

前提: `tmp_path` 配下に `db/`, `sounds/default/`, `sounds/user/` を用意し、`input()` を `monkeypatch` で差し替える。

| ID | シナリオ | 期待結果 |
| --- | --- | --- |
| IT-M-01 | 初回実行（テーブル無し） | 3テーブル作成、`audio_types` に 3 件、戻り値 0 |
| IT-M-02 | `sounds/default` 登録 | 全 wav に `DEFAULT` が付与される |
| IT-M-03 | `*notify.wav` | `DEFAULT` + `NOTIFICATION` の 2 タイプが付与される |
| IT-M-04 | `sample.wav`（notify でない） | `DEFAULT` のみ |
| IT-M-05 | `sounds/user` の対話選択（`"1"`） | 選択した 1 タイプのみ付与 |
| IT-M-06 | 対話選択（`"1,3"`） | 2 タイプ付与、順序は昇順 |
| IT-M-07 | 対話入力が空 | 再入力を促し、ループする |
| IT-M-08 | 対話入力が非数値（`"abc"`） | 「数値で入力してください。」を表示し再入力 |
| IT-M-09 | 対話入力が範囲外（`"9"`） | 「範囲外の番号があります。」を表示し再入力 |
| IT-M-10 | 既存テーブルあり + `n` 回答 | テーブル状態を表示して終了、**データは変更されない** |
| IT-M-11 | 既存テーブルあり + `y` 回答 | `drop_all` → `create_all` され、データが再構築される |
| IT-M-12 | `y/n` 以外の入力 | 「y か n を入力してください。」で再入力 |
| IT-M-13 | 2 回連続実行（`y`） | 結果が同一（冪等性） |
| IT-M-14 | 同名曲でパスが変わった場合 | `file_path` が更新され、行は増えない（`_upsert_track_by_wav`） |
| IT-M-15 | `sounds/user` が存在しない | エラーにならず空扱い（`_list_wav_files`） |
| IT-M-16 | wav 以外のファイルが混在 | 無視される |
| IT-M-17 | 大文字拡張子 `.WAV` | 登録対象になる（`suffix.lower()`） |
| IT-M-18 | ファイル一覧の順序 | ソート順で処理される |

---

## 6. システムテストケース

音声デバイスが利用可能な実環境で手動実施する。

| ID | 手順 | 期待結果 |
| --- | --- | --- |
| ST-01 | `uv sync` → `cp settings/sample_schedules.json settings/schedules.json` → `uv run python scripts/migrate_music_db.py` | セットアップがドキュメント通りに完了し、テーブル状態が表示される |
| ST-02 | `schedules.json` を現在時刻に合わせて編集し `uv run python src/main.py` | 実際に音が鳴る |
| ST-03 | `minute_settings` で `sound_file_name` を指定して実行 | 指定した曲が鳴る |
| ST-04 | `sound_types: ["NOTIFICATION"]` を指定して複数回実行 | `*notify` 系の曲が鳴り、実行ごとに曲が変わりうる |
| ST-05 | 非該当時刻で実行 | 何も鳴らず、正常終了する |
| ST-06 | cron に毎分登録して 1 時間放置 | 設定した時刻のみ鳴る |
| ST-07 | 音声デバイスが無い環境で実行 | `sounddevice` 由来のエラー内容を確認（現状は未ハンドリング） |
| ST-08 | `settings/schedules.json` を削除して実行 | `FileNotFoundError` で異常終了する（課題 6.3） |

---

## 7. 回帰テスト（既知の修正に紐づくもの）

| ID | 元コミット | 内容 | 期待結果 |
| --- | --- | --- | --- |
| RT-01 | `f941307` | スケジュール設定はあるが `minute_settings` が無い | 再生される（`{}` が返り、ALARM 既定で選曲） |

---

## 8. テスト対象外・前提

| 項目 | 理由 |
| --- | --- |
| `jpholiday` の祝日判定精度 | 外部ライブラリの責務 |
| `sounddevice` / PortAudio の実再生品質 | 環境依存。ST でのみ手動確認 |
| `src/schedules_models.py` の内容 | `datamodel-codegen` の生成物。生成が再現できることのみ確認（`./scripts/generate_model` 実行後に差分が出ないこと） |
| SQLAlchemy 自体の動作 | ライブラリの責務。ただし本システムが定義した制約・カスケードは UT-D-* で検証する |
| 並行実行時の DB ロック | 現状ワンショット実行で並行性が無いため対象外。cron の多重起動が想定されるようになったら追加すること |

---

## 9. 実行方法（テスト導入後）

```bash
# 全テスト
uv run pytest

# カバレッジ付き
uv run pytest --cov=src --cov-report=term-missing

# 単体のみ
uv run pytest tests/unit

# Lint / 型検査
uv run ruff check .
uv run mypy src   # ※ mypy.ini の修正が前提（課題 6.5）
```

---

## 10. 課題対応との対応表

概要設計書 6 章の既知課題と、それを検知・固定するテストケースの対応。

| 課題 | 関連テスト | 備考 |
| --- | --- | --- |
| 6.1 スキーマ検証なし | UT-L-01〜03 | 検証を導入する場合はテストの期待値変更が必要 |
| 6.2 `sound_file_name` 必須の矛盾 | UT-S-05, UT-S-06 | スキーマ修正時に `schema.json` のバリデーションテストを追加 |
| 6.3 設定ファイル不在 | UT-L-04, ST-08 | 現仕様を固定。改善時は期待値を変更 |
| 6.4 `exclude_track_names` 未使用 | UT-D-17, UT-D-18 | API 自体の正しさは担保済み |
| 6.5 mypy 設定不整合 | — | 9章の `mypy` コマンドが通ることをもって確認 |
| 6.6 ログが print のみ | — | ログ基盤導入時にテスト追加 |
| 6.7 テスト未導入 | 本書全体 | |
| 6.8 相対パス依存 | IT-10 | |
