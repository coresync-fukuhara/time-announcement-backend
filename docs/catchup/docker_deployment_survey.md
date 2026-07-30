# Docker化 方式調査（キャッチアップ資料） — タイムアナウンスメント

| 項目 | 内容 |
| --- | --- |
| 対象システム | タイムアナウンスメント (time-announcement-backend) |
| 目的 | 現行の cron 運用を Docker 化するにあたって存在する方式を洗い出し、判断材料として整理する |
| 関連文書 | [概要設計書](../design_overview.md) |
| 作成日 | 2026-07-30 |
| 位置づけ | 調査資料 兼 決定事項ログ。選定が固まった項目は0章に追記し、未定の項目は5章に残す |

---

## 0. 決定事項

| 項目 | 決定 | 根拠 | 決定日 |
| --- | --- | --- | --- |
| スケジューリング方式（3.1） | **D. supercronic**（コンテナ内蔵） | 要件「`docker compose up` 一発でデプロイ完結」を満たすのは D/E のみ（A/B/C はホスト側 cron/systemd の別設定が必要なため除外）。D と E を比べると、E は `docker-compose.yml` に ofelia サービスを追加し `/var/run/docker.sock` を渡す必要がある（実質 root 相当の権限）一方、本システムはスケジュールするジョブが1つだけで ofelia の疎結合という強みがほぼ活きない。実装コスト・セキュリティ面ともに D が優位と判断した | 2026-07-30 |
| デプロイ先ホスト環境 | **Ubuntu**（素の Linux。WSL2 ではない） | 本番ホストとして確定。ただし「他プロセスも音を鳴らす可能性がある」という制約があるため、3.2 の音声方式選定に直結する | 2026-07-30 |
| 音声出力方式（3.2） | **PulseAudio ソケット共有**（ホストの PulseAudio／PipeWire-pulse ソケットを bind mount） | ALSA デバイス直渡しは単一プロセス専有が前提で、他プロセスと同時に音を鳴らすと競合する。今回は「他プロセスも音を鳴らす可能性がある」ため不適合。PulseAudio ソケット共有は複数プロセスの同時再生に対応でき、devcontainer（WSLg 経由）で実績もある方式のため採用。**要確認**: 対象 Ubuntu ホストが素の PulseAudio か PipeWire-pulse かで bind mount するソケットパスが変わる（実装時に `pactl info` 等でホストを確認する） | 2026-07-30 |
| 永続化データの方式（3.3） | **全て named volume 化**（`db/music.sqlite3`、`settings/schedules.json`、`sounds/user/`） | 別リポジトリの**フロントエンド（スケジュール編集・楽曲追加UI）が同じボリュームをマウントして書き込む**運用のため、単純な bind mount（ホスト直編集前提）ではなく、複数コンテナ間の共有ストレージに適した named volume を採用。`sounds/default/*.wav` はリポジトリ同梱で実行時に変化しないため volume 化せず `COPY` で焼き込む | 2026-07-30 |
| Volume名（3.3） | `time-announcement-db` / `time-announcement-settings` / `time-announcement-sounds-user`（`external: true`） | 本リポジトリ側で固定名を先に決め、フロントエンド側がそれに合わせる運用で合意 | 2026-07-30 |
| イメージビルド（3.4） | builder stage は追加 apt パッケージ**不要**／最終stage は `libportaudio2 libasound2 libasound2-plugins libpulse0` のみ | devcontainer の `.venv` を実査したところ、本プロジェクトの全依存が prebuilt wheel でソースビルドが発生しないことを確認。PortAudio は Linux では ALSA 経由でしか出力できないため、PulseAudio ソケット共有（3.2）を選んでいても ALSA→PulseAudio ブリッジ（`libasound2-plugins`）が必要 | 2026-07-30 |
| マイグレーションスクリプトの扱い（3.5） | **現状の対話式 (`input()`) のまま**。エントリポイントには含めず、環境構築時に `docker compose run --rm -it app uv run python scripts/migrate_music_db.py` で手動実行する運用を継続 | 非対話化にはアプリ側の改修が必要で今回のDocker化のスコープを超えるため、既存の運用を素直にコンテナに持ち込む方針とした | 2026-07-30 |

これで 3.1〜3.5 すべて決定済み。次は実装（Dockerfile / docker-compose.yml / crontab）フェーズ。

---

## 1. 前提の整理（現状の実行方式）

