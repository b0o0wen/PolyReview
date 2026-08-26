#!/bin/sh
# PolyReview 一键安装：uv > pipx > pip 三级探测，装完提示下一步。
# 用法: curl -fsSL https://raw.githubusercontent.com/b0o0wen/PolyReview/main/install.sh | sh
set -e

say() { printf '\033[36m▸\033[0m %s\n' "$1"; }
err() { printf '\033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }

# 目标：git+ssh 对私有友好、https 对公众友好；本脚本用 https（public 仓库）
SRC="git+https://github.com/b0o0wen/PolyReview.git"

if command -v uv >/dev/null 2>&1; then
    say "检测到 uv —— uv tool install polyreview"
    uv tool install "$SRC" && BIN="uvx polyreview"
elif command -v pipx >/dev/null 2>&1; then
    say "检测到 pipx —— pipx install"
    pipx install "$SRC" && BIN="polyreview"
elif command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
    PIP=$(command -v pip3 || command -v pip)
    say "使用 $PIP install --user（建议改用 uv: https://docs.astral.sh/uv/）"
    "$PIP" install --user "$SRC" && BIN="polyreview"
else
    err "未找到 uv/pipx/pip。请先安装 uv:  curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

say "安装完成。下一步："
echo "  $BIN demo                 # 30 秒零成本试用（mock 评审团）"
echo "  $BIN scan               # 探测本机已装的评审员 CLI"
echo "  $BIN init --host claude   # 一键接入 host（qoder/claude/cursor/vscode）"
