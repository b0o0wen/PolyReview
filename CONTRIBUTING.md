# Contributing

欢迎 PR —— 尤其是这两类：

## 1. 验证实验性 adapter（最高优先）

`gemini` / `qwen` / `aider` / `qoder` 的命令模板来自公开文档，未在真实安装上验证（opencode 语法已实测）。
你装了对应 CLI 的话，帮忙跑通并把结论发到 issue（或直接修 `registry.py` 提 PR）：

```bash
polyreview init --host <your-host> --reviewers <name>   # 装上
# 然后在该 host 会话里对任一 md 文件发起交叉评审，观察：
#   - 命令是否成功执行（否则贴出 CLI 的 headless 用法，我们改模板）
#   - identity() 是否能返回
```

验证通过后我们把该 adapter 移出 experimental（README 表格同步）。

## 2. 新 adapter

优先改配置而不是代码：`polyreview config add-reviewer <name> --new '...' [--resume '...' --session-regex '...']`。
如果你验证的模板值得内置进 `registry.py`，提交 PR 时请附上：
- CLI 版本与安装方式
- new/resume 命令模板
- 会话 id 在输出中的位置（stdout/stderr/JSON 字段）—— 参考 `docs/host-compat.md` 第 4 节

## 开发

```bash
pip install -e . && pip install pytest
python -m unittest discover -s tests    # 必须全过（零模型成本）
python -m polyreview demo               # 冒烟
```

设计决策（host 仲裁为主模式、rejected 清单等）见 [ROADMAP.md](ROADMAP.md) ——
改动方向与 Rejected 区冲突的 PR 请先开 issue 讨论。
