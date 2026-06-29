import re
import os
import asyncio
from pathlib import Path
from browser.driver import BrowserDriver, CHAOXING_URL
from homework.ocr_recognizer import OCRRecognizer


class HomeworkFetcher:
    """学习通作业抓取"""

    def __init__(self, driver: BrowserDriver, use_ocr: bool = True):
        self.driver = driver
        self.use_ocr = use_ocr
        self._ocr = OCRRecognizer() if use_ocr else None
        self.hw_frame = None  # 解析题目时找到的 frame，供 fill_and_submit 复用

    async def get_assignments(self, course_url: str) -> list[dict]:
        """获取课程的作业列表（OCR识别 + DOM提取链接）"""
        page = self.driver.page

        # 进入课程页面
        if course_url.startswith("/"):
            course_url = f"{CHAOXING_URL}{course_url}"
        await page.goto(course_url, wait_until="domcontentloaded")
        await self.driver.random_delay(3, 5)

        # 点击"作业"标签
        try:
            clicked = await page.evaluate("""
                () => {
                    const els = document.querySelectorAll('li, a, span, div');
                    for (const el of els) {
                        if (el.innerText.trim() === '作业' && el.offsetParent !== null) {
                            el.click(); return true;
                        }
                    }
                    return false;
                }
            """)
            if clicked:
                print("[作业] 已点击作业标签")
        except Exception as e:
            print(f"[作业] 点击作业标签失败: {e}")

        # 等待作业内容加载
        print("[作业] 等待作业内容加载...")
        for wait_i in range(20):
            await self.driver.random_delay(1, 1)
            for frame in page.frames:
                try:
                    has_work = await frame.evaluate("""
                        () => (document.body?.innerText || '').includes('未交')
                    """)
                    if has_work:
                        print(f"[作业] 检测到作业内容 (等待{wait_i+1}秒)")
                        break
                except Exception:
                    continue
            else:
                continue
            break

        # 1) OCR 截图识别蓝色未交作业标题
        ocr_titles = []
        screenshot_path = "data/assignments_list.png"
        await page.screenshot(path=screenshot_path)
        if self._ocr:
            print("[作业] OCR 识别作业列表...")
            ocr_items = await self._ocr.recognize_assignments(screenshot_path)
            ocr_titles = [item["title"] for item in ocr_items]
            print(f"[作业] OCR 识别到 {len(ocr_titles)} 个蓝色未交作业: {ocr_titles}")

        # 2) DOM 提取所有未交作业（含链接），按标题匹配 OCR 结果
        assignments = []
        dom_items = []
        for frame in page.frames:
            try:
                raw = await frame.evaluate("""
                    () => {
                        const results = [];
                        const seen = new Set();
                        const allEls = document.querySelectorAll('div, li, a, span, tr');
                        for (const el of allEls) {
                            const text = el.innerText || '';
                            if (text.length < 10 || text.length > 500) continue;
                            if (!text.includes('未交')) continue;
                            if (el.querySelectorAll('div, li, tr').length > 6) continue;
                            const lines = text.split(/\\n/).map(l => l.trim()).filter(l => l.length > 0);
                            if (lines.length < 2) continue;
                            let title = lines[0];
                            if (!title || title.length > 100 || title === '作业' || title.length < 3) continue;
                            if (seen.has(title)) continue;
                            seen.add(title);
                            let url = '';
                            const link = el.querySelector('a[href]');
                            if (link) url = link.href;
                            else {
                                const oc = el.querySelector('[onclick]');
                                if (oc) {
                                    const m = (oc.getAttribute('onclick')||'').match(/https?:[^'"\\s)]+/);
                                    if (m) url = m[0];
                                }
                            }
                            results.push({title, url});
                        }
                        return results;
                    }
                """)
                if raw:
                    dom_items.extend(raw)
            except Exception:
                continue

        print(f"[作业] DOM 找到 {len(dom_items)} 个未交作业")
        for item in dom_items:
            print(f"  - {item['title']} url={'有' if item['url'] else '无'}")

        # 3) 合并: OCR 确认的标题 + DOM 的链接
        if ocr_titles:
            for ocr_title in ocr_titles:
                matched = None
                for dom_item in dom_items:
                    if dom_item["title"] in ocr_title or ocr_title in dom_item["title"]:
                        matched = dom_item
                        break
                assignments.append({
                    "title": ocr_title,
                    "status": "未交",
                    "done": False,
                    "url": matched["url"] if matched else "",
                })
        else:
            # OCR 不可用，直接用 DOM 结果
            for item in dom_items:
                assignments.append({
                    "title": item["title"],
                    "status": "未交",
                    "done": False,
                    "url": item.get("url", ""),
                })

        print(f"[作业] 最终获取 {len(assignments)} 个未交作业")
        for a in assignments:
            print(f"  [TODO] {a['title']} url={'有' if a['url'] else '无'}")

        # 去重
        seen_titles = set()
        unique = []
        for a in assignments:
            if a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique.append(a)
        assignments = unique

        print(f"[作业] 获取到 {len(assignments)} 个未交作业")
        for a in assignments[:5]:
            print(f"  [TODO] {a['title']}")
        if len(assignments) > 5:
            print(f"  ... 共 {len(assignments)} 个")

        return assignments

    async def open_assignment(self, assignment_url: str, assignment_title: str = "") -> dict:
        """打开作业页面，返回题目列表"""
        page = self.driver.page

        if assignment_url:
            # 有 URL，直接导航
            if assignment_url.startswith("/"):
                assignment_url = f"{CHAOXING_URL}{assignment_url}"
            await page.goto(assignment_url, wait_until="domcontentloaded")
        elif assignment_title:
            # 没有 URL，从 DOM 的 data 属性提取链接
            print(f"[作业] 无URL，从DOM提取: {assignment_title}")
            found_url = False
            for frame in page.frames:
                try:
                    url = await frame.evaluate("""
                        (title) => {
                            const lis = document.querySelectorAll('li[onclick*="goTask"]');
                            for (const li of lis) {
                                const text = (li.innerText || '').trim();
                                if (text.includes(title) || title.includes(text.split('\\n')[0].trim())) {
                                    return li.getAttribute('data') || '';
                                }
                            }
                            return '';
                        }
                    """, assignment_title)
                    if url:
                        assignment_url = url
                        found_url = True
                        print(f"[作业] 提取到URL: {url[:80]}")
                        break
                except Exception as e:
                    print(f"[作业] 提取失败: {e}")
                    continue

            if not found_url:
                print(f"[作业] 未找到作业: {assignment_title}")
                return {"total": 0, "questions": [], "error": "未找到作业入口"}
        else:
            return {"total": 0, "questions": [], "error": "无URL也无标题"}

        # 直接导航到作业URL（不依赖新tab）
        if assignment_url.startswith("/"):
            assignment_url = f"{CHAOXING_URL}{assignment_url}"
        await page.goto(assignment_url, wait_until="domcontentloaded")
        await self.driver.random_delay(3, 5)

        print(f"[作业] 当前URL: {page.url[:80]}")

        # 在当前页面找题目frame（多种选择器）
        hw_frame = None
        frame_selectors = [
            '.questionLi, .singleQuesId, .mark_item, .Zy_TIt6',
            '.TiMu, [class*="question"], [class*="Question"]',
        ]
        for sel in frame_selectors:
            for f in page.frames:
                try:
                    has_q = await f.evaluate(f"""
                        () => document.querySelectorAll('{sel}').length
                    """)
                    if has_q > 0:
                        hw_frame = f
                        print(f"[作业] 找到题目frame: {f.url[:60]} ({has_q}题, 选择器: {sel[:30]})")
                        break
                except Exception:
                    continue
            if hw_frame:
                break

        # 如果特定选择器都没找到，通过页面文本关键词找frame
        if not hw_frame:
            print("[作业] 特定选择器未找到frame，尝试关键词匹配...")
            for f in page.frames:
                if f == page.main_frame:
                    continue
                try:
                    body_text = await f.evaluate("document.body ? document.body.innerText.substring(0, 1000) : ''")
                    if any(kw in body_text for kw in ['单选题', '多选题', '判断题', '填空题', '题量']):
                        hw_frame = f
                        print(f"[作业] 关键词匹配到frame: {f.url[:60]}")
                        break
                except Exception:
                    continue

        if not hw_frame:
            print("[作业] 未找到题目frame，尝试整页OCR...")
            # 最后手段：对整个页面截图做 OCR
            if self._ocr:
                questions = await self._ocr.recognize_questions(page)
                return {"total": len(questions), "questions": questions}
            return {"total": 0, "questions": [], "error": "未找到题目"}

        # 保存 frame 引用，供后续 fill_and_submit 使用同一 frame
        self.hw_frame = hw_frame

        # 解析题目
        questions = await self._parse_questions_from_frame(hw_frame)

        # OCR 兜底（DOM解析失败或数量不对）
        if not questions and self._ocr:
            print("[作业] DOM未解析到题目，尝试OCR...")
            questions = await self._ocr.recognize_questions(hw_frame)

        # 注意：不导航回课程页，因为 fill_and_submit 需要在当前作业页面填写答案
        # 调用方在 fill_and_submit 完成后再处理导航

        # 下载附件（如果有）
        attachments = await self._download_attachments(hw_frame)
        if attachments:
            print(f"[作业] 下载了 {len(attachments)} 个附件")
            # 将附件信息添加到返回结果中
            return {"total": len(questions), "questions": questions, "attachments": attachments}

        return {"total": len(questions), "questions": questions}

    async def _parse_questions(self) -> dict:
        """解析作业页面的题目"""
        page = self.driver.page
        questions = []

        # 查找所有题目容器（跨 frame 查找）
        hw_frame = None
        for frame in page.frames:
            if "selectWorkQuestion" in frame.url or "doHomeWorkNew" in frame.url:
                hw_frame = frame
                break

        if not hw_frame:
            for frame in page.frames:
                try:
                    has_q = await frame.evaluate("""
                        () => document.querySelectorAll('.questionLi, .singleQuesId, .mark_item').length
                    """)
                    if has_q > 0:
                        hw_frame = frame
                        break
                except:
                    continue

        if not hw_frame:
            print("[作业] 未找到包含题目的 frame")
            return {"total": 0, "questions": []}

        # 先尝试 DOM 解析
        q_containers = await hw_frame.query_selector_all(
            ".questionLi, .singleQuesId, .TiMu, .question-item, [class*='question']"
        )

        if not q_containers:
            q_containers = await hw_frame.query_selector_all(".mark_item, .Zy_TIt6")

        # 检测是否需要 OCR（字体反爬导致乱码）
        need_ocr = False
        if q_containers and self.use_ocr:
            sample_text = await q_containers[0].inner_text()
            if self._is_garbled(sample_text):
                print("[作业] 检测到字体反爬（乱码），切换到 OCR 模式")
                need_ocr = True

        # 如果需要 OCR 或没有找到容器
        if need_ocr or (not q_containers and self.use_ocr):
            print("[作业] 使用 OCR 识别题目...")
            return {"total": 0, "questions": [], "ocr_frame": hw_frame, "use_ocr": True}

        # 正常 DOM 解析
        for i, container in enumerate(q_containers):
            try:
                q = await self._parse_single_question(container, i)
                if q:
                    questions.append(q)
            except Exception as e:
                print(f"[作业] 解析第{i+1}题失败: {e}")

        return {"total": len(questions), "questions": questions}

    async def _parse_questions_from_frame(self, hw_frame) -> list[dict]:
        """在指定 frame 中解析题目"""
        questions = []

        q_containers = await hw_frame.query_selector_all(
            ".questionLi, .singleQuesId, .mark_item, .Zy_TIt6"
        )
        # 排除非题目元素（如标题容器 fanyaMarking TiMu）
        # 同时记录每个容器在原始 NodeList 中的位置，用于填写答案时精确定位
        filtered = []
        raw_indices = []
        for idx, c in enumerate(q_containers):
            cls = await c.get_attribute("class") or ""
            if "fanyaMarking" in cls:
                continue
            filtered.append(c)
            raw_indices.append(idx)
        q_containers = filtered

        if not q_containers:
            print("[作业] DOM 未找到题目容器")
            return []

        print(f"[作业] DOM 找到 {len(q_containers)} 个题目容器")

        # 校验：从页面提取"题量: N"，对比实际数量
        try:
            page_text = await hw_frame.evaluate("document.body ? document.body.innerText : ''")
            import re
            m = re.search(r'题量[：:]\s*(\d+)', page_text)
            if m:
                expected = int(m.group(1))
                actual = len(q_containers)
                if actual != expected:
                    print(f"[作业] DOM数量({actual})与页面({expected})不一致，切换OCR模式")
                    return []  # 返回空，让调用方走 OCR 兜底
                else:
                    print(f"[作业] 数量校验通过: {actual} 题")
        except Exception as e:
            print(f"[作业] 校验失败: {e}")

        # 检测字体反爬
        if self.use_ocr and q_containers:
            try:
                sample_text = await q_containers[0].inner_text()
                if self._is_garbled(sample_text):
                    print("[作业] 检测到字体反爬，切换 OCR")
                    return []
            except Exception:
                pass

        for i, container in enumerate(q_containers):
            try:
                q = await self._parse_single_question(container, raw_indices[i])
                if q:
                    questions.append(q)
            except Exception as e:
                print(f"[作业] 解析第{i+1}题失败: {e}")

        print(f"[作业] DOM 解析到 {len(questions)} 道题")
        return questions

    async def _parse_single_question(self, container, index: int) -> dict | None:
        """解析单个题目"""
        text = await container.inner_text()

        # 判断题型
        q_type = "unknown"
        if "单选" in text or "单选题" in text:
            q_type = "single"
        elif "多选" in text or "多选题" in text:
            q_type = "multi"
        elif "判断" in text or "判断题" in text:
            q_type = "judge"
        elif "填空" in text or "填空题" in text:
            q_type = "fill"
        elif "简答" in text or "论述" in text:
            q_type = "short"
        elif "编程" in text or "代码" in text:
            q_type = "code"
        elif "论文" in text or "报告" in text or "文档" in text:
            q_type = "paper"

        # 提取题目文本
        question_text = text.strip()

        # 提取选项（如果是选择题）
        options = []
        if q_type in ("single", "multi"):
            # 格式1: "A. 选项文本" 或 "A、选项文本"
            option_matches = re.findall(r'[A-E][.、．]\s*(.+?)(?=[A-E][.、．]|$)', text, re.DOTALL)
            options = [opt.strip() for opt in option_matches]

            # 格式2: "A\n选项文本"（字母单独一行，换行后是选项内容）
            if not options:
                option_matches = re.findall(r'\n\s*([A-E])\s*\n\s*(.+?)(?=\n\s*[A-E]\s*\n|$)', text, re.DOTALL)
                options = [opt.strip() for _, opt in option_matches]

            # 清理选项末尾的 "我的答案:" 等干扰文本
            options = [re.split(r'\n*\s*我的答案', opt)[0].strip() for opt in options]
            options = [opt for opt in options if opt]

            # 备用：从DOM提取（学习通用 div[role="radio"]）
            if not options:
                opt_elements = await container.query_selector_all('[role="radio"]')
                for el in opt_elements:
                    opt_text = (await el.inner_text()).strip()
                    if opt_text and len(opt_text) < 200:
                        options.append(opt_text)
                # 再兜底
                if not options:
                    opt_elements = await container.query_selector_all(".xuanxiang, .option, li")
                    for el in opt_elements:
                        opt_text = (await el.inner_text()).strip()
                        if opt_text and len(opt_text) < 200:
                            options.append(opt_text)

        return {
            "index": index,
            "type": q_type,
            "text": question_text[:500],
            "options": options,
            "selector": f".questionLi:nth-child({index+1}), .singleQuesId:nth-child({index+1})"
        }

    def _is_garbled(self, text: str) -> bool:
        """检测文本是否是字体反爬导致的乱码"""
        if not text:
            return False
        # 检测 Unicode 私有区字符（PUA）- 字体反爬常用
        pua_count = sum(1 for c in text if '' <= c <= '')
        if pua_count > len(text) * 0.1:
            return True
        # 检测是否有大量生僻字（可能是字体映射）
        rare_count = sum(1 for c in text if '一' <= c <= '鿿' and ord(c) > 0x9FFF - 0x200)
        if rare_count > len(text) * 0.3:
            return True
        return False

    async def _download_attachments(self, frame) -> list[dict]:
        """下载题目中的附件文件"""
        attachments = []

        # 创建下载目录
        download_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "attachments")
        os.makedirs(download_dir, exist_ok=True)

        # 查找附件链接
        try:
            # 查找所有链接和附件元素
            links = await frame.evaluate("""
                () => {
                    const results = [];
                    // 查找所有链接
                    const allLinks = document.querySelectorAll('a[href]');
                    for (const link of allLinks) {
                        const href = link.href || '';
                        const text = (link.innerText || '').trim();
                        // 检查是否是附件链接
                        if (href.match(/\\.(doc|docx|pdf|xls|xlsx|ppt|pptx|zip|rar|txt)$/i) ||
                            text.match(/\\.(doc|docx|pdf|xls|xlsx|ppt|pptx|zip|rar|txt)$/i) ||
                            href.includes('download') || href.includes('attachment')) {
                            results.push({href, text});
                        }
                    }
                    // 查找可能的附件容器
                    const attachContainers = document.querySelectorAll('.attach, .attachment, .file, [class*="attach"], [class*="file"]');
                    for (const container of attachContainers) {
                        const links = container.querySelectorAll('a[href]');
                        for (const link of links) {
                            const href = link.href || '';
                            const text = (link.innerText || '').trim();
                            if (href && !results.some(r => r.href === href)) {
                                results.push({href, text});
                            }
                        }
                    }
                    return results;
                }
            """)

            if not links:
                print("[附件] 未找到附件链接")
                return []

            print(f"[附件] 找到 {len(links)} 个附件链接")

            # 下载每个附件
            for i, link_info in enumerate(links):
                href = link_info.get('href', '')
                text = link_info.get('text', f'attachment_{i}')

                if not href:
                    continue

                try:
                    # 生成文件名
                    filename = text if text else f'attachment_{i}'
                    # 清理文件名
                    filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
                    if not filename:
                        filename = f'attachment_{i}'

                    # 确保文件名有扩展名
                    if not any(filename.endswith(ext) for ext in ['.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.txt']):
                        # 从 URL 推断扩展名
                        url_ext = re.search(r'\.(\w{2,4})(?:\?|$)', href)
                        if url_ext:
                            filename += f'.{url_ext.group(1)}'
                        else:
                            filename += '.docx'  # 默认

                    filepath = os.path.join(download_dir, filename)

                    # 下载文件
                    print(f"[附件] 下载: {filename}")

                    # 使用 Playwright 下载
                    async with self.driver.page.expect_download() as download_info:
                        # 点击链接触发下载
                        await frame.evaluate(f"""
                            () => {{
                                const link = document.querySelector('a[href="{href}"]');
                                if (link) link.click();
                            }}
                        """)

                    download = await download_info.value
                    await download.save_as(filepath)

                    attachments.append({
                        'filename': filename,
                        'filepath': filepath,
                        'url': href
                    })

                    print(f"[附件] 已下载: {filepath}")

                except Exception as e:
                    print(f"[附件] 下载失败 {text}: {e}")
                    # 尝试直接通过 URL 下载
                    try:
                        import httpx
                        async with httpx.AsyncClient() as client:
                            response = await client.get(href, follow_redirects=True, timeout=30)
                            if response.status_code == 200:
                                # 从 Content-Disposition 或 URL 推断文件名
                                content_disp = response.headers.get('content-disposition', '')
                                if 'filename=' in content_disp:
                                    filename = re.search(r'filename="?([^"]+)"?', content_disp).group(1)
                                else:
                                    filename = text if text else f'attachment_{i}'
                                    if not any(filename.endswith(ext) for ext in ['.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.txt']):
                                        url_ext = re.search(r'\.(\w{2,4})(?:\?|$)', href)
                                        if url_ext:
                                            filename += f'.{url_ext.group(1)}'
                                        else:
                                            filename += '.docx'

                                filepath = os.path.join(download_dir, filename)
                                with open(filepath, 'wb') as f:
                                    f.write(response.content)

                                attachments.append({
                                    'filename': filename,
                                    'filepath': filepath,
                                    'url': href
                                })
                                print(f"[附件] HTTP下载成功: {filepath}")
                    except Exception as e2:
                        print(f"[附件] HTTP下载也失败: {e2}")

        except Exception as e:
            print(f"[附件] 查找附件失败: {e}")

        return attachments

    async def _read_docx_file(self, filepath: str) -> str:
        """读取 docx 文件内容"""
        try:
            from docx import Document
            doc = Document(filepath)
            content = []
            for para in doc.paragraphs:
                if para.text.strip():
                    content.append(para.text.strip())
            return '\n'.join(content)
        except Exception as e:
            print(f"[附件] 读取 docx 失败: {e}")
            return ""

    async def _process_attachments(self, attachments: list[dict]) -> str:
        """处理附件，提取内容"""
        all_content = []
        for att in attachments:
            filepath = att.get('filepath', '')
            filename = att.get('filename', '')

            if not filepath or not os.path.exists(filepath):
                continue

            # 根据文件类型处理
            if filename.endswith('.docx'):
                content = await self._read_docx_file(filepath)
                if content:
                    all_content.append(f"=== {filename} ===\n{content}")
            elif filename.endswith('.txt'):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if content:
                        all_content.append(f"=== {filename} ===\n{content}")
                except Exception as e:
                    print(f"[附件] 读取 txt 失败: {e}")

        return '\n\n'.join(all_content)
