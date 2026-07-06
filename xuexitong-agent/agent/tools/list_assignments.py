"""工具：list_assignments — 查看课程作业列表"""

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "list_assignments",
        "description": "获取指定课程的老师布置的日常作业列表（不是章节练习）",
        "parameters": {
            "type": "object",
            "properties": {
                "course_name": {
                    "type": "string",
                    "description": "课程名称关键词",
                },
            },
            "required": ["course_name"],
        },
    },
}


async def execute(driver, page, args, memory) -> str:
    """执行查看作业列表"""
    from homework.fetch import HomeworkFetcher

    course_name = args.get("course_name", "")
    if not course_name:
        return "缺少课程名称参数"

    fetcher = HomeworkFetcher(driver, use_ocr=True)

    # 查找课程
    from video.player import VideoPlayer
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
        return f"未找到包含「{course_name}」的课程。"

    assignments = await fetcher.get_assignments(course["url"])
    if not assignments:
        return f"「{course['name']}」没有作业。"

    lines = []
    for i, a in enumerate(assignments):
        status = "已完成" if a["done"] else "未完成"
        lines.append(f"{i+1}. [{status}] {a['title']}")

    result = f"「{course['name']}」共 {len(assignments)} 个作业：\n" + "\n".join(lines)
    memory.record_tool_execution("list_assignments", course["name"], result)
    return result