[概要設計書](../design_overview.md) の通り、本システムは以下の特性を持つ。Docker化はこの特性を変えるものではなく、「誰が・どうやってこの特性を包むか」を変える作業になる。

- **ワンショット実行**。`main.py` は常駐せず、呼ばれた瞬間の時刻判定→（該当すれば）再生→終了。
- **毎分の起動は外部委譲**（現状は cron）。
- **音声出力が必須**（`sounddevice` / PortAudio 経由）。コンテナは既定でホストのサウンドデバイスに触れないため、ここが最大の論点になる。
- **状態を持つファイルが3種**: `db/music.sqlite3`（+ 稼働状況によっては `-shm`/`-wal`）、`settings/schedules.json`（`.gitignore` 対象・環境ごとに手動配置）、`sounds/user/*.wav`（`.gitignore` 対象・環境ごとに追加）。`sounds/default/*.wav` はリポジトリ同梱。
- **対話式のセットアップスクリプト**（`scripts/migrate_music_db.py`）が存在し、`input()` に依存する。
- **別リポジトリのフロントエンド**（スケジュール編集・楽曲追加 UI、本リポジトリには含まれない）が存在し、上記の状態ファイル（特に `settings/schedules.json` と `sounds/user/`、おそらく `db/music.sqlite3` も）を**同じボリューム越しに書き込む**運用を想定している。したがって永続化データの設計は「このコンテナ単体でどう持つか」ではなく「フロントエンドと共有できる形でどう持つか」で考える必要がある（→ 3.3）。

なお、本リポジトリには過去に **開発コンテナ用**の `.devcontainer/Dockerfile` / `.devcontainer/docker-compose.yaml` が存在した（コミット `efbbd26` で devcontainer features 方式に置き換えて削除済み。`git show efbbd26^:.devcontainer/Dockerfile` 等で参照可能）。中身は以下で、音声を **PulseAudio ソケット共有**（WSLg 経由）で通していた。これは「開発環境」向けであり「デプロイ」向けではないが、音声を Docker に通す実績あるパターンとして参考になる。

```dockerfile
# (削除済み) .devcontainer/Dockerfile
FROM python:3.13
RUN pip install --upgrade pip setuptools wheel uv
RUN apt update
RUN apt install -y pkg-config python3-dev build-essential libgirepository1.0-dev portaudio19-dev pulseaudio
WORKDIR /app
```

```yaml
# (削除済み) .devcontainer/docker-compose.yaml
services:
  app:
    build: { context: ., dockerfile: Dockerfile }
    volumes:
      - ../:/app
      - /mnt/wslg:/mnt/wslg
    environment:
      - PULSE_SERVER=/mnt/wslg/PulseServer
    command: sleep infinity
```

---

## 2. Docker化で新たに生じる論点

| # | 論点 | 概要 |
| --- | --- | --- |
| 2.1 | スケジューリングの実行主体 | 毎分起動を誰が担うか（cron はコンテナに標準で無い） |
| 2.2 | 音声デバイスへのアクセス | コンテナからホストのスピーカーへどう出力するか |
| 2.3 | 永続化データの扱い | DB・ユーザー設定・ユーザー音源をイメージ再ビルドで消さない |
| 2.4 | イメージビルド（uv） | ネイティブ依存（scipy/sounddevice）のビルド・実行時ライブラリ |
| 2.5 | 対話式マイグレーションの扱い | `input()` 依存のスクリプトを Docker運用にどう乗せるか |

---

## 3. 各論点の選択肢

### 3.1 スケジューリング方式

いずれの方式でも `main.py` 自体（ワンショット・無ループ）は変更不要。「毎分呼び出す主体」だけが変わる。

