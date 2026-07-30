# Docker化 方式調査（キャッチアップ資料） — タイムアナウンスメント

| 項目 | 内容 |
| --- | --- |
| 対象システム | タイムアナウンスメント (time-announcement-backend) |
| 目的 | 現行の cron 運用を Docker 化するにあたって存在する方式を洗い出し、判断材料として整理する |
| 関連文書 | [概要設計書](../design_overview.md) |
| 作成日 | 2026-07-30 |
| 位置づけ | **調査資料**。特定方式の採用を決定するものではない。実装前のキャッチアップ用 |

---

## 1. 前提の整理（現状の実行方式）

[概要設計書](../design_overview.md) の通り、本システムは以下の特性を持つ。Docker化はこの特性を変えるものではなく、「誰が・どうやってこの特性を包むか」を変える作業になる。

- **ワンショット実行**。`main.py` は常駐せず、呼ばれた瞬間の時刻判定→（該当すれば）再生→終了。
- **毎分の起動は外部委譲**（現状は cron）。
- **音声出力が必須**（`sounddevice` / PortAudio 経由）。コンテナは既定でホストのサウンドデバイスに触れないため、ここが最大の論点になる。
- **状態を持つファイルが3種**: `db/music.sqlite3`（+ 稼働状況によっては `-shm`/`-wal`）、`settings/schedules.json`（`.gitignore` 対象・環境ごとに手動配置）、`sounds/user/*.wav`（`.gitignore` 対象・環境ごとに追加）。`sounds/default/*.wav` はリポジトリ同梱。
- **対話式のセットアップスクリプト**（`scripts/migrate_music_db.py`）が存在し、`input()` に依存する。

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

**重要な未確定事項**: どの方式が適切かは**デプロイ先ホストのOS・構成に強く依存する**。
- Windows + WSL2 上で動かし続けるなら、devcontainer と同じ「PulseAudio ソケット共有（WSLg 経由）」がそのまま流用できる可能性が高い。
- 素の Linux 機（常時起動PCなど）に置くなら、ALSA 直渡しの方がシンプルで依存が少ない。
- Raspberry Pi 等の専用ハードウェアに置くなら、上記どちらも選択肢になるが検証が必要。

→ **デプロイ先が未確定なため、本章はあくまで選択肢の整理に留める。**

### 3.3 永続化データの扱い

| 対象 | 現状 | Docker化での扱い（案） |
| --- | --- | --- |
| `db/music.sqlite3`（+ `-shm`/`-wal`） | ローカルファイル、`.gitignore` 対象 | named volume または bind mount。イメージに焼き込まない |
| `settings/schedules.json` | `.gitignore` 対象、環境ごとに手動配置 | bind mount（設定ファイルなのでホストで編集したい） |
| `sounds/user/*.wav` | `.gitignore` 対象、環境ごとに追加 | bind mount |
| `sounds/default/*.wav` | リポジトリ同梱 | イメージに `COPY` で焼き込んで良い（bind mount でも可） |

### 3.4 イメージビルド（uv）

`uv` 公式ドキュメントが示す multi-stage パターンをベースに、本プロジェクトのネイティブ依存を踏まえて調整する必要がある。

```dockerfile
# builder stage（ビルド時のみ必要な依存を含む）
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config build-essential libgirepository1.0-dev portaudio19-dev
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-editable

# 最終stage（実行時のみ必要な最小構成）
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 libasound2 libpulse0   # ← 採用する音声方式に応じて絞る
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
CMD ["python", "src/main.py"]
```

ポイント:
- `build-essential` / `pkg-config` / `libgirepository1.0-dev` は**ビルド時のみ**（scipy/sounddevice のネイティブビルド用）。最終イメージに残す必要はない。
- 一方 `libportaudio2` は `sounddevice` が実行時に動的リンクするため**最終イメージにも必要**。ALSA/PulseAudio どちらを使うかで `libasound2` / `libpulse0` の要否が変わる（3.2 節に依存）。
- `--locked` で `uv.lock` との整合を強制、`--no-editable` でソース非依存の venv にして最終イメージへコピーする、という astral 公式推奨パターンに準拠。

### 3.5 対話式マイグレーションスクリプトの扱い

`scripts/migrate_music_db.py` は `input()` に依存する対話式で、スケジュール実行や `docker build` の中には組み込みにくい。

- 案: エントリポイント（毎分実行される方）には含めず、**環境構築時に一度だけ手動実行**する運用のまま据え置く。
  ```bash
  docker compose run --rm -it app uv run python scripts/migrate_music_db.py
  ```
- 非対話化（フラグでデフォルトタイプを指定する等）は別途アプリ側の改修が必要なため、本調査のスコープ外（概要設計書 6章の既知課題と合わせて別途検討）。

---

## 4. 組み合わせパターン（参考）

| パターン | スケジューリング | 音声 | 特徴 |
| --- | --- | --- | --- |
| ① 最小変更 | A. ホスト cron + `docker run --rm` | ALSA 直渡し | 現行運用に最も近い。Docker化の第一歩として着手しやすい |
| ② コンテナ内完結 | D. supercronic | PulseAudio ソケット共有（devcontainer と同じ方式） | devcontainer の音声設定資産を流用しやすい。WSL2運用なら一貫性が高い |
| ③ 疎結合・拡張志向 | E. ofelia | PulseAudio ソケット共有 | 将来他のジョブも増える想定なら候補。現状は過剰な可能性 |

---

## 5. 未確定・要確認事項（次のステップで詰める）

- **デプロイ先ホストの環境**（Windows+WSL2 / 素の Linux / Raspberry Pi 等）。音声方式の選定に直結するため最優先で確認したい。
- スケジューリングをコンテナに内蔵する（パターン②）か、引き続きホスト管理にする（パターン①）か。
- `scripts/migrate_music_db.py` を対話実行のまま使い続けるか、Docker運用に合わせて非対話フラグを追加するか。
- `settings/schedules.json` の実行時バリデーション欠如（概要設計書 6.1 / 6.3）は Docker化そのものとは独立した既知課題だが、無人運用（コンテナ化）を機に対応要否を再検討してもよい。

---

## 6. 参考リンク

- [astral-sh/uv-docker-example](https://github.com/astral-sh/uv-docker-example) / [Using uv in Docker（公式ガイド）](https://docs.astral.sh/uv/guides/integration/docker/)
- [aptible/supercronic](https://github.com/aptible/supercronic)
- [mcuadros/ofelia](https://github.com/mcuadros/ofelia)
- [How to Run Cron Jobs Inside Docker Containers](https://oneuptime.com/blog/post/2026-01-06-docker-cron-jobs/view)
- [x11docker wiki: Container sound: ALSA or Pulseaudio](https://github.com/mviereck/x11docker/wiki/Container-sound:-ALSA-or-Pulseaudio)
