"""工具自动注册中心。

扫描 agent/tools/ 目录下所有 .py 文件（除 __init__.py），
动态导入每个工具的 TOOL_DEF 和 execute 函数，
聚合为 TOOL_DEFINITIONS 列表和 EXECUTORS 字典。
"""

import importlib
from pathlib import Path
from typing import Any

# 工具目录
_TOOLS_DIR = Path(__file__).parent


def _discover_tools() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """扫描 tools/ 目录，发现所有工具模块。"""
    tool_defs = []
    executors = {}

    for py_file in sorted(_TOOLS_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        module_name = py_file.stem
        module = importlib.import_module(f"agent.tools.{module_name}")

        if hasattr(module, "TOOL_DEF"):
            tool_defs.append(module.TOOL_DEF)
        if hasattr(module, "execute"):
            executors[module_name] = module.execute

    return tool_defs, executors


# 模块级初始化：启动时自动发现所有工具
TOOL_DEFINITIONS, EXECUTORS = _discover_tools()

__all__ = ["TOOL_DEFINITIONS", "EXECUTORS"]
