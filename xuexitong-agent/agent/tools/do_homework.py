"""工具：do_homework — 自动完成老师布置的日常作业"""

import asyncio
import json

from llm.client import llm


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "do_homework",
        "description": "自动完成老师布置的日常作业（不是章节练习）：获取题目、AI答题、自动提交",
        "parameters": {
            "type": "object",
            "properties": {
                "course_name": {
                    "type": "string",
                    "description": "课程名称关键词",
                },
                "assignment_title": {
                    "type": "string",
                    "description": "作业标题关键词（可选，不填则完成所有未完成的作业）",
                },
            },
            "required": ["course_name"],
        },
    },
}


async def execute(driver, page, args, memory) -> str:
    """执行自动做作业"""
    from homework.fetch import HomeworkFetcher
    from homework.submit import HomeworkSubmitter
    from video.player import VideoPlayer
    from browser.driver import CHAOXING_URL

    course_name = args.get("course_name", "")
    assignment_title = args.get("assignment_title")

    if not course_name:
        return "缺少课程名称参数"

    # 查找课程
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

    fetcher = HomeworkFetcher(driver, use_ocr=True)
    submitter = HomeworkSubmitter(driver)

    assignments = await fetcher.get_assignments(course["url"])
    if not assignments:
        return f"「{course['name']}」没有作业。"

    todo = [a for a in assignments if not a["done"]]
    if not todo:
        return f"「{course['name']}」的所有作业都已完成！"

    targets = todo
    if assignment_title:
        targets = [a for a in todo if assignment_title in a["title"]]
        if not targets:
            return f"未找到包含「{assignment_title}」的未完成作业。可用的未完成作业：\n" + "\n".join(
                [f"- {a['title']}" for a in todo]
            )

    results = []
    for assignment in targets:
        hw = await fetcher.open_assignment(assignment["url"], assignment["title"])
        questions = hw.get("questions", [])

        # DOM 解析失败或数量不对 → OCR 兜底
        if not questions and fetcher._ocr:
            print(f"[作业] {assignment['title']}: DOM解析失败，切换OCR...")
            url = assignment.get("url", "")

            if not url:
                try:
                    await driver.page.goto(course["url"], wait_until="domcontentloaded")
                    await driver.random_delay(3, 5)
                    await driver.page.evaluate("""() => {
                        const els = document.querySelectorAll('li, a, span, div');
                        for (const el of els) {
                            if (el.innerText.trim() === '作业' && el.offsetParent !== null) { el.click(); return; }
                        }
                    }""")
                    await driver.random_delay(3, 5)
                except Exception:
                    pass
                for frame in driver.page.frames:
                    try:
                        url = await frame.evaluate("""(title) => {
                            const lis = document.querySelectorAll('li[onclick*="goTask"]');
                            for (const li of lis) {
                                if ((li.innerText||'').includes(title)) return li.getAttribute('data') || '';
                            }
                            return '';
                        }""", assignment["title"])
                        if url:
                            break
                    except Exception:
                        continue

            if url:
                if url.startswith("/"):
                    url = f"{CHAOXING_URL}{url}"
                await driver.page.goto(url, wait_until="domcontentloaded")
                await driver.random_delay(3, 5)

            for f in driver.page.frames:
                try:
                    has_q = await f.evaluate("""() => {
                        const selectors = '.questionLi, .singleQuesId, .mark_item, .Zy_TIt6, .TiMu, [class*="question"]';
                        return document.querySelectorAll(selectors).length;
                    }""")
                    if has_q > 0:
                        questions = await fetcher._ocr.recognize_questions(f)
                        print(f"[作业] OCR 识别到 {len(questions)} 道题")
                        break
                except Exception:
                    continue

            if not questions:
                for f in driver.page.frames:
                    if f == driver.page.main_frame:
                        continue
                    try:
                        body_text = await f.evaluate("document.body ? document.body.innerText.substring(0, 500) : ''")
                        if any(kw in body_text for kw in ['单选', '多选', '判断', '填空', '题量']):
                            questions = await fetcher._ocr.recognize_questions(f)
                            if questions:
                                print(f"[作业] OCR 识别到 {len(questions)} 道题")
                                break
                    except Exception:
                        continue

        if not questions:
            results.append(f"• {assignment['title']}: 未解析到题目，跳过")
            continue

        # 处理附件
        attachments = hw.get("attachments", [])
        attachment_content = ""
        if attachments:
            attachment_content = await fetcher._process_attachments(attachments)

        # 并发答题
        sem = asyncio.Semaphore(5)
        loop = asyncio.get_event_loop()

        async def answer_one(qi, q):
            async with sem:
                q_type = q["type"]
                q_text = q["text"]
                options = q.get("options", [])
                if attachment_content and q_type in ("paper", "short", "code"):
                    q_text = f"{q_text}\n\n参考材料：\n{attachment_content}"

                print(f"[作业] 答题 {qi+1}/{len(questions)}: [{q_type}] {q_text[:50]}...")
                if q_type == "single":
                    ans = await loop.run_in_executor(None, llm.answer_choice, q_text, options, False)
                elif q_type == "multi":
                    ans = await loop.run_in_executor(None, llm.answer_choice, q_text, options, True)
                elif q_type == "judge":
                    ans = await loop.run_in_executor(None, llm.answer_judge, q_text)
                elif q_type == "fill":
                    ans = await loop.run_in_executor(None, llm.answer_fill, q_text)
                elif q_type == "short":
                    ans = await loop.run_in_executor(None, llm.answer_short, q_text)
                elif q_type == "code":
                    ans = await loop.run_in_executor(None, llm.answer_code, q_text)
                elif q_type == "paper":
                    ans = await loop.run_in_executor(None, llm.answer_paper, q_text)
                else:
                    ans = await loop.run_in_executor(None, llm.answer_short, q_text)
                print(f"[作业]   第{qi+1}题答案: {ans}")
                return ans

        raw_answers = await asyncio.gather(*[answer_one(qi, q) for qi, q in enumerate(questions)], return_exceptions=True)
        answers = []
        for i, ans in enumerate(raw_answers):
            if isinstance(ans, Exception):
                print(f"[作业]   第{i+1}题答题失败: {ans}，使用默认答案A")
                answers.append("A")
            else:
                answers.append(ans)

        hw_frame = getattr(fetcher, 'hw_frame', None)
        submit_result = await submitter.fill_and_submit(questions, answers, frame=hw_frame)

        result_msg = f"• {assignment['title']}: {len(questions)} 道题已作答，状态={submit_result['status']}"
        if submit_result.get('code_files'):
            result_msg += f"\n  编程题文件已保存到: data/code/ 目录，请手动上传"
        if submit_result.get('paper_files'):
            result_msg += f"\n  论文文件已保存到: data/code/ 目录，请手动上传"
        if attachments:
            result_msg += f"\n  已读取 {len(attachments)} 个附件"
        results.append(result_msg)

        # 导航回课程页
        try:
            await driver.page.goto(course["url"], wait_until="domcontentloaded", timeout=15000)
            await driver.random_delay(2, 3)
            await driver.page.evaluate("""() => {
                const els = document.querySelectorAll('li, a, span, div');
                for (const el of els) {
                    if (el.innerText.trim() === '作业' && el.offsetParent !== null) { el.click(); return; }
                }
            }""")
            await driver.random_delay(3, 5)
        except Exception:
            pass

    reply = f"作业完成！\n课程：{course['name']}\n" + "\n".join(results)
    memory.record_tool_execution("do_homework", course["name"], reply)
    return reply
