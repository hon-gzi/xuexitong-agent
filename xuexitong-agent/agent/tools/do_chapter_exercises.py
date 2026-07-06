"""工具：do_chapter_exercises — 自动完成章节练习"""

import asyncio


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "do_chapter_exercises",
        "description": "自动完成课程每个章节后面的练习题（章节测验/章节作业），区别于老师布置的日常作业",
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
    """执行自动完成章节练习"""
    from homework.fetch import HomeworkFetcher
    from homework.submit import HomeworkSubmitter
    from video.player import VideoPlayer
    from llm.client import llm

    course_name = args.get("course_name", "")
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

    # 进入课程页面
    await page.goto(course["url"], wait_until="domcontentloaded", timeout=30000)
    await driver.random_delay(3, 5)

    # 点击"章节"标签
    await page.evaluate("""
        () => {
            const els = document.querySelectorAll('li, a, span');
            for (const el of els) {
                if (el.innerText.trim() === '章节' && el.offsetParent !== null) {
                    el.click(); return;
                }
            }
        }
    """)
    await driver.random_delay(5, 8)

    # 找到章节frame
    target_frame = None
    for frame in page.frames:
        if "studentcourse" in frame.url:
            target_frame = frame
            break

    if not target_frame:
        return "未找到章节列表。"

    # 进入第一个子章节
    first_chapter = await target_frame.evaluate("""
        () => {
            const items = document.querySelectorAll('.chapter_item');
            for (const item of items) {
                const onclick = item.getAttribute('onclick') || '';
                const match = onclick.match(/toOld\\('([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*(\\d+)/);
                if (match) return {courseId: match[1], chapterId: match[2], clazzid: match[3]};
            }
            return null;
        }
    """)

    if not first_chapter:
        return "未找到章节入口。"

    await target_frame.evaluate(f"""
        () => {{ toOld('{first_chapter["courseId"]}', '{first_chapter["chapterId"]}', '{first_chapter["clazzid"]}', 0); }}
    """)
    await driver.random_delay(10, 15)

    # 找 studentstudy frame
    study_frame = None
    for frame in page.frames:
        if "studentstudy" in frame.url:
            study_frame = frame
            break

    if not study_frame:
        return "未进入章节详情页。"

    # 获取所有章节测试题
    test_items = await study_frame.evaluate("""
        () => {
            const items = [];
            const spans = document.querySelectorAll('.posCatalog_name');
            for (const s of spans) {
                const text = s.innerText.trim();
                if (text.includes('测试题') || text.includes('章节测验') || text.includes('章节作业')) {
                    const onclick = s.getAttribute('onclick') || '';
                    const match = onclick.match(/getTeacherAjax\\('([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*'([^']+)'\\s*(?:,\\s*(\\d+))?/);
                    if (match) {
                        items.push({
                            title: text,
                            courseId: match[1],
                            clazzid: match[2],
                            chapterId: match[3],
                            cpi: match[4] || '0',
                        });
                    }
                }
            }
            return items;
        }
    """)

    if not test_items:
        return f"「{course['name']}」未找到章节测试题。"

    print(f"[章节练习] 找到 {len(test_items)} 个章节测试")

    results = []
    for item in test_items:
        title = item["title"]
        chapter_id = item["chapterId"]
        print(f"[章节练习] 处理: {title}")

        # 重新找 study frame
        study_frame = None
        for frame in page.frames:
            if "studentstudy" in frame.url:
                study_frame = frame
                break

        if not study_frame:
            results.append(f"• {title}: study frame丢失")
            continue

        # 加载章节内容
        try:
            await asyncio.wait_for(
                study_frame.evaluate(f"""
                    () => {{
                        const spans = document.querySelectorAll('.posCatalog_name');
                        for (const s of spans) {{
                            if (s.innerText.includes('{chapter_id}') || s.getAttribute('onclick')?.includes('{chapter_id}')) {{
                                s.click();
                                return;
                            }}
                        }}
                        if (typeof getTeacherAjax === 'function') {{
                            getTeacherAjax('{item["courseId"]}', '{item["clazzid"]}', '{chapter_id}', {item["cpi"]});
                        }}
                    }}
                """),
                timeout=15,
            )
        except Exception as e:
            print(f"[章节练习] 调用getTeacherAjax失败: {e}")
            results.append(f"• {title}: 加载失败")
            continue

        # 等待测试 iframe 出现
        hw_frame = None
        for _ in range(15):
            await driver.random_delay(2, 3)
            for frame in page.frames:
                if "doHomeWorkNew" in frame.url or "work/do" in frame.url:
                    hw_frame = frame
                    break
            if hw_frame:
                break
            print(f"[章节练习] 等待测试iframe... ({_+1}/15)")

        if not hw_frame:
            results.append(f"• {title}: 未加载出测试页面，可能已完成")
            continue

        print(f"[章节练习] 找到测试iframe: {hw_frame.url[:80]}")

        # 解析题目
        questions = await _parse_questions_in_frame(fetcher, hw_frame)
        print(f"[章节练习] 解析到 {len(questions)} 道题")
        if not questions:
            results.append(f"• {title}: 未解析到题目，可能已完成")
            continue

        # AI 答题
        answers = []
        for qi, q in enumerate(questions):
            q_type = q["type"]
            q_text = q["text"]
            options = q.get("options", [])
            print(f"[章节练习] 答题 {qi+1}/{len(questions)}: [{q_type}] {q_text[:60]}")
            if q_type == "single":
                answer = llm.answer_choice(q_text, options, is_multi=False)
            elif q_type == "multi":
                answer = llm.answer_choice(q_text, options, is_multi=True)
            elif q_type == "judge":
                answer = llm.answer_judge(q_text)
            elif q_type == "fill":
                answer = llm.answer_fill(q_text)
            else:
                answer = llm.answer_short(q_text)
            print(f"[章节练习]   LLM答案: {answer}")
            answers.append(answer)

        # 填写并提交
        filled = await _fill_and_submit_in_frame(driver, hw_frame, questions, answers)
        results.append(f"• {title}: {len(questions)} 道题已作答")

    reply = f"章节练习完成！\n课程：{course['name']}\n" + "\n".join(results)
    memory.record_tool_execution("do_chapter_exercises", course["name"], reply)
    return reply


