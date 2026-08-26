"""PolyReview: multi-agent cross-review panel for specs & code.

让任意 CLI agent（claude/codex/gemini/qwen/kimi/opencode...）互相评审你的方案与代码。
评审员 = agent（不选模型，模型由各 CLI 自身配置决定）。
"""

__version__ = "0.1.0"

from .adapter import Adapter  # noqa: F401
from .registry import REGISTRY, get_adapter  # noqa: F401