| 方式 | 概要 | メリット | デメリット |
| --- | --- | --- | --- |
| A. ホスト cron + `docker run --rm` | 既存 crontab の実行コマンドを `uv run python src/main.py` → `docker run --rm ...` に差し替えるだけ | 変更が最小。現行運用の構造をそのまま維持 | 毎分コンテナ起動のオーバーヘッド。ホスト側の cron 管理は残る |
| B. ホスト cron + `docker exec`（常駐コンテナへ） | アプリを `sleep infinity` 等で常駐させ、ホスト cron から `docker exec` | 起動オーバーヘッドが無い | コンテナが落ちるとジョブごと失敗。名前変更に弱い |
| C. systemd timer + `docker run` | cron の代わりに systemd timer から起動 | ログ・再試行・依存関係の管理が systemd に統合される | Linux ホスト前提。学習コストがやや上がる |
| D. supercronic（コンテナ内蔵） | crontab 互換のスケジューラをコンテナの PID 1 として常駐させ、内部で `python src/main.py` を毎分実行 | シグナルハンドリングが適切（`docker stop` で正常終了）。環境変数を保持したまま実行。ログが `stdout`/`stderr` に出て `docker logs` で追える。バイナリ1つ（~5MB）で依存なし | スケジューラとアプリが同一コンテナに同居する（役割は分離されているが1プロセスグループ） |
| E. ofelia（外部スケジューラコンテナ） | 別コンテナが Docker API 経由で対象コンテナにジョブを注入（`job-run`/`job-exec`） | スケジュール定義がアプリイメージから完全分離。複数コンテナ・複数ジョブを一元管理しやすい | Docker socket をスケジューラに渡す必要がありセキュリティ考慮が増える。本プロジェクト規模には過剰気味 |
| F. Kubernetes CronJob | k8s クラスタのネイティブ機能でワンショット Pod を毎分起動 | 複数ホスト運用・監視基盤との統合に強い | 単一ホストの個人プロジェクトには明らかにオーバースペック |

> 素の cron（vixie-cron 等）をそのままコンテナの PID 1 にする方式は今回の候補から除外した。環境変数が引き継がれない・シグナルハンドリングが弱い・ログが `syslog` 前提で `docker logs` に出ないという問題が知られており、D（supercronic）がその代替として設計されている。

### 3.2 音声出力へのアクセス

| 方式 | 概要 | 必要なもの | 特徴 |
| --- | --- | --- | --- |
| ALSA デバイス直渡し | `docker run --device /dev/snd ...` | ホスト側は素の ALSA でOK。コンテナに `libasound2` | 最もシンプル。ただし**同時に複数プロセスがデバイスを使うと競合**しやすい。非root実行には `--group-add=audio` |
| PulseAudio ソケット共有 | ホストの PulseAudio ソケットをコンテナにマウントし `PULSE_SERVER` で指定 | ホスト・コンテナ双方に `libpulse0`。UID/GID をホストユーザーに合わせる必要あり | 複数プロセスの同時再生に強い。**このプロジェクトの devcontainer が WSLg 経由で既に採用しているパターン**（`PULSE_SERVER=/mnt/wslg/PulseServer` の bind mount） |
| PulseAudio TCP | `module-native-protocol-tcp` をロードしてネットワーク越しに接続 | ポート開放・簡易認証（IP ACL） | コンテナ起動後にモジュールロードが要るためタイミング調整が必要。あまり推奨されない |
| PipeWire ソケット共有 | `$XDG_RUNTIME_DIR/pipewire-0` 等を bind mount | 比較的新しいディストリで pulseaudio の代わりに主流 | 現代的だが本プロジェクトの開発環境（WSLg）は pulse 系のため今は優先度低 |

**決定（0章参照）**: デプロイ先は Ubuntu（素の Linux）で確定。「他プロセスも音を鳴らす可能性がある」制約により、単一プロセス専有前提の ALSA 直渡しは不採用とし、**PulseAudio ソケット共有**を採用する。

- devcontainer は WSLg 経由の PulseAudio ソケット共有（`PULSE_SERVER=/mnt/wslg/PulseServer`）だったが、本番の Ubuntu ホストでは WSLg は無いため `/mnt/wslg` 経由ではなく、ホスト側の PulseAudio（または PipeWire-pulse）ソケット（例: `$XDG_RUNTIME_DIR/pulse/native` 相当）を直接 bind mount する形になる。ソケット共有という**方式**は同じでも、**パス**は環境依存のため実装時に対象ホストで確認が必要。
- UID/GID をホストのオーディオ実行ユーザーに合わせる必要がある点は変わらず留意（3.2 冒頭の比較表参照）。

### 3.3 永続化データの扱い

**決定（0章参照）**: `db/music.sqlite3`・`settings/schedules.json`・`sounds/user/` は**すべて named volume 化**する。bind mount ではなく named volume を選んだ理由は、**別リポジトリのフロントエンド（スケジュール編集・楽曲追加UI）が同じデータへ書き込むため**——複数コンテナ間の共有ストレージという、named volume が本来得意とするユースケースに合致するため。

