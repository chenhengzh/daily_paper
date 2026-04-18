import os
import json
import logging
import argparse
import sys
from datetime import date, datetime, timedelta
from typing import Optional
import subprocess

# 确保 src 目录在 Python 路径中，以便导入其他模块
# 这通常在运行脚本时自动处理，或者可以通过设置 PYTHONPATH
# 或者更好的方式是使用相对导入（如果结构允许）或将项目作为包安装
try:
    from scraper import fetch_daily_papers, DEFAULT_KEYWORDS, DEFAULT_CATEGORIES
    from filter import rate_papers, DEFAULT_INTERESTS, DEFAULT_ARXIV_KEYWORDS
    from remote_llm_api import RemoteLLMConfig, default_chat_completion_text
except ModuleNotFoundError:
    # 兼容通过 `import src.main` / repo root 运行的方式
    import os as _os
    import sys as _sys

    _SRC_DIR = _os.path.dirname(_os.path.abspath(__file__))
    if _SRC_DIR not in _sys.path:
        _sys.path.insert(0, _SRC_DIR)
    from scraper import fetch_daily_papers, DEFAULT_KEYWORDS, DEFAULT_CATEGORIES
    from filter import rate_papers, DEFAULT_INTERESTS, DEFAULT_ARXIV_KEYWORDS
    from remote_llm_api import RemoteLLMConfig, default_chat_completion_text
import asyncio
from html_generator import generate_html_from_json


