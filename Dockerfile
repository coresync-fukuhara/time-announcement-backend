# builder stage（ビルド時の追加パッケージは不要 — 全依存が prebuilt wheel のため）
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY . /app
# settings/schedules.json は .gitignore 対象で通常イメージに含まれない。
# 無い場合はサンプルをコピーして焼き込むことで、初回 `docker compose up` 時に
# 空の named volume へサンプル設定が自動コピーされ、そのまま起動できるようにする。
RUN test -f settings/schedules.json || cp settings/sample_schedules.json settings/schedules.json
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

# supercronic 取得用ステージ（最終イメージに curl を残さないよう分離）
FROM debian:bookworm-slim AS supercronic
ARG SUPERCRONIC_VERSION=v0.2.48
ARG SUPERCRONIC_SHA1SUM=016b7c9aebfc8d9fd9526e8ba33b191fc524485f
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSLo /supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    && echo "${SUPERCRONIC_SHA1SUM}  /supercronic" | sha1sum -c - \
    && chmod +x /supercronic

# 最終stage（実行時に必要な音声ライブラリのみ）
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 libasound2 libasound2-plugins libpulse0 \
    && rm -rf /var/lib/apt/lists/*
# ALSA の既定出力を PulseAudio へ向ける（PortAudio は Linux では ALSA 経由でしか出力できないため）
RUN printf 'pcm.!default { type pulse }\nctl.!default { type pulse }\n' > /etc/asound.conf

COPY --from=supercronic /supercronic /usr/local/bin/supercronic
COPY --from=builder /bin/uv /bin/uv
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app
COPY crontab /app/crontab
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# 毎分の起動は supercronic が PID 1 として担う（SIGTERM を正しくハンドリングし、
# ジョブの stdout/stderr を自身の stdout/stderr に転送するため `docker logs` で追える）
CMD ["supercronic", "/app/crontab"]
