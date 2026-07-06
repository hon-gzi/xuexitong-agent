"""工具：list_courses — 获取课程列表"""

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "list_courses",
        "description": "获取用户的课程列表",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


async def execute(driver, page, args, memory) -> str:
    """执行获取课程列表"""
    from video.player import VideoPlayer

    player = VideoPlayer(driver)
    courses = await player.get_course_list()

    if not courses:
        return "未获取到课程列表，请确认已登录。"

    lines = [f"{i+1}. {c['name']}" for i, c in enumerate(courses)]
    result = f"共 {len(courses)} 门课程：\n" + "\n".join(lines)

    # 记录到情景记忆
    memory.record_tool_execution("list_courses", "", result)

    return result
