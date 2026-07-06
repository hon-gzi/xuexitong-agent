"""工具：watch_course — 刷课程视频"""

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "watch_course",
        "description": "刷指定课程的视频。可指定只刷特定章节（通过章节序号列表）。",
        "parameters": {
            "type": "object",
            "properties": {
                "course_name": {
                    "type": "string",
                    "description": "课程名称关键词",
                },
                "chapters": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "要刷的章节序号列表（从0开始）。不填则刷所有章节。",
                },
                "speed": {
                    "type": "number",
                    "description": "播放倍速，默认2.0",
                },
            },
            "required": ["course_name"],
        },
    },
}


async def execute(driver, page, args, memory) -> str:
    """执行刷课"""
    from video.player import VideoPlayer

    course_name = args.get("course_name", "")
    speed = args.get("speed", 2.0)
    chapters_filter = args.get("chapters")

    if not course_name:
        return "缺少课程名称参数"

    player = VideoPlayer(driver)
    courses = await player.get_course_list()
    course = None
    for c in courses:
        if course_name in c["name"]:
            course = c
            break
    if not course:
        for c in courses:
            if course_name.replace(" ", "") in c["name"].replace(" ", ""):
                course = c
                break

    if not course:
        return f"未找到包含「{course_name}」的课程，请检查名称或先用 list_courses 查看课程列表。"

    result = await player.batch_watch(course["url"], speed, chapters_filter)

    reply = (
        f"刷课完成！\n"
        f"课程：{course['name']}\n"
        f"进度：{result['completed']}/{result['total']} 个视频已完成\n"
        f"跳过：{result['skipped']}，失败：{result['failed']}"
    )

    memory.record_tool_execution("watch_course", course["name"], reply)
    return reply
