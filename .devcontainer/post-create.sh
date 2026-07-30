#!/usr/bin/env bash
set -euo pipefail

# システムライブラリの導入（PyGObject / PyAudio のネイティブビルド・音声再生に必要）
install_system_packages() {
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends \
        pkg-config \
        build-essential \
        libgirepository1.0-dev \
        portaudio19-dev \
        pulseaudio
}

# Python 環境と依存関係のセットアップ
setup_python() {
    pip install --upgrade pip setuptools wheel uv
    uv sync
}

# Git の設定
configure_git() {
    git config --global --add safe.directory /app
}

# .claude の所有者を変更する (root でマウントされるため)
claude_ownership() {
    sudo chown -R vscode:vscode ~/.claude
}

# APM (Agent Package Manager, microsoft/apm) を導入する
setup_apm() {
    curl -sSL https://aka.ms/apm-unix | sh
    # apm.yml がまだ無い段階でも失敗しない (setup_node の package.json チェックと同じパターン)
    if [ -f apm.yml ]; then
        # .claude/ は空ディレクトリのため git 経由では復元されない。
        # 無い状態で apm install が Claude Code 向け設定の書き込みをスキップするため先に作る
        mkdir -p .claude
        if [ -f apm.lock.yaml ]; then
            apm install --frozen
        else
            apm install
        fi
    fi
}

main() {
    install_system_packages
    setup_python
    configure_git
    claude_ownership
    setup_apm
}

main "$@"
