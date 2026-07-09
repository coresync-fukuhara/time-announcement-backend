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

main() {
    install_system_packages
    setup_python
    configure_git
    claude_ownership
}

main "$@"