def _score(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _tier_label(overall: float, relevance: float, quality: float) -> str:
    """更严格的分层（用于展示/统计）。

    说明：
    - 仅用于 UI 分层；“高优精选”会再额外做 top-N cap
    - 让 S/A 不至于过多
    """
    if overall >= 8.6 and relevance >= 8.0 and quality >= 7.0:
        return "S"
    if overall >= 7.8 and relevance >= 7.0 and quality >= 6.5:
        return "A"
    if overall >= 6.8:
        return "B"
    return "C"


def mark_high_priority(
    papers: list[dict],
    *,
    target: int = 15,
) -> list[dict]:
    """将当日“高优精选”控制在 10-20（默认 15）。

    策略：
    - 先按 (overall, relevance, quality) 排序
    - 只在 keep=true 范围内做 top-N
    - 写回字段：high_priority / high_priority_rank / tier
    """

    target = int(target)
    if target <= 0:
        target = 15

    # 先写回 tier（展示分层也依赖它）
    for p in papers:
        overall = _score(p.get("overall_priority_score"), 0)
        rel = _score(p.get("relevance_score"), 0)
        qual = _score(p.get("quality_score"), 0)
        p["tier"] = _tier_label(overall, rel, qual)

    kept = [p for p in papers if bool(p.get("keep", True))]

    # 高优精选：只从 S/A 中挑选，避免出现 B 档仍进入“高优”造成认知错位。
    hp_candidates = [p for p in kept if (p.get("tier") in ("S", "A"))]
    hp_candidates.sort(
        key=lambda x: (
            _score(x.get("overall_priority_score"), 0),
            _score(x.get("relevance_score"), 0),
            _score(x.get("quality_score"), 0),
        ),
        reverse=True,
    )

    top = hp_candidates[:target]
    top_ids = set()
    for i, p in enumerate(top):
        pid = p.get("arxiv_id") or p.get("abs_url") or p.get("url") or p.get("title")
        if pid:
            top_ids.add(str(pid))
        p["high_priority"] = True
        p["high_priority_rank"] = i + 1

    for p in papers:
        pid = p.get("arxiv_id") or p.get("abs_url") or p.get("url") or p.get("title")
        if str(pid) in top_ids:
            p.setdefault("high_priority", True)
        else:
            p["high_priority"] = False
            p.pop("high_priority_rank", None)

    return papers


async def generate_daily_brief_zh(
    *,
    target_date: date,
    papers: list[dict],
    max_papers: int = 20,
) -> str:
    """对“高优精选”做串讲式当日简报（中文）。

    - 仅依赖 title/作者/tldr/关键信号，避免塞入过长 abstract
    - 若缺少 key，则返回空字符串（不中断主流程）
    """

    cfg = RemoteLLMConfig()
    if not getattr(cfg, "AZURE_API_KEY", ""):
        return ""

    hp = [p for p in papers if bool(p.get("high_priority"))]
    if not hp:
        hp = [p for p in papers if bool(p.get("keep", True))]
    hp = hp[: int(max_papers)]

    def _short(s: str, n: int = 240) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[:n] + "..."

    lines: list[str] = []
    for i, p in enumerate(hp, 1):
        title = (p.get("title") or "").strip()
        authors = ", ".join([a for a in (p.get("authors") or []) if isinstance(a, str)])
        tldr_zh = (p.get("tldr_zh") or "").strip()
        tldr = (p.get("tldr") or "").strip()
        sig = []
        for k in (p.get("signal_high_keywords") or [])[:6]:
            sig.append(str(k))
        for a in (p.get("signal_notable_authors") or [])[:3]:
            sig.append(f"author:{a}")
        sig_s = ", ".join(sig)
        overall = _score(p.get("overall_priority_score"), 0)
        rel = _score(p.get("relevance_score"), 0)
        qual = _score(p.get("quality_score"), 0)
        desc = tldr_zh or tldr
        lines.append(
            f"[{i}] {title}\n"
            f"- authors: {authors}\n"
            f"- scores: overall={overall:.1f}, rel={rel:.1f}, qual={qual:.1f}\n"
            f"- signals: {sig_s}\n"
            f"- tldr: {_short(desc)}\n"
        )

    prompt = (
        "你是一位资深 AI 研究员，需要把当日高优 arXiv 论文做成‘串讲式简报’，方便快速浏览进展。\n\n"
        "要求：\n"
        "1) 用中文输出，优先写成连贯段落（不要只是逐条罗列）。\n"
        "2) 先给 1 段总览（当日主线 + 趋势），再按 2-4 个主题串讲（每个主题 3-5 句）。\n"
        "3) 明确点出：LLM/MLLM 的 RL（RLHF/RLAIF/RLVF/可验证奖励）、world model / model-based、test-time compute/agent 等你认为最值得关注的线索。\n"
        "4) 尽量指出每条主线的‘方法/设定/可能影响’，避免空话。\n"
        "5) 最后给 3 条阅读建议（先读哪几篇、为什么）。\n\n"
        f"日期：{target_date.isoformat()}\n"
        f"候选论文（共 {len(lines)} 篇，含标题/作者/分数/信号/tldr）：\n\n"
        + "\n".join(lines)
    )

    messages = [
        {"role": "system", "content": "You write concise, information-dense Chinese research briefings."},
        {"role": "user", "content": prompt},
    ]
    txt = await default_chat_completion_text(
        namespace="daily_brief_zh",
        messages=messages,
        max_tokens=4096,
        temperature=0.6,
    )
    return (txt or "").strip()


async def generate_daily_summary_zh(
    *,
    target_date: date,
    papers: list[dict],
    max_papers: int = 20,
) -> str:
    """当日总结（中文）：强调主线、insight、现象发现、关键技术点。"""

    cfg = RemoteLLMConfig()
    if not getattr(cfg, "AZURE_API_KEY", ""):
        return ""

    hp = [p for p in papers if bool(p.get("high_priority"))]
    if not hp:
        hp = [p for p in papers if bool(p.get("keep", True))]
    hp = hp[: int(max_papers)]

    def _short(s: str, n: int = 260) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[:n] + "..."

    lines: list[str] = []
    for i, p in enumerate(hp, 1):
        title = (p.get("title") or "").strip()
        authors = ", ".join([a for a in (p.get("authors") or []) if isinstance(a, str)])
        tldr_zh = (p.get("tldr_zh") or "").strip()
        tldr = (p.get("tldr") or "").strip()
        sig = []
        for k in (p.get("signal_high_keywords") or [])[:6]:
            sig.append(str(k))
        for a in (p.get("signal_notable_authors") or [])[:3]:
            sig.append(f"author:{a}")
        overall = _score(p.get("overall_priority_score"), 0)
        rel = _score(p.get("relevance_score"), 0)
        qual = _score(p.get("quality_score"), 0)
        desc = tldr_zh or tldr
        lines.append(
            f"[{i}] {title}\n"
            f"- authors: {authors}\n"
            f"- scores: overall={overall:.1f}, rel={rel:.1f}, qual={qual:.1f}\n"
            f"- signals: {', '.join(sig)}\n"
            f"- tldr: {_short(desc)}\n"
        )

    prompt = (
        "你是一位资深 AI 研究员，需要对当日 arXiv 高优论文做‘批判性研究总结’，强调真正的技术创新与新发现。\n\n"
        "输出要求：\n"
        "1) 用中文，信息密度高；先 1 段总览（当日主线 + 趋势），再按 2-4 个主题串讲（每个主题 4-6 句）。\n"
        "2) 明确点出：哪些是‘新现象/新 insight/关键机制’，哪些可能只是包装或过于具体；用 ICML/ICLR/NeurIPS 标准批判性评价。\n"
        "3) 尽量写清楚：方法/设定/为什么重要/可能影响与局限，不要空话。\n"
        "4) 末尾给 5 条阅读建议（先读哪几篇、为什么、读时关注哪些点）。\n\n"
        f"日期：{target_date.isoformat()}\n"
        f"候选论文（共 {len(lines)} 篇，含标题/作者/分数/信号/tldr）：\n\n"
        + "\n".join(lines)
    )

    messages = [
        {"role": "system", "content": "You write concise, critical Chinese research summaries."},
        {"role": "user", "content": prompt},
    ]
    txt = await default_chat_completion_text(
        namespace="daily_summary_zh",
        messages=messages,
        max_tokens=8192,
        temperature=0.35,
    )
    return (txt or "").strip()


async def generate_future_ideas_zh(
    *,
    target_date: date,
    papers: list[dict],
    max_papers: int = 20,
) -> str:
    """未来工作 brainstorm（中文）：提出方向、问题定义、可做的实验/理论切入点。"""

    cfg = RemoteLLMConfig()
    if not getattr(cfg, "AZURE_API_KEY", ""):
        return ""

    hp = [p for p in papers if bool(p.get("high_priority"))]
    if not hp:
        hp = [p for p in papers if bool(p.get("keep", True))]
    hp = hp[: int(max_papers)]

    def _short(s: str, n: int = 240) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[:n] + "..."

    lines: list[str] = []
    for i, p in enumerate(hp, 1):
        title = (p.get("title") or "").strip()
        tldr_zh = (p.get("tldr_zh") or "").strip()
        tldr = (p.get("tldr") or "").strip()
        desc = tldr_zh or tldr
        lines.append(f"[{i}] {title}\n- tldr: {_short(desc)}\n")

    prompt = (
        "你是一位资深 AI 研究员，需要基于当日高优论文做‘未来工作 brainstorm’，提出可转化为研究项目的 idea。\n\n"
        "输出要求：\n"
        "1) 给 6-10 个研究 idea，每个 idea 用统一结构：问题/动机 → 核心假设 → 方法路径（可含理论或实验）→ 最小可行实验(MVP) → 预期风险与替代方案。\n"
        "2) 至少覆盖：通用技术创新、重要现象解释/预测、理论切入点、以及可验证的评测/反例构造。\n"
        "3) 避免过于具体场景工程；尽量抽象出可迁移的原则或机制。\n\n"
        f"日期：{target_date.isoformat()}\n"
        "材料（标题 + TLDR）：\n\n"
        + "\n".join(lines)
    )

    messages = [
        {"role": "system", "content": "You propose concrete, technically detailed research ideas in Chinese."},
        {"role": "user", "content": prompt},
    ]
    txt = await default_chat_completion_text(
        namespace="future_ideas_zh",
        messages=messages,
        max_tokens=8192,
        temperature=0.75,
    )
    return (txt or "").strip()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 定义默认目录
DEFAULT_JSON_DIR = os.path.join(PROJECT_ROOT, 'daily_json')
DEFAULT_HTML_DIR = os.path.join(PROJECT_ROOT, 'daily_html')
DEFAULT_TEMPLATE_DIR = os.path.join(PROJECT_ROOT, 'templates')
DEFAULT_TEMPLATE_NAME = 'paper_template.html'


def _parse_csv_list(s: Optional[str]) -> list[str]:
    if not s:
        return []
    out: list[str] = []
    for x in s.split(","):
        x = x.strip()
        if x:
            out.append(x)
    return out


def _install_launchd(*, python_exe: str, main_py: str, project_root: str, hour: int, minute: int) -> str:
    """写入一个 launchd LaunchAgent plist（不自动 load，由用户决定是否启用）。"""
    launch_agents = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(launch_agents, exist_ok=True)

    label = "com.daily_paper.arxiv"
    plist_path = os.path.join(launch_agents, f"{label}.plist")
    log_path = os.path.expanduser("~/Library/Logs/daily_paper_arxiv.log")
    err_path = os.path.expanduser("~/Library/Logs/daily_paper_arxiv.err.log")

    plist = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python_exe}</string>
    <string>{main_py}</string>
  </array>
  <key>WorkingDirectory</key><string>{project_root}</string>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>{int(hour)}</integer>
    <key>Minute</key><integer>{int(minute)}</integer>
  </dict>
  <key>StandardOutPath</key><string>{log_path}</string>
  <key>StandardErrorPath</key><string>{err_path}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <!-- 如需固定环境变量（例如 AZURE_API_KEY / AZURE_ENDPOINT / AZURE_MODEL_NAME），可在此处填写 -->
  </dict>