async def _parse_questions_in_frame(fetcher, frame) -> list[dict]:
    """在指定iframe里解析题目"""
    if fetcher.use_ocr and fetcher._ocr:
        print("[章节练习] 使用 OCR 识别题目")
        return await fetcher._ocr.recognize_questions(frame)

    questions = await frame.evaluate("""
        () => {
            const questions = [];
            const seen = new Set();
            const containers = document.querySelectorAll(
                '.questionLi, .singleQuesId, .TiMu, .question-item, [class*="question"], .mark_item, .Zy_TIt6'
            );
            if (containers.length > 0) {
                for (let i = 0; i < containers.length; i++) {
                    const c = containers[i];
                    const text = (c.innerText || '').trim();
                    if (text.length < 10) continue;
                    const key = text.substring(0, 80);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    let type = 'unknown';
                    if (text.includes('单选')) type = 'single';
                    else if (text.includes('多选')) type = 'multi';
                    else if (text.includes('判断')) type = 'judge';
                    else if (text.includes('填空')) type = 'fill';
                    if (type === 'unknown') continue;
                    let questionText = text;
                    const typeMatch = text.match(/(?:单选题|多选题|判断题|填空题|简答题)\\s*[：:]?\\s*/);
                    if (typeMatch) {
                        questionText = text.substring(typeMatch.index + typeMatch[0].length).trim();
                    }
                    const options = [];
                    const lines = text.split(/[\\n\\r]+/);
                    for (const line of lines) {
                        const m = line.match(/^([A-E])[.、．\\s]+(.+)/);
                        if (m && m[2].trim().length < 200) {
                            options.push(m[2].trim());
                        }
                    }
                    if (options.length === 0) {
                        const lis = c.querySelectorAll('li, .xuanxiang, .option');
                        for (const li of lis) {
                            const t = (li.innerText || '').trim();
                            if (t && t.length < 200 && /^[A-E]/.test(t)) {
                                options.push(t.replace(/^[A-E][.、．\\s]+/, '').trim());
                            }
                        }
                    }
                    questions.push({
                        index: questions.length,
                        type: type,
                        text: questionText.substring(0, 500),
                        options: options,
                        containerIndex: i,
                    });
                }
            }
            return questions;
        }
    """)
    return questions if questions else []