| 対象 | 現状 | Docker化での扱い |
| --- | --- | --- |
| `db/music.sqlite3`（+ `-shm`/`-wal`） | ローカルファイル、`.gitignore` 対象 | named volume。イメージには焼き込まない。フロントエンド／マイグレーションスクリプト双方から書き込まれる想定 |
| `settings/schedules.json` | `.gitignore` 対象、環境ごとに手動配置 | named volume。`settings/sample_schedules.json` をイメージに `COPY` しておけば、Docker の「ボリュームが空の場合はイメージの中身を初回コピーする」仕様により `docker compose up` 一発でサンプル設定のまま起動できる。実運用の編集はフロントエンド経由 |
| `sounds/user/*.wav` | `.gitignore` 対象、環境ごとに追加 | named volume。フロントエンドの楽曲追加機能が書き込む前提 |
| `sounds/default/*.wav` | リポジトリ同梱 | volume 化しない。実行時に変化しないため `COPY` でイメージに焼き込む |

**Volume名（決定）**: 本リポジトリ側で固定名を決め、フロントエンド側がそれに合わせる運用となった。`external: true` を付けて Compose のプロジェクト名前空間から独立させる。

| named volume 名 | マウント先 |
| --- | --- |
| `time-announcement-db` | `/app/db` |
| `time-announcement-settings` | `/app/settings` |
| `time-announcement-sounds-user` | `/app/sounds/user` |

**残る注意点**:
- 複数コンテナが同一 SQLite ファイルへ同時に書き込む可能性がある場合、SQLite のロック挙動（特に WAL モード時の `-shm`/`-wal`）を踏まえた検証が必要。現状 `main.py` 側は WAL モードを明示していない（[music_db.py](../../src/music_db.py) は `PRAGMA foreign_keys=ON` のみ設定）ため、フロントエンド側の書き込み方式次第では追加確認が要る（5章に残置）。
- `scripts/migrate_music_db.py` の対話式実行（3.5）は、named volume 化後も変わらず `docker compose run --rm -it app ...` の形で行う想定。

### 3.4 イメージビルド（uv）

`uv` 公式ドキュメントが示す multi-stage パターンをベースに、本プロジェクトのネイティブ依存を踏まえて調整する。

**検証済みの事実（決定の根拠）**: devcontainer の `.venv` を実際に調べたところ、本プロジェクトの依存（`scipy` / `sounddevice` / `sqlalchemy` / `jpholiday` / `datamodel-code-generator`）は**すべて prebuilt wheel（manylinux または pure Python）でインストールされており、ソースビルドは一切発生していない**（各パッケージの `WHEEL` メタデータで `Tag: cp313-...-manylinux_*` または `Tag: py3-none-any` を確認済み）。特に `sounddevice` は ctypes ベースの薄いラッパーで、C拡張のコンパイルは行わずシステムの `libportaudio2` を実行時に動的ロードするだけ。

→ **builder stage は `build-essential` / `pkg-config` / `libgirepository1.0-dev` / `portaudio19-dev` のインストールが不要**（devcontainer の `post-create.sh` にはこれらがあるが、`libgirepository1.0-dev`（PyGObject向け）は `pyproject.toml` のどの依存にも対応しておらず、開発コンテナ側の構成そのものが別プロジェクトからの持ち越しの可能性がある。今回の Docker化の対象外なので深追いはしないが、イメージには持ち込まない）。

**最終stage の音声パッケージ（3.2 の決定を反映）**: PortAudio の Linux 側実装は ALSA ベースで、PulseAudio 専用の host API は無い。そのため PulseAudio ソケット共有を選んでいても、実際には **ALSA → PulseAudio 変換プラグイン（`libasound2-plugins`）を経由**する構成になる。「ALSA か PulseAudio か」の二択ではなく、両方が必要。

```dockerfile
# builder stage（ビルド時の追加パッケージは不要 — 全依存が prebuilt wheel のため）
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

# 最終stage（実行時に必要な音声ライブラリのみ）
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 libasound2 libasound2-plugins libpulse0 \
    && rm -rf /var/lib/apt/lists/*
# ALSA の既定出力を PulseAudio へ向ける（PortAudio は ALSA 経由でしか出力できないため）
RUN printf 'pcm.!default { type pulse }\nctl.!default { type pulse }\n' > /etc/asound.conf
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
CMD ["python", "src/main.py"]
```

