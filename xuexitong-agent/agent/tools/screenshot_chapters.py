"""工具：screenshot_chapters — 截图课程章节列表"""

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "screenshot_chapters",
        "description": "截图课程的章节列表（含完成状态标记），返回截图路径。用于在刷课前识别哪些章节未完成。",
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
    """执行截图章节列表"""
    from video.player import VideoPlayer

    course_name = args.get("course_name", "")
    if not course_name:
        return "缺少课程名称参数"

    # 先获取课程列表找到对应课程
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

    path = await player.screenshot_chapter_list(course["url"])
    result = (
        f"课程「{course['name']}」的章节列表截图已保存到: {path}\n"
        "请用Read工具查看截图，识别哪些章节没有绿色勾选标记（未完成），"
        "然后调用watch_course并传入这些章节的序号。"
    )

    memory.record_tool_execution("screenshot_chapters", course["name"], result)
    return result