async def _fill_and_submit_in_frame(driver, frame, questions: list[dict], answers: list[str]) -> int:
    """在指定iframe里填写答案并提交"""
    filled = 0
    selectors = '.questionLi, .singleQuesId, .TiMu, .question-item, [class*="question"], .mark_item, .Zy_TIt6'

    for q, answer in zip(questions, answers):
        try:
            q_type = q["type"]
            idx = q.get("dom_index", q.get("containerIndex", q["index"]))

            if q_type == "single":
                await frame.evaluate(f"""
                    (data) => {{
                        const containers = document.querySelectorAll('{selectors}');
                        const c = containers[data.idx];
                        if (!c) return '容器不存在';
                        let optEls = Array.from(c.querySelectorAll('[role="radio"]'));
                        if (optEls.length < 2) optEls = Array.from(c.querySelectorAll('.xuanxiang, .option, [data-key]'));
                        if (optEls.length < 2) optEls = Array.from(c.querySelectorAll('li'));
                        const L = data.letter.toUpperCase();
                        for (const el of optEls) {{
                            const span = el.querySelector('span[data]');
                            if (span && span.getAttribute('data').toUpperCase() === L) {{
                                el.click(); return 'ok';
                            }}
                        }}
                        const i = L.charCodeAt(0) - 65;
                        if (i >= 0 && i < optEls.length) {{ optEls[i].click(); return 'ok'; }}
                        return '选项越界';
                    }}
                """, {"idx": idx, "letter": answer})

            elif q_type == "multi":
                for letter in answer.split(","):
                    letter = letter.strip()
                    if not letter:
                        continue
                    await frame.evaluate(f"""
                        (data) => {{
                            const containers = document.querySelectorAll('{selectors}');
                            const c = containers[data.idx];
                            if (!c) return '容器不存在';
                            let optEls = Array.from(c.querySelectorAll('[role="radio"]'));
                            if (optEls.length < 2) optEls = Array.from(c.querySelectorAll('.xuanxiang, .option'));
                            if (optEls.length < 2) optEls = Array.from(c.querySelectorAll('li'));
                            const L = data.letter.toUpperCase();
                            for (const el of optEls) {{
                                const span = el.querySelector('span[data]');
                                if (span && span.getAttribute('data').toUpperCase() === L) {{
                                    el.click(); return 'ok';
                                }}
                            }}
                            const i = L.charCodeAt(0) - 65;
                            if (i >= 0 && i < optEls.length) {{ optEls[i].click(); return 'ok'; }}
                            return '选项越界';
                        }}
                    """, {"idx": idx, "letter": letter})
                    await driver.random_delay(0.3, 0.5)

            elif q_type == "judge":
                await frame.evaluate(f"""
                    (answer) => {{
                        const containers = document.querySelectorAll('{selectors}');
                        const c = containers[{idx}];
                        if (!c) return;
                        const wantTrue = answer.includes('对');
                        const radios = c.querySelectorAll('[role="radio"]');
                        for (const r of radios) {{
                            const span = r.querySelector('span[data]');
                            const d = span ? span.getAttribute('data') : null;
                            if ((wantTrue && d === 'true') || (!wantTrue && d === 'false')) {{
                                r.click(); return;
                            }}
                        }}
                    }}
                """, answer)

            elif q_type == "fill":
                await frame.evaluate(f"""
                    (answer) => {{
                        const containers = document.querySelectorAll('{selectors}');
                        const c = containers[{idx}];
                        if (!c) return;
                        const input = c.querySelector('textarea, input[type="text"], [contenteditable="true"]');
                        if (input) {{
                            input.value = answer;
                            input.dispatchEvent(new Event('input', {{bubbles: true}}));
                        }}
                    }}
                """, answer)

            filled += 1
            await driver.random_delay(0.5, 1)
        except Exception as e:
            print(f"[章节练习] 第{q['index']+1}题填写失败: {e}")

    # 提交
    try:
        await frame.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, a, span, input[type="button"]');
                for (const b of btns) {
                    const text = b.innerText.trim();
                    if (text === '提交' || text === '交卷' || text === '确定') {
                        b.click(); return;
                    }
                }
            }
        """)
        await driver.random_delay(2, 3)
        await frame.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, a, span');
                for (const b of btns) {
                    const text = b.innerText.trim();
                    if (text === '确定' || text === '确认提交') {
                        b.click(); return;
                    }
                }
            }
        """)
        await driver.random_delay(2, 3)
    except Exception as e:
        print(f"[章节练习] 提交失败: {e}")

    return filled
