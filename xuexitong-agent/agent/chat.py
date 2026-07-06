"""ReAct Agent — 向后兼容层。

新版 Agent 请使用 agent.core.AgentCore。
"""

from agent.tools import TOOL_DEFINITIONS


class ReActAgent:
    """已弃用：请使用 AgentCore。"""

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("ReActAgent is deprecated. Use AgentCore instead.")