</dict>
</plist>
"""

    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(plist)
    return plist_path


def _launchctl_load(plist_path: str) -> None:
    """尽量幂等地启用 launchd 任务（先 unload 再 load）。"""
    try:
        subprocess.run(["launchctl", "unload", "-w", plist_path], check=False)
    except Exception:
        pass
    subprocess.run(["launchctl", "load", "-w", plist_path], check=True)


def _llm_smoke_test() -> None:
    cfg = RemoteLLMConfig()
    if not getattr(cfg, "AZURE_API_KEY", ""):
        raise RuntimeError("未检测到 AZURE_API_KEY / OPENAI_API_KEY，请先在当前环境导出后再测试。")

    async def _run() -> None:
        txt = await default_chat_completion_text(
            namespace="smoke_test",
            messages=[
                {"role": "system", "content": "Reply with one short sentence."},
                {"role": "user", "content": "Say 'LLM smoke test ok'."},
            ],
            max_tokens=32,
            temperature=0.0,
        )
        print(txt.strip())

    asyncio.run(_run())

def main(
    *,
    target_date: date,
    keywords: list[str],
    categories: list[str],
    interests: str,
    max_results: int,
    force: bool,
):
    """主执行流程：抓取、粗筛/打分、保存、生成 HTML。"""
    logging.info(f"开始处理日期: {target_date.isoformat()}")

    # --- 确定 JSON 文件路径 ---
    json_filename = f"{target_date.isoformat()}.json"
    json_filepath = os.path.join(DEFAULT_JSON_DIR, json_filename)
    logging.info(f"目标 JSON 文件路径: {json_filepath}")

    if os.path.exists(json_filepath) and not force:
        logging.info(f"找到已存在的 JSON 文件: {json_filepath}。跳过抓取与评分（用 --force 可重跑）。")
    else:
        logging.info("步骤 1: 从 arXiv API 抓取当日论文（关键词检索）...")
        raw_papers = fetch_daily_papers(
            specified_date=target_date,
            keywords=keywords,
            categories=categories,
            max_results=max_results,
        )
        if not raw_papers:
            logging.warning(f"在 {target_date.isoformat()} 未找到论文或抓取失败。")
            return
        logging.info(f"抓取到 {len(raw_papers)} 篇候选论文。")

        logging.info("步骤 2: 调用大模型进行粗筛与评分...")
        rated_papers = rate_papers(raw_papers, interests=interests)

        rated_papers.sort(
            key=lambda x: (
                x.get('overall_priority_score', 0),
                x.get('relevance_score', 0),
                x.get('quality_score', 0),
            ),
            reverse=True,
        )

        # --- 2.5 细化“高优精选”并写回 tier/high_priority 字段 ---
        # 目标：高优控制在 10-20（默认 15，可用环境变量覆盖）
        hp_target = int(os.getenv("DAILY_HIGH_PRIORITY_TARGET", os.getenv("HIGH_PRIORITY_TARGET", "15")) or 15)
        rated_papers = mark_high_priority(rated_papers, target=hp_target)

        logging.info("步骤 3: 保存 JSON（包含评分字段）...")
        # --- 3.1 生成“当日总结 + 未来工作 brainstorm”（仅基于高优精选）---
        daily_summary_zh = ""
        daily_ideas_zh = ""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                async def _gen() -> tuple[str, str]:
                    s, i = await asyncio.gather(
                        generate_daily_summary_zh(target_date=target_date, papers=rated_papers),
                        generate_future_ideas_zh(target_date=target_date, papers=rated_papers),
                    )
                    return (s or ""), (i or "")

                daily_summary_zh, daily_ideas_zh = asyncio.run(_gen())
            except Exception as e:
                logging.warning(f"当日总结/brainstorm 生成失败（忽略，不影响主流程）: {e}")
        else:
            # 理论上 main() 不会在已有 event loop 里跑；这里做防御
            logging.warning("检测到运行中的 event loop，跳过当日总结/brainstorm 生成（避免阻塞）。")

        hp_count = sum(1 for p in rated_papers if bool(p.get("high_priority")))
        kept_count = sum(1 for p in rated_papers if bool(p.get("keep", True)))
        meta = {
            "date": target_date.isoformat(),
            "generated_at": datetime.now().astimezone().isoformat(),
            "total": len(rated_papers),
            "kept": kept_count,
            "high_priority": hp_count,
            "high_priority_target": hp_target,
            # 兼容旧字段：daily_brief_zh 复用“当日总结”
            "daily_brief_zh": daily_summary_zh,
            "daily_summary_zh": daily_summary_zh,
            "daily_ideas_zh": daily_ideas_zh,
        }

        for paper in rated_papers:
            if isinstance(paper.get('published_date'), datetime):
                paper['published_date'] = paper['published_date'].isoformat()
            if isinstance(paper.get('updated_date'), datetime):
                paper['updated_date'] = paper['updated_date'].isoformat()

        os.makedirs(DEFAULT_JSON_DIR, exist_ok=True)
        try:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump({"meta": meta, "papers": rated_papers}, f, indent=2, ensure_ascii=False)
            logging.info(f"论文数据已保存到: {json_filepath}")
        except Exception as e:
            logging.error(f"保存 JSON 时发生错误: {e}", exc_info=True)
            return

    # --- 4. 生成 HTML (无论 JSON 是新建还是已存在) --- #
    logging.info("步骤 4: 从 JSON 文件生成 HTML 报告...")
    # 再次检查 JSON 文件是否实际存在（以防万一）
    if not os.path.exists(json_filepath):
         logging.error(f"无法找到 JSON 文件 '{json_filepath}' 来生成 HTML。")
         return

    try:
        generate_html_from_json(
            json_file_path=json_filepath,
            template_dir=DEFAULT_TEMPLATE_DIR,
            template_name=DEFAULT_TEMPLATE_NAME,
            output_dir=DEFAULT_HTML_DIR,
        )
        logging.info(f"HTML 报告已生成在: {DEFAULT_HTML_DIR}")

        # --- 5. 更新 reports.json --- #
        logging.info("步骤 5: 更新根目录下的 reports.json 文件...")
        reports_json_path = os.path.join(PROJECT_ROOT, 'reports.json')
        try:
            if os.path.exists(DEFAULT_HTML_DIR) and os.path.isdir(DEFAULT_HTML_DIR):
                html_files = [f for f in os.listdir(DEFAULT_HTML_DIR) if f.endswith('.html')]
                # 按文件名（日期）降序排序
                html_files.sort(reverse=True)
                with open(reports_json_path, 'w', encoding='utf-8') as f:
                    json.dump(html_files, f, indent=4, ensure_ascii=False)
                logging.info(f"reports.json 已更新，包含 {len(html_files)} 个报告。")
            else:
                logging.warning(f"HTML 目录 '{DEFAULT_HTML_DIR}' 不存在，无法生成 reports.json。")
                # 如果目录不存在，可以选择创建一个空的 reports.json
                with open(reports_json_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, indent=4, ensure_ascii=False)
                logging.info("已创建空的 reports.json。")
        except Exception as e:
            logging.error(f"更新 reports.json 时发生错误: {e}", exc_info=True)

    except FileNotFoundError:
        logging.error(f"模板文件 '{DEFAULT_TEMPLATE_NAME}' 未在 '{DEFAULT_TEMPLATE_DIR}' 中找到。")
    except Exception as e:
        logging.error(f"生成 HTML 时发生意外错误: {e}", exc_info=True)

    logging.info(f"日期 {target_date.isoformat()} 的处理流程完成。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='抓取并生成 arXiv 每日论文（LLM/RL/World Models/Agents）报告。')
    parser.add_argument(
        '--date',
        type=str,
        help='指定抓取的日期 (YYYY-MM-DD)。如果未指定，当天的 UTC 日期。'
    )

    parser.add_argument(
        '--keywords',
        type=str,
        default=",".join(DEFAULT_ARXIV_KEYWORDS),
        help='关键词列表，逗号分隔。例如: "LLM,Reinforcement Learning,World Models,Agents"',
    )
    parser.add_argument(
        '--categories',
        type=str,
        default=",".join(DEFAULT_CATEGORIES),
        help='arXiv 分类列表，逗号分隔。例如: "cs.AI,cs.LG,cs.CL,stat.ML"。留空表示不限制分类。',
    )
    parser.add_argument(
        '--interests',
        type=str,
        default=DEFAULT_INTERESTS,
        help='用于 relevance 打分的研究兴趣描述（会传给大模型）。',
    )
    parser.add_argument('--max-results', type=int, default=1000, help='arXiv 单次查询最大返回数。')
    parser.add_argument('--force', action='store_true', help='即使 JSON 已存在也强制重新抓取/评分并覆盖。')
    parser.add_argument(
        '--install-launchd',
        action='store_true',
        help='写入 macOS launchd 任务（登录后自动跑 + 每日定时）。',
    )
    parser.add_argument(
        '--enable-launchd',
        action='store_true',
        help='在写入 plist 后自动执行 launchctl load -w 启用（需要用户会话权限）。',
    )
    parser.add_argument('--launchd-hour', type=int, default=9, help='launchd 每日运行小时（本地时区）。')
    parser.add_argument('--launchd-minute', type=int, default=30, help='launchd 每日运行分钟（本地时区）。')
    parser.add_argument(
        '--llm-smoke-test',
        action='store_true',
        help='只做一次 LLM 连通性测试（发起 1 个最小请求后退出）。',
    )

    args = parser.parse_args()

    run_date: date
    if args.date:
        try:
            run_date = datetime.strptime(args.date, '%Y-%m-%d').date()
            logging.info(f"使用用户指定的日期: {run_date.isoformat()}")
        except ValueError:
            logging.error("日期格式无效，请使用 YYYY-MM-DD 格式。退出程序。")
            exit(1)
    else:
        # 未指定日期：使用本地日期（更符合“每天开机自动跑”）
        run_date = datetime.now().astimezone().date()
        logging.info(f"未指定日期，使用默认日期: {run_date.isoformat()}")

    keywords = _parse_csv_list(args.keywords) or DEFAULT_KEYWORDS
    categories = _parse_csv_list(args.categories)

    if args.llm_smoke_test:
        _llm_smoke_test()
        sys.exit(0)

    if args.install_launchd:
        plist_path = _install_launchd(
            python_exe=sys.executable,
            main_py=os.path.abspath(__file__),
            project_root=PROJECT_ROOT,
            hour=args.launchd_hour,
            minute=args.launchd_minute,
        )
        logging.info(f"launchd plist 已写入: {plist_path}")
        if args.enable_launchd:
            _launchctl_load(plist_path)
            logging.info("launchd 已启用（RunAtLoad + 每日定时）。")
        else:
            logging.info("启用命令：`launchctl load -w ~/Library/LaunchAgents/com.daily_paper.arxiv.plist`")

        # 安装调度器后直接退出，避免意外触发一次长耗时的抓取/评分。
        sys.exit(0)

    # 检查过去两天的报告，避免遗漏，并生成当天的报告
    main(
        target_date=run_date - timedelta(days=2),
        keywords=keywords,
        categories=categories,
        interests=args.interests,
        max_results=args.max_results,
        force=args.force,
    )
    main(
        target_date=run_date - timedelta(days=1),
        keywords=keywords,
        categories=categories,
        interests=args.interests,
        max_results=args.max_results,
        force=args.force,
    )
    main(
        target_date=run_date,
        keywords=keywords,
        categories=categories,
        interests=args.interests,
        max_results=args.max_results,
        force=args.force,
    )