ポイント（更新後）:
- `uv sync` に **`--no-dev`** を追加し、`ruff`（開発用 lint ツール）を本番イメージから除外する。
- builder stage・最終stage ともに `apt-get install` は音声ライブラリ以外は不要。イメージが小さく・攻撃対象も減る。
- `libasound2-plugins` が ALSA→PulseAudio ブリッジ本体、`/etc/asound.conf` の `pcm.!default`/`ctl.!default` を `pulse` に向けることで `sounddevice` がデフォルトデバイス経由で自動的に PulseAudio ソケットへ出力される。
- `--locked` で `uv.lock` との整合を強制、`--no-editable` でソース非依存の venv にして最終イメージへコピーする、という astral 公式推奨パターンに準拠。

### 3.5 対話式マイグレーションスクリプトの扱い

`scripts/migrate_music_db.py` は `input()` に依存する対話式で、スケジュール実行や `docker build` の中には組み込みにくい。

**決定（0章参照）**: エントリポイント（毎分実行される方）には含めず、**環境構築時に一度だけ手動実行**する運用のまま据え置く。
```bash
docker compose run --rm -it app uv run python scripts/migrate_music_db.py
```
非対話化（フラグでデフォルトタイプを指定する等）は別途アプリ側の改修が必要なため、今回のDocker化のスコープ外とする（概要設計書 6章の既知課題と合わせて別途検討）。

---

## 4. 組み合わせパターン（参考）

| パターン | スケジューリング | 音声 | 特徴 |
| --- | --- | --- | --- |
| ① 最小変更 | A. ホスト cron + `docker run --rm` | ALSA 直渡し | 現行運用に最も近い。`docker compose up` 一発完結の要件を満たさないため不採用 |
| ② コンテナ内完結（**採用方針**） | **D. supercronic**（0章で決定） | **PulseAudio ソケット共有**（0章で決定） | devcontainer の音声設定資産（方式）を流用しつつ、Ubuntu本番ホスト向けにソケットパスを読み替える。複数プロセス同時再生にも対応 |
| ③ 疎結合・拡張志向 | E. ofelia | PulseAudio ソケット共有 | 将来他のジョブも増える想定なら候補。現状は過剰と判断し不採用 |

---

## 5. 未確定・要確認事項（次のステップで詰める）

- **対象 Ubuntu ホストのサウンドサーバー種別**（素の PulseAudio か PipeWire-pulse か）と、bind mount すべきソケットの実パス。実装時に対象ホストで `pactl info` 等を実行して確認する。
- `settings/schedules.json` の実行時バリデーション欠如（概要設計書 6.1 / 6.3）は Docker化そのものとは独立した既知課題だが、無人運用（コンテナ化）を機に対応要否を再検討してもよい。
- **SQLite への複数プロセス同時書き込みの安全性確認**。フロントエンド（楽曲追加・スケジュール編集）と本バックエンド（読み取り中心、`migrate_music_db.py` 実行時のみ書き込み）が同じ `db/music.sqlite3` を named volume 経由で共有するため、書き込みタイミングが重なった場合の挙動（ロック・WALモードの要否）をフロントエンド側の実装と合わせて確認する。

---

## 6. 参考リンク

- [astral-sh/uv-docker-example](https://github.com/astral-sh/uv-docker-example) / [Using uv in Docker（公式ガイド）](https://docs.astral.sh/uv/guides/integration/docker/)
- [aptible/supercronic](https://github.com/aptible/supercronic)
- [mcuadros/ofelia](https://github.com/mcuadros/ofelia)
- [How to Run Cron Jobs Inside Docker Containers](https://oneuptime.com/blog/post/2026-01-06-docker-cron-jobs/view)
- [x11docker wiki: Container sound: ALSA or Pulseaudio](https://github.com/mviereck/x11docker/wiki/Container-sound:-ALSA-or-Pulseaudio)
- [joonas.fi: Audio in Docker containers, Linux audio subsystems, Spotifyd](https://joonas.fi/2020/12/audio-in-docker-containers-linux-audio-subsystems-spotifyd/)（`libasound2-plugins` による ALSA→PulseAudio ブリッジの設定例）
- [PortAudio Linux ホスト API についての議論（portaudio ML アーカイブ）](https://portaudio.music.columbia.narkive.com/doCvUSqY/pulseaudio-vs)（PortAudio が Linux では ALSA 経由でしか出力しない点の根拠）
