"""工具注册表：定义 LLM 可调用的工具及执行逻辑"""

import asyncio
from playwright.async_api import Page
from browser.driver import BrowserDriver
from video.player import VideoPlayer
from homework.fetch import HomeworkFetcher
from homework.submit import HomeworkSubmitter
from llm.client import llm


TOOL_DEFINITIONS = [
    {
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
    },
    {
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
    },
    {
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
                        "description": "要刷的章节序号列表（从0开始，对应截图中的章节顺序）。不填则刷所有章节。",
                    },
                    "speed": {
                        "type": "number",
                        "description": "播放倍速，默认2.0",
                    },
                },
                "required": ["course_name"],
            },
        },
    },
    {
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
    },
    {
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
    },
    {
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
    },
]


class ToolExecutor:
    def __init__(self, driver: BrowserDriver, page: Page):
        self.driver = driver
        self.page = page
        self.player = VideoPlayer(driver)
        self.fetcher = HomeworkFetcher(driver, use_ocr=True)
        self.submitter = HomeworkSubmitter(driver)

    async def execute(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "list_courses":
            return await self._list_courses()
        elif tool_name == "screenshot_chapters":
            return await self._screenshot_chapters(arguments)
        elif tool_name == "watch_course":
            return await self._watch_course(arguments)
        elif tool_name == "list_assignments":
            return await self._list_assignments(arguments)
        elif tool_name == "do_homework":
            return await self._do_homework(arguments)
        elif tool_name == "do_chapter_exercises":
            return await self._do_chapter_exercises(arguments)
        else:
            return f"未知工具: {tool_name}"

    async def _find_course(self, course_name: str) -> dict | None:
        courses = await self.player.get_course_list()
        if not courses:
            return None
        for c in courses:
            if course_name in c["name"]:
                return c
        for c in courses:
            if course_name.replace(" ", "") in c["name"].replace(" ", ""):
                return c
        return None

    async def _list_courses(self) -> str:
        courses = await self.player.get_course_list()
        if not courses:
            return "未获取到课程列表，请确认已登录。"
        lines = [f"{i+1}. {c['name']}" for i, c in enumerate(courses)]
        return f"共 {len(courses)} 门课程：\n" + "\n".join(lines)

    async def _screenshot_chapters(self, args: dict) -> str:
        """截图章节列表，返回截图文件路径"""
        course_name = args.get("course_name", "")
        if not course_name:
            return "缺少课程名称参数"

        course = await self._find_course(course_name)
        if not course:
            return f"未找到包含「{course_name}」的课程。"

        path = await self.player.screenshot_chapter_list(course["url"])
        return f"课程「{course['name']}」的章节列表截图已保存到: {path}\n请用Read工具查看截图，识别哪些章节没有绿色勾选标记（未完成），然后调用watch_course并传入这些章节的序号。"

    async def _watch_course(self, args: dict) -> str:
        course_name = args.get("course_name", "")
        speed = args.get("speed", 2.0)
        chapters_filter = args.get("chapters")  # 可选：要刷的章节序号列表

        if not course_name:
            return "缺少课程名称参数"

        course = await self._find_course(course_name)
        if not course:
            return f"未找到包含「{course_name}」的课程，请检查名称或先用 list_courses 查看课程列表。"

        result = await self.player.batch_watch(course["url"], speed, chapters_filter)
        return (
            f"刷课完成！\n"
            f"课程：{course['name']}\n"
            f"进度：{result['completed']}/{result['total']} 个视频已完成\n"
            f"跳过：{result['skipped']}，失败：{result['failed']}"
        )

    async def _list_assignments(self, args: dict) -> str:
        course_name = args.get("course_name", "")
        if not course_name:
            return "缺少课程名称参数"

        course = await self._find_course(course_name)
        if not course:
            return f"未找到包含「{course_name}」的课程。"

        assignments = await self.fetcher.get_assignments(course["url"])
        if not assignments:
            return f"「{course['name']}」没有作业。"

        lines = []
        for i, a in enumerate(assignments):
            status = "已完成" if a["done"] else "未完成"
            lines.append(f"{i+1}. [{status}] {a['title']}")
        return f"「{course['name']}」共 {len(assignments)} 个作业：\n" + "\n".join(lines)

    async def _do_homework(self, args: dict) -> str:
        course_name = args.get("course_name", "")
        assignment_title = args.get("assignment_title")

        if not course_name:
            return "缺少课程名称参数"

        course = await self._find_course(course_name)
        if not course:
            return f"未找到包含「{course_name}」的课程。"

        assignments = await self.fetcher.get_assignments(course["url"])
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
            hw = await self.fetcher.open_assignment(assignment["url"], assignment["title"])
            questions = hw.get("questions", [])

            # DOM 解析失败或数量不对 → OCR 兜底
            if not questions and self.fetcher._ocr:
                print(f"[作业] {assignment['title']}: DOM解析失败，切换OCR...")
                url = assignment.get("url", "")

                # 如果没有URL，先导航回课程页提取
                if not url:
                    try:
                        await self.driver.page.goto(course["url"], wait_until="domcontentloaded")
                        await self.driver.random_delay(3, 5)
                        await self.driver.page.evaluate("""() => {
                            const els = document.querySelectorAll('li, a, span, div');
                            for (const el of els) {
                                if (el.innerText.trim() === '作业' && el.offsetParent !== null) { el.click(); return; }
                            }
                        }""")
                        await self.driver.random_delay(3, 5)
                    except Exception:
                        pass
                    for frame in self.driver.page.frames:
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

                # 导航到作业页面
                if url:
                    if url.startswith("/"):
                        from browser.driver import CHAOXING_URL
                        url = f"{CHAOXING_URL}{url}"
                    await self.driver.page.goto(url, wait_until="domcontentloaded")
                    await self.driver.random_delay(3, 5)
                    print(f"[作业] OCR兜底: 已导航到 {self.driver.page.url[:80]}")

                # 在当前页面找frame并OCR（不限于特定选择器）
                for f in self.driver.page.frames:
                    try:
                        has_q = await f.evaluate("""() => {
                            const selectors = '.questionLi, .singleQuesId, .mark_item, .Zy_TIt6, .TiMu, [class*="question"]';
                            return document.querySelectorAll(selectors).length;
                        }""")
                        if has_q > 0:
                            print(f"[作业] OCR兜底: 找到frame {f.url[:60]} ({has_q}个容器)")
                            questions = await self.fetcher._ocr.recognize_questions(f)
                            print(f"[作业] OCR 识别到 {len(questions)} 道题")
                            break
                    except Exception:
                        continue

                # 如果还是没找到，尝试所有frame截图OCR
                if not questions:
                    print(f"[作业] OCR兜底: 特定选择器未找到，尝试全frame截图...")
                    for f in self.driver.page.frames:
                        if f == self.driver.page.main_frame:
                            continue
                        try:
                            body_text = await f.evaluate("document.body ? document.body.innerText.substring(0, 500) : ''")
                            if any(kw in body_text for kw in ['单选', '多选', '判断', '填空', '题量']):
                                print(f"[作业] OCR兜底: 在frame {f.url[:60]} 中检测到题目关键词")
                                questions = await self.fetcher._ocr.recognize_questions(f)
                                if questions:
                                    print(f"[作业] OCR 识别到 {len(questions)} 道题")
                                    break
                        except Exception:
                            continue

            if not questions:
                results.append(f"• {assignment['title']}: 未解析到题目，跳过")
                continue

            # 处理附件（如果有）
            attachments = hw.get("attachments", [])
            attachment_content = ""
            if attachments:
                print(f"[作业] 发现 {len(attachments)} 个附件，正在读取...")
                attachment_content = await self.fetcher._process_attachments(attachments)
                if attachment_content:
                    print(f"[作业] 附件内容已读取，长度: {len(attachment_content)} 字符")
                    print(f"[作业] 附件内容前200字: {attachment_content[:200]}...")

            # 并发答题：同时调多个LLM，限制5个并发避免API限流
            sem = asyncio.Semaphore(5)
            loop = asyncio.get_event_loop()

            async def answer_one(qi, q):
                async with sem:
                    q_type = q["type"]
                    q_text = q["text"]
                    options = q.get("options", [])

                    # 如果有附件内容，添加到题目中
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

            print(f"[作业] 开始并发答题 {len(questions)} 题（5并发）...")
            raw_answers = await asyncio.gather(*[answer_one(qi, q) for qi, q in enumerate(questions)], return_exceptions=True)
            answers = []
            for i, ans in enumerate(raw_answers):
                if isinstance(ans, Exception):
                    print(f"[作业]   第{i+1}题答题失败: {ans}，使用默认答案A")
                    answers.append("A")
                else:
                    answers.append(ans)

            print(f"[作业] {len(questions)}道题全部答完，开始填写答案...")
            hw_frame = getattr(self.fetcher, 'hw_frame', None)
            submit_result = await self.submitter.fill_and_submit(questions, answers, frame=hw_frame)

            # 构建结果信息
            result_msg = f"• {assignment['title']}: {len(questions)} 道题已作答，状态={submit_result['status']}"
            if submit_result.get('code_files'):
                result_msg += f"\n  编程题文件已保存到: data/code/ 目录，请手动上传"
            if submit_result.get('paper_files'):
                result_msg += f"\n  论文文件已保存到: data/code/ 目录，请手动上传"
            if attachments:
                result_msg += f"\n  已读取 {len(attachments)} 个附件"
            results.append(result_msg)

            # 填写完成后导航回课程页，准备处理下一个作业
            try:
                await self.driver.page.goto(course["url"], wait_until="domcontentloaded", timeout=15000)
                await self.driver.random_delay(2, 3)
                # 重新点击作业标签
                await self.driver.page.evaluate("""() => {
                    const els = document.querySelectorAll('li, a, span, div');
                    for (const el of els) {
                        if (el.innerText.trim() === '作业' && el.offsetParent !== null) { el.click(); return; }
                    }
                }""")
                await self.driver.random_delay(3, 5)
            except Exception:
                pass

        return f"作业完成！\n课程：{course['name']}\n" + "\n".join(results)

    async def _do_chapter_exercises(self, args: dict) -> str:
        course_name = args.get("course_name", "")
        if not course_name:
            return "缺少课程名称参数"

        course = await self._find_course(course_name)
        if not course:
            return f"未找到包含「{course_name}」的课程。"

        page = self.driver.page

        # 进入课程页面
        await page.goto(course["url"], wait_until="domcontentloaded", timeout=30000)
        await self.driver.random_delay(3, 5)

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
        await self.driver.random_delay(5, 8)

        # 找到章节frame（studentcourse）
        target_frame = None
        for frame in page.frames:
            if "studentcourse" in frame.url:
                target_frame = frame
                break

        if not target_frame:
            return "未找到章节列表。"

        # 先进入第一个子章节（调用toOld），让章节详情页加载出来
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

        # 调用toOld进入第一章
        await target_frame.evaluate(f"""
            () => {{ toOld('{first_chapter["courseId"]}', '{first_chapter["chapterId"]}', '{first_chapter["clazzid"]}', 0); }}
        """)
        await self.driver.random_delay(10, 15)

        # 现在在studentstudy页面，找章节列表frame里的测试题
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

            # 重新找study frame（可能因导航失效）
            study_frame = None
            for frame in page.frames:
                if "studentstudy" in frame.url:
                    study_frame = frame
                    break

            if not study_frame:
                results.append(f"• {title}: study frame丢失")
                continue

            # 调用getTeacherAjax加载章节内容（用span的onclick）
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
                            // 直接调用
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

            # 等待doHomeWorkNew iframe出现
            hw_frame = None
            for _ in range(15):
                await self.driver.random_delay(2, 3)
                for frame in page.frames:
                    if "doHomeWorkNew" in frame.url or "work/do" in frame.url:
                        hw_frame = frame
                        break
                if hw_frame:
                    break
                print(f"[章节练习] 等待测试iframe... ({_+1}/15)")

            if not hw_frame:
                print(f"[章节练习] {title}: 未找到测试iframe，跳过")
                results.append(f"• {title}: 未加载出测试页面，可能已完成")
                continue

            print(f"[章节练习] 找到测试iframe: {hw_frame.url[:80]}")

            # 在测试iframe里解析题目
            print(f"[章节练习] 开始解析题目...")
            questions = await self._parse_questions_in_frame(hw_frame)
            print(f"[章节练习] 解析到 {len(questions)} 道题")
            if not questions:
                results.append(f"• {title}: 未解析到题目，可能已完成")
                continue

            # AI答题
            answers = []
            for qi, q in enumerate(questions):
                q_type = q["type"]
                q_text = q["text"]
                options = q.get("options", [])
                print(f"[章节练习] 答题 {qi+1}/{len(questions)}: [{q_type}] {q_text[:60]}")
                if options:
                    print(f"[章节练习]   选项: {options}")
                else:
                    print(f"[章节练习]   警告: 无选项!")

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

            # 在iframe里填写答案并提交
            filled = await self._fill_and_submit_in_frame(hw_frame, questions, answers)
            results.append(f"• {title}: {len(questions)} 道题已作答")

        return f"章节练习完成！\n课程：{course['name']}\n" + "\n".join(results)

    async def _parse_questions_in_frame(self, frame) -> list[dict]:
        """在指定iframe里解析题目，返回干净的题目列表"""
        # 强制使用 OCR（完全绕过字体反爬）
        if self.fetcher.use_ocr and self.fetcher._ocr:
            print("[章节练习] 使用 OCR 识别题目")
            return await self.fetcher._ocr.recognize_questions(frame)

        # 备用：DOM 解析（不推荐，会被字体反爬干扰）
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

    async def _fill_and_submit_in_frame(self, frame, questions: list[dict], answers: list[str]) -> int:
        """在指定iframe里填写答案并提交"""
        filled = 0
        selectors = '.questionLi, .singleQuesId, .TiMu, .question-item, [class*="question"], .mark_item, .Zy_TIt6'

        for q, answer in zip(questions, answers):
            try:
                q_type = q["type"]
                # 优先用 dom_index（OCR解析时记录的原始DOM位置），其次 containerIndex
                idx = q.get("dom_index", q.get("containerIndex", q["index"]))
                print(f"[填写] 第{q['index']+1}题 [{q_type}] 答案={answer} 容器索引={idx}")

                if q_type == "single":
                    result = await frame.evaluate(f"""
                        (data) => {{
                            const containers = document.querySelectorAll('{selectors}');
                            const c = containers[data.idx];
                            if (!c) return '容器不存在 idx=' + data.idx;
                            // 学习通选项: div[role="radio"] 内含 span[data="A"]
                            let optEls = Array.from(c.querySelectorAll('[role="radio"]'));
                            if (optEls.length < 2) optEls = Array.from(c.querySelectorAll('.xuanxiang, .option, [data-key]'));
                            if (optEls.length < 2) optEls = Array.from(c.querySelectorAll('li'));
                            const L = data.letter.toUpperCase();
                            for (const el of optEls) {{
                                const span = el.querySelector('span[data]');
                                if (span && span.getAttribute('data').toUpperCase() === L) {{
                                    el.click(); return 'ok clicked ' + el.innerText.substring(0, 30);
                                }}
                            }}
                            const i = L.charCodeAt(0) - 65;
                            if (i >= 0 && i < optEls.length) {{
                                optEls[i].click(); return 'ok clicked ' + optEls[i].innerText.substring(0, 30);
                            }}
                            return '选项越界 letter=' + data.letter;
                        }}
                    """, {"idx": idx, "letter": answer})
                    print(f"[填写] 单选结果: {result}")

                elif q_type == "multi":
                    for letter in answer.split(","):
                        letter = letter.strip()
                        if not letter: continue
                        result = await frame.evaluate(f"""
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
                        print(f"[填写] 多选 {letter}: {result}")
                        await self.driver.random_delay(0.3, 0.5)

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
                await self.driver.random_delay(0.5, 1)
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
            await self.driver.random_delay(2, 3)
            # 确认弹窗
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
            await self.driver.random_delay(2, 3)
        except Exception as e:
            print(f"[章节练习] 提交失败: {e}")

        return filled
