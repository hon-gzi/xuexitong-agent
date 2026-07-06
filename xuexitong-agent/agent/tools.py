"""向后兼容 shim — 工具已从 agent/tools/ 目录自动注册。

保留此文件以兼容旧代码中的 `from agent.tools import TOOL_DEFINITIONS` 等导入。
"""

from agent.tools import TOOL_DEFINITIONS, EXECUTORS

__all__ = ["TOOL_DEFINITIONS", "EXECUTORS"]
