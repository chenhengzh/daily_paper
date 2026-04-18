import json
import os
import logging
import re
from datetime import date, datetime
from html import escape
from typing import Any, Dict, List, Optional


def _score(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _join(xs: Any, sep: str = ", ") -> str:
    if not xs:
        return ""
    if isinstance(xs, list):
        return sep.join([str(x) for x in xs if x is not None and str(x).strip()])
    return str(xs)


def _tier_label(overall: float, relevance: float) -> str:
    # 以 overall 为主，relevance 作为 tie-breaker
    s = overall
    if s >= 8.0 and relevance >= 7.0:
        return "S"
    if s >= 7.0:
        return "A"
    if s >= 6.0:
        return "B"
    return "C"


def generate_html_from_json(json_file_path: str, template_dir: str, template_name: str, output_dir: str):
    """从 JSON 生成一个自包含（无外部模板依赖）的 HTML 报告。

    兼容旧签名：template_dir/template_name 保留但不再需要。
    """
    meta: Dict[str, Any] = {}
    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            # 兼容两种格式：
            # 1) 旧版：直接是 papers 的 list
            # 2) 新版：{"meta": {...}, "papers": [...]}
            if isinstance(raw, list):
                papers = raw
            elif isinstance(raw, dict):
                meta = raw.get("meta") or {}
                papers = raw.get("papers") or []
            else:
                papers = []
    except FileNotFoundError:
        logging.error(f"JSON file not found at {json_file_path}")
        return
    except json.JSONDecodeError:
        logging.error(f"Could not decode JSON from {json_file_path}")
        return

    filename = os.path.basename(json_file_path)
    report_date: Optional[date] = None
    formatted_date = date.today().strftime("%Y_%m_%d")
    try:
        date_str = filename.split(".")[0]
        report_date = date.fromisoformat(date_str)
        formatted_date = report_date.strftime("%Y_%m_%d")
    except Exception:
        report_date = None

    # 排序：keep 优先，其次 overall，再次 relevance/quality
    def _sort_key(p: Dict[str, Any]):
        keep = bool(p.get("keep", True))
        overall = _score(p.get("overall_priority_score"), 0)
        rel = _score(p.get("relevance_score"), 0)
        qual = _score(p.get("quality_score"), 0)
        return (1 if keep else 0, overall, rel, qual)

    papers.sort(key=_sort_key, reverse=True)

    kept = [p for p in papers if bool(p.get("keep", True))]
    dropped = [p for p in papers if not bool(p.get("keep", True))]

    title = f"arXiv 每日论文速览 - {report_date.isoformat() if report_date else filename}"
    gen_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def _paper_id(p: Dict[str, Any]) -> str:
        return str(p.get("arxiv_id") or p.get("abs_url") or p.get("url") or p.get("title") or "")


    def _safe_json_in_script(obj: Any) -> str:
        """将 JSON 安全嵌入 <script>，避免出现 </script> 提前闭合。"""
        s = json.dumps(obj, ensure_ascii=False)
        return s.replace("</", "<\\/")


    def _md_to_safe_html(md: str) -> str:
        """把 Markdown 渲染成安全的 HTML（非常保守的子集）。

        目标：让 LLM 输出的 markdown 在页面可读，同时避免 XSS。
        支持：标题、粗体、斜体、行内代码、代码块、列表、分隔线、链接。
        注意：所有 HTML 都会先 escape，再做少量替换，因此不会执行任意 HTML。
        """

        s = (md or "").strip("\n")
        if not s:
            return ""

        lines = s.split("\n")
        out: list[str] = []
        in_code = False
        code_buf: list[str] = []

        def _flush_code() -> None:
            nonlocal code_buf
            if not code_buf:
                out.append('<pre class="md-code"><code></code></pre>')
                return
            code = "\n".join(code_buf)
            out.append(f'<pre class="md-code"><code>{escape(code)}</code></pre>')
            code_buf = []

        def _inline_format(text: str) -> str:
            # 先 escape，确保任何 HTML 都不会被执行
            t = escape(text)
            # links: [text](url)
            t = re.sub(
                r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                lambda m: f'<a href="{escape(m.group(2))}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>',
                t,
            )
            # inline code
            t = re.sub(r"`([^`]+)`", r"<code class=\"md-inline-code\">\1</code>", t)
            # bold / italic（简单处理，避免复杂嵌套）
            t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
            t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
            return t

        # block parsing
        for raw in lines:
            line = raw.rstrip("\r")
            if line.strip().startswith("```"):
                if in_code:
                    in_code = False
                    _flush_code()
                else:
                    in_code = True
                    code_buf = []
                continue

            if in_code:
                code_buf.append(line)
                continue

            if re.match(r"^\s*---\s*$", line):
                out.append("<hr />")
                continue

            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                lvl = len(m.group(1))
                out.append(f"<h{lvl} class=\"md-h{lvl}\">{_inline_format(m.group(2))}</h{lvl}>")
                continue

            m2 = re.match(r"^\s*[-*]\s+(.*)$", line)
            if m2:
                # 简化：每行一个 li（不做嵌套合并），足够可读
                out.append(f"<div class=\"md-li\">• {_inline_format(m2.group(1))}</div>")
                continue

            if not line.strip():
                out.append('<div class="md-sp"></div>')
                continue

            out.append(f"<p class=\"md-p\">{_inline_format(line)}</p>")

        if in_code:
            _flush_code()

        return "\n".join(out)

    # --- 高优精选：默认只展示一份（避免在 S/A/B/C 里重复）---
    # 高优精选：展示层面只取 S/A，避免出现 B 档仍被标为“高优”
    high_priority = [
        p
        for p in kept
        if bool(p.get("high_priority"))
        and ((p.get("tier") or "").strip() in ("S", "A"))
    ]

    if not high_priority:
        # 兼容旧 JSON：没有 high_priority 字段时，按分数取 top-N 做前置展示
        try:
            hp_target = int((meta or {}).get("high_priority_target") or 15)
        except Exception:
            hp_target = 15
        hp_target = max(10, min(20, hp_target))
        tmp = sorted(
            [p for p in kept if ((p.get("tier") or "").strip() in ("S", "A"))],
            key=lambda x: (
                _score(x.get("overall_priority_score"), 0),
                _score(x.get("relevance_score"), 0),
                _score(x.get("quality_score"), 0),
            ),
            reverse=True,
        )
        high_priority = tmp[:hp_target]
        for i, p in enumerate(high_priority, 1):
            p.setdefault("high_priority", True)
            p.setdefault("high_priority_rank", i)
    high_priority.sort(
        key=lambda x: (
            int(x.get("high_priority_rank") or 10**9),
            -_score(x.get("overall_priority_score"), 0),
        )
    )

    # 重新编号：避免因为过滤（例如剔除 B 档）导致 rank 出现空洞
    for i, p in enumerate(high_priority, 1):
        p["high_priority"] = True
        p["high_priority_rank"] = i
    picked_ids = {_paper_id(p) for p in high_priority if _paper_id(p)}
    kept_rest = [p for p in kept if _paper_id(p) not in picked_ids]

    # 分组渲染：按 tier（对非精选部分）
    groups: Dict[str, List[Dict[str, Any]]] = {"S": [], "A": [], "B": [], "C": []}
    for p in kept_rest:
        tier = (p.get("tier") or "").strip() or _tier_label(
            _score(p.get("overall_priority_score"), 0),
            _score(p.get("relevance_score"), 0),
        )
        groups.setdefault(tier, []).append(p)

    # --- 数据下发：避免一次性渲染大量 DOM 导致浏览器卡死/崩溃 ---
    # 设计：
    # - HTML 初始只输出骨架 + 少量统计
    # - 论文卡片由 JS 分批渲染（并使用 content-visibility 降低 layout/paint 成本）
    paper_map: Dict[str, Dict[str, Any]] = {}
    used_keys: Dict[str, int] = {}

    def _paper_key(p: Dict[str, Any]) -> str:
        base = _paper_id(p) or (p.get("title") or "")
        base = str(base).strip() or "paper"
        n = used_keys.get(base, 0) + 1
        used_keys[base] = n
        return base if n == 1 else f"{base}#{n}"

    def _pack_paper(p: Dict[str, Any], key: str) -> Dict[str, Any]:
        abs_url = p.get("abs_url") or p.get("url") or ""
        pdf_url = p.get("pdf_url") or ""

        overall = _score(p.get("overall_priority_score"), 0)
        rel = _score(p.get("relevance_score"), 0)
        qual = _score(p.get("quality_score"), 0)
        nov = _score(p.get("novelty_claim_score"), 0)
        imp = _score(p.get("potential_impact_score"), 0)
        tier = (p.get("tier") or "").strip() or _tier_label(overall, rel)

        tags = p.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        i_field = (p.get("interest_field") or "").strip()
        i_sub = (p.get("interest_subfield") or "").strip()
        if i_field and i_sub:
            tags = [f"{i_field} / {i_sub}"] + tags

        raw_tldr = (p.get("tldr") or "").strip()
        raw_tldr_zh = (p.get("tldr_zh") or "").strip()
        abstract_raw = (p.get("summary") or "").strip()
        if not raw_tldr_zh and not raw_tldr and abstract_raw:
            raw_tldr_zh = abstract_raw[:220] + ("..." if len(abstract_raw) > 220 else "")

        return {
            "key": key,
            "title": (p.get("title") or "").strip(),
            "authors": p.get("authors") or [],
            "categories": p.get("categories") or [],
            "abs_url": abs_url,
            "pdf_url": pdf_url,
            "scores": {
                "overall": float(overall),
                "rel": float(rel),
                "qual": float(qual),
                "nov": float(nov),
                "impact": float(imp),
            },
            "tier": tier,
            "high_priority": bool(p.get("high_priority")),
            "high_priority_rank": p.get("high_priority_rank"),
            "tags": [str(t) for t in tags[:10]],
            "tldr": raw_tldr,
            "tldr_zh": raw_tldr_zh,
            "keep_reason": (p.get("keep_reason") or "").strip(),
            "interest_match_reason": (p.get("interest_match_reason") or "").strip(),
            "abstract": abstract_raw,
        }

    # 只把会展示的论文下发到前端（dropped 默认仅取前 200）
    dropped_preview = dropped[:200]
    all_for_ui = list(high_priority) + list(kept_rest) + list(dropped_preview)
    for p in all_for_ui:
        k = _paper_key(p)
        # 写回一个仅用于本次 HTML 生成的临时 key，避免重复生成导致错乱
        p["_ui_key"] = k
        paper_map[k] = _pack_paper(p, k)

    sections = {
        "hp": [str(p.get("_ui_key")) for p in high_priority if p.get("_ui_key")],
        "S": [str(p.get("_ui_key")) for p in groups.get("S", []) if p.get("_ui_key")],
        "A": [str(p.get("_ui_key")) for p in groups.get("A", []) if p.get("_ui_key")],
        "B": [str(p.get("_ui_key")) for p in groups.get("B", []) if p.get("_ui_key")],
        "C": [str(p.get("_ui_key")) for p in groups.get("C", []) if p.get("_ui_key")],
        "dropped": [str(p.get("_ui_key")) for p in dropped_preview if p.get("_ui_key")],
    }

    css = """
    :root {
      /* Light theme (default) */
      --bg-primary: #f8fafc;
      --bg-secondary: #ffffff;
      --bg-card: #ffffff;
      --bg-card-hover: #f1f5f9;
      --text-primary: #0f172a;
      --text-secondary: #334155;
      --text-muted: #64748b;
      --border-light: rgba(15, 23, 42, 0.10);
      --border-accent: rgba(79, 70, 229, 0.25);
      --accent-blue: #4f46e5;
      --accent-purple: #7c3aed;
      --accent-cyan: #0891b2;
      --accent-green: #16a34a;
      --accent-amber: #d97706;
      --accent-rose: #e11d48;
      --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.06);
      --shadow-md: 0 10px 24px rgba(15, 23, 42, 0.08);
      --shadow-lg: 0 16px 40px rgba(15, 23, 42, 0.10);
      --shadow-glow: 0 0 32px rgba(79, 70, 229, 0.10);
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 16px;
      --radius-xl: 24px;
    }

    * { box-sizing: border-box; }

    html {
      font-size: 16px;
      scroll-behavior: smooth;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg-primary);
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    body::before { content: none; }

    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 40px 32px 80px;
    }

    /* Header */
    .header {
      margin-bottom: 48px;
    }

    .header-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      flex-wrap: wrap;
    }

    .header-info h1 {
      margin: 0 0 12px 0;
      font-size: 32px;
      font-weight: 700;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, var(--text-primary) 0%, var(--accent-blue) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .header-meta {
      display: flex;
      align-items: center;
      gap: 16px;
      color: var(--text-secondary);
      font-size: 14px;
    }

    .header-meta span {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .header-meta svg {
      width: 16px;
      height: 16px;
      opacity: 0.7;
    }

    /* Stats */
    .stats {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .stat-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 16px 24px;
      background: var(--bg-card);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-lg);
      backdrop-filter: none;
      min-width: 100px;
    }

    .stat-value {
      font-size: 28px;
      font-weight: 700;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .stat-label {
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-top: 4px;
    }

    /* Section */
    .sec {
      margin-top: 48px;
    }

    .sec-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border-light);
    }

    .sec h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: -0.3px;
    }

    .sec-count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 28px;
      height: 28px;
      padding: 0 10px;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      color: white;
    }

    .sec-desc {
      font-size: 13px;
      color: var(--text-muted);
      margin-left: auto;
    }

    /* Grid */
    .grid {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .sec-actions {
      margin-top: 16px;
      display: flex;
      justify-content: center;
    }

    .btn {
      appearance: none;
      border: 1px solid var(--border-light);
      background: rgba(15, 23, 42, 0.04);
      color: var(--text-secondary);
      border-radius: 999px;
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }

    .btn:hover {
      border-color: var(--border-accent);
      background: rgba(15, 23, 42, 0.06);
      color: var(--text-primary);
    }

    /* Card */
    .card {
      position: relative;
      background: var(--bg-card);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-xl);
      padding: 24px;
      backdrop-filter: none;
      box-shadow: var(--shadow-md);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      overflow: hidden;
      /* 性能：长列表时减少 layout/paint，避免 Chrome 打开大报告崩溃 */
      content-visibility: auto;
      contain: content;
      contain-intrinsic-size: 260px 520px;
    }

    .card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
    }

    .card:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-accent);
      box-shadow: var(--shadow-lg), var(--shadow-glow);
      transform: translateY(-2px);
    }

    .card[data-tier="S"] { border-left: 4px solid var(--accent-amber); }
    .card[data-tier="A"] { border-left: 4px solid var(--accent-green); }
    .card[data-tier="B"] { border-left: 4px solid var(--accent-cyan); }
    .card[data-tier="C"] { border-left: 4px solid var(--text-muted); }

    /* Card Header */
    .card-h {
      display: flex;
      gap: 16px;
      align-items: flex-start;
    }

    /* Tier Badge */
    .tier {
      width: 44px;
      height: 44px;
      border-radius: var(--radius-md);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 800;
      flex-shrink: 0;
      letter-spacing: -0.5px;
    }

    .card[data-tier="S"] .tier {
      background: linear-gradient(135deg, rgba(251, 191, 36, 0.2), rgba(245, 158, 11, 0.15));
      border: 1px solid rgba(251, 191, 36, 0.4);
      color: var(--accent-amber);
      box-shadow: 0 0 20px rgba(251, 191, 36, 0.2);
    }

    .card[data-tier="A"] .tier {
      background: linear-gradient(135deg, rgba(52, 211, 153, 0.2), rgba(16, 185, 129, 0.15));
      border: 1px solid rgba(52, 211, 153, 0.4);
      color: var(--accent-green);
      box-shadow: 0 0 20px rgba(52, 211, 153, 0.2);
    }

    .card[data-tier="B"] .tier {
      background: linear-gradient(135deg, rgba(34, 211, 238, 0.2), rgba(6, 182, 212, 0.15));
      border: 1px solid rgba(34, 211, 238, 0.4);
      color: var(--accent-cyan);
      box-shadow: 0 0 20px rgba(34, 211, 238, 0.2);
    }

    .card[data-tier="C"] .tier {
      background: linear-gradient(135deg, rgba(100, 116, 139, 0.2), rgba(71, 85, 105, 0.15));
      border: 1px solid rgba(100, 116, 139, 0.4);
      color: var(--text-muted);
    }

    /* Title Section */
    .title {
      flex: 1;
      min-width: 0;
    }

    .paper-title {
      font-size: 18px;
      font-weight: 600;
      line-height: 1.4;
      color: var(--text-primary);
      margin-bottom: 8px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .meta {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      font-size: 13px;
      color: var(--text-muted);
    }

    .meta-authors {
      color: var(--text-secondary);
    }

    .meta-sep {
      opacity: 0.4;
    }

    .meta a {
      color: var(--accent-blue);
      text-decoration: none;
      font-weight: 500;
      transition: color 0.2s;
    }

    .meta a:hover {
      color: var(--accent-purple);
      text-decoration: underline;
    }

    /* Scores */
    .scores {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
      flex-shrink: 0;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      background: rgba(15, 23, 42, 0.04);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-sm);
      transition: all 0.2s;
    }

    .badge:hover {
      background: rgba(15, 23, 42, 0.06);
      border-color: var(--border-accent);
    }

    .badge-label {
      color: var(--text-muted);
      font-weight: 400;
    }

    .badge-value {
      font-weight: 600;
      color: var(--text-primary);
    }

    /* High Priority badge */
    .hp {
      display: inline-flex;
      align-items: center;
      padding: 3px 10px;
      font-size: 12px;
      font-weight: 600;
      color: #ffffff;
      background: linear-gradient(135deg, var(--accent-amber), #f59e0b);
      border-radius: 999px;
      border: 1px solid rgba(251, 191, 36, 0.35);
    }

    /* Brief & Charts */
    .brief {
      margin-top: 24px;
      padding: 20px 22px;
      background: rgba(8, 145, 178, 0.06);
      border: 1px solid rgba(8, 145, 178, 0.14);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-sm);
    }

    .brief-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 16px;
      font-weight: 700;
      color: var(--accent-cyan);
      margin-bottom: 10px;
    }

    .brief-body {
      color: var(--text-primary);
      font-size: 14px;
      line-height: 1.8;
      white-space: pre-wrap;
    }

    /* Markdown rendering (safe subset) */
    .brief-body.md { white-space: normal; }
    .brief-body.md .md-sp { height: 10px; }
    .brief-body.md .md-p { margin: 10px 0; }
    .brief-body.md .md-li { margin: 6px 0 6px 4px; }
    .brief-body.md .md-h1, .brief-body.md .md-h2, .brief-body.md .md-h3,
    .brief-body.md .md-h4, .brief-body.md .md-h5, .brief-body.md .md-h6 {
      margin: 14px 0 8px;
      line-height: 1.25;
      letter-spacing: -0.2px;
      color: var(--text-primary);
    }
    .brief-body.md .md-h1 { font-size: 18px; }
    .brief-body.md .md-h2 { font-size: 16px; }
    .brief-body.md .md-h3 { font-size: 15px; }
    .brief-body.md .md-inline-code {
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 12px;
      padding: 2px 6px;
      border-radius: 6px;
      background: rgba(15, 23, 42, 0.05);
      border: 1px solid var(--border-light);
    }
    .brief-body.md .md-code {
      margin: 12px 0;
      padding: 12px;
      background: rgba(15, 23, 42, 0.04);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-md);
      overflow: auto;
    }
    .brief-body.md .md-code code {
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 12px;
      line-height: 1.6;
      color: var(--text-secondary);
      white-space: pre;
    }
    .brief-body.md a { color: var(--accent-blue); text-decoration: none; }
    .brief-body.md a:hover { text-decoration: underline; }

    .charts {
      margin-top: 20px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }

    .chart {
      padding: 18px 18px;
      background: rgba(148, 163, 184, 0.06);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-xl);
    }

    .chart h3 {
      margin: 0 0 10px 0;
      font-size: 14px;
      color: var(--text-secondary);
      font-weight: 700;
      letter-spacing: 0.2px;
    }

    .bar-row {
      display: grid;
      grid-template-columns: 1fr 4fr auto;
      gap: 10px;
      align-items: center;
      margin: 8px 0;
    }

    .bar-label {
      color: var(--text-secondary);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .bar {
      width: 100%;
      height: 10px;
      background: rgba(148, 163, 184, 0.10);
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 999px;
      overflow: hidden;
    }

    .bar-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
    }

    .bar-val {
      color: var(--text-muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }

    /* Tags */
    .tags {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 16px;
      padding-left: 60px;
    }

    .tag {
      display: inline-flex;
      align-items: center;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 500;
      color: var(--accent-purple);
      background: rgba(139, 92, 246, 0.1);
      border: 1px solid rgba(139, 92, 246, 0.25);
      border-radius: 999px;
      transition: all 0.2s;
    }

    .tag:hover {
      background: rgba(139, 92, 246, 0.18);
      border-color: rgba(139, 92, 246, 0.4);
    }

    /* TLDR */
    .tldr {
      margin-top: 16px;
      padding-left: 60px;
      color: var(--text-secondary);
      font-size: 14px;
      line-height: 1.7;
    }

    .tldr.zh {
      color: var(--text-primary);
      opacity: 0.95;
      margin-top: 8px;
      padding: 12px 16px;
      background: rgba(79, 70, 229, 0.06);
      border-left: 3px solid var(--accent-blue);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    }

    /* Details */
    .details {
      margin-top: 16px;
      padding-left: 60px;
      border-top: 1px dashed var(--border-light);
      padding-top: 16px;
    }

    summary {
      cursor: pointer;
      color: var(--text-muted);
      font-size: 13px;
      font-weight: 500;
      padding: 4px 0;
      transition: color 0.2s;
      outline: none;
    }

    summary:hover {
      color: var(--accent-blue);
    }

    summary::-webkit-details-marker {
      display: none;
    }

    summary::before {
      content: '▶';
      display: inline-block;
      margin-right: 8px;
      font-size: 10px;
      transition: transform 0.2s;
    }

    details[open] > summary::before {
      transform: rotate(90deg);
    }

    .details-body {
      margin-top: 16px;
    }

    .keep-reason {
      padding: 12px 16px;
      margin-bottom: 12px;
      background: rgba(8, 145, 178, 0.06);
      border: 1px solid rgba(8, 145, 178, 0.14);
      border-radius: var(--radius-md);
      font-size: 13px;
      color: var(--text-secondary);
      line-height: 1.6;
    }

    .keep-reason b {
      color: var(--accent-cyan);
      font-weight: 600;
    }

    pre.abstract {
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(15, 23, 42, 0.04);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-md);
      padding: 16px;
      color: var(--text-secondary);
      font-size: 13px;
      line-height: 1.7;
      margin: 0;
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    }

    /* Dropped Section */
    .dropped-info {
      padding: 16px 20px;
      background: rgba(225, 29, 72, 0.06);
      border: 1px solid rgba(225, 29, 72, 0.14);
      border-radius: var(--radius-md);
      font-size: 13px;
      color: var(--text-secondary);
      margin-bottom: 16px;
    }

    .small {
      font-size: 13px;
      color: var(--text-muted);
    }

    /* Responsive */
    @media (max-width: 768px) {
      .wrap {
        padding: 24px 16px 60px;
      }

      .header-top {
        flex-direction: column;
      }

      .header-info h1 {
        font-size: 24px;
      }

      .stats {
        width: 100%;
        justify-content: space-between;
      }

      .stat-item {
        flex: 1;
        min-width: 80px;
        padding: 12px 16px;
      }

      .stat-value {
        font-size: 22px;
      }

      .card {
        padding: 16px;
      }

      .card-h {
        flex-direction: column;
        gap: 12px;
      }

      .tier {
        width: 36px;
        height: 36px;
        font-size: 16px;
      }

      .paper-title {
        font-size: 16px;
      }

      .scores {
        justify-content: flex-start;
        margin-top: 8px;
      }

      .tags, .tldr, .details {
        padding-left: 0;
      }

      .sec-header {
        flex-wrap: wrap;
      }

      .sec-desc {
        width: 100%;
        margin-top: 8px;
        margin-left: 0;
      }
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }

    ::-webkit-scrollbar-track {
      background: var(--bg-primary);
    }

    ::-webkit-scrollbar-thumb {
      background: var(--text-muted);
      border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
      background: var(--text-secondary);
    }

    /* Selection */
    ::selection {
      background: rgba(99, 102, 241, 0.3);
      color: var(--text-primary);
    }
    """

    def render_section(label: str, section_key: str, count: int, desc: str = "") -> str:
        if count <= 0:
            return ""
        desc_html = f'<span class="sec-desc">{escape(desc)}</span>' if desc else ""
        return f"""<div class="sec" data-sec="{escape(section_key)}">
          <div class="sec-header">
            <h2>{escape(label)}</h2>
            <span class="sec-count">{int(count)}</span>
            {desc_html}
          </div>
          <div class="grid" id="grid-{escape(section_key)}"></div>
          <div class="sec-actions"><button class="btn" data-load-more="{escape(section_key)}">加载更多</button></div>
        </div>"""

    def _top_counts(items: List[str], topk: int = 10) -> List[tuple[str, int]]:
        m: Dict[str, int] = {}
        for x in items:
            if not x:
                continue
            m[x] = m.get(x, 0) + 1
        pairs = sorted(m.items(), key=lambda kv: kv[1], reverse=True)
        return pairs[: int(topk)]

    def render_bar_chart(title: str, pairs: List[tuple[str, int]]) -> str:
        if not pairs:
            return ""
        max_v = max(v for _, v in pairs) or 1
        rows = []
        for k, v in pairs:
            w = int(round(100.0 * float(v) / float(max_v)))
            rows.append(
                f'<div class="bar-row">'
                f'<div class="bar-label">{escape(str(k))}</div>'
                f'<div class="bar"><div class="bar-fill" style="width:{w}%"></div></div>'
                f'<div class="bar-val">{int(v)}</div>'
                f'</div>'
            )
        return f'<div class="chart"><h3>{escape(title)}</h3>{"".join(rows)}</div>'

    # --- 汇总统计（用于图表）---
    tier_labels: List[str] = []
    for p in kept:
        t = (p.get("tier") or "").strip()
        if not t:
            t = _tier_label(_score(p.get("overall_priority_score"), 0), _score(p.get("relevance_score"), 0))
        tier_labels.append(t)
    tier_pairs = _top_counts(tier_labels, topk=10)

    fields = []
    for p in kept:
        f1 = (p.get("interest_field") or "").strip()
        if f1:
            fields.append(f1)
    field_pairs = _top_counts(fields, topk=10)

    cats = []
    for p in kept:
        c = p.get("categories")
        if isinstance(c, list) and c:
            cats.append(str(c[0]))
    cat_pairs = _top_counts(cats, topk=10)

    # “当日总结/未来工作 brainstorm”
    summary_zh = ""
    ideas_zh = ""
    if isinstance(meta, dict):
        summary_zh = (meta.get("daily_summary_zh") or meta.get("daily_brief_zh") or "").strip()
        ideas_zh = (meta.get("daily_ideas_zh") or "").strip()

    brief_html = ""
    if summary_zh:
        brief_html += f'<div class="brief"><div class="brief-title">当日总结</div><div class="brief-body md">{_md_to_safe_html(summary_zh)}</div></div>'
    if ideas_zh:
        brief_html += f'<div class="brief"><div class="brief-title">未来工作（Brainstorm）</div><div class="brief-body md">{_md_to_safe_html(ideas_zh)}</div></div>'

    charts_html = ""
    if kept:
        charts = []
        charts.append(render_bar_chart("Tier 分布（保留）", tier_pairs))
        charts.append(render_bar_chart("研究方向（interest_field）Top", field_pairs))
        charts.append(render_bar_chart("arXiv 主分类 Top", cat_pairs))
        charts = [c for c in charts if c]
        if charts:
            charts_html = f'<div class="brief"><div class="brief-title">当日汇总</div><div class="charts">{"".join(charts)}</div></div>'

    # NOTE: raw string to avoid Python interpreting JS regex escapes (e.g. \/)
    js = r"""
      (() => {
        const paperDataEl = document.getElementById('papers-data');
        const sectionsEl = document.getElementById('sections-data');
        if (!paperDataEl || !sectionsEl) return;

        /** @type {Record<string, any>} */
        const PAPERS = JSON.parse(paperDataEl.textContent || '{}');
        /** @type {Record<string, string[]>} */
        const SECTIONS = JSON.parse(sectionsEl.textContent || '{}');

        const state = {};
        const DEFAULT_BATCH = 30;

        function el(tag, className, text) {
          const e = document.createElement(tag);
          if (className) e.className = className;
          if (text != null && text !== '') e.textContent = String(text);
          return e;
        }

        function join(arr, sep) {
          if (!Array.isArray(arr) || arr.length === 0) return '';
          return arr.map(x => (x == null ? '' : String(x).trim())).filter(Boolean).join(sep || ', ');
        }

        function renderPaperCard(p) {
          const card = el('div', 'card');
          card.dataset.tier = (p.tier || 'C');

          const head = el('div', 'card-h');
          const tier = el('div', 'tier', p.tier || 'C');

          const titleWrap = el('div', 'title');
          titleWrap.appendChild(el('div', 'paper-title', p.title || ''));

          const meta = el('div', 'meta');
          const authors = join(p.authors, ', ');
          if (authors) meta.appendChild(el('span', 'meta-authors', authors));

          const cats = join(p.categories, ', ');
          if (cats) {
            meta.appendChild(el('span', 'meta-sep', '·'));
            meta.appendChild(el('span', '', cats));
          }

          function alphaUrl(u) {
            if (!u) return '';
            return String(u).replace(/^https?:\/\/arxiv\.org\/abs\//, 'https://www.alphaxiv.org/abs/');
          }

          const links = [];
          if (p.abs_url) links.push({ href: p.abs_url, text: 'arXiv' });
          const ax = alphaUrl(p.abs_url);
          if (ax && ax !== p.abs_url) links.push({ href: ax, text: 'AlphaXiv' });
          if (links.length) {
            meta.appendChild(el('span', 'meta-sep', '·'));
            const linkWrap = el('span', '');
            links.forEach((l, i) => {
              if (i > 0) linkWrap.appendChild(document.createTextNode(' · '));
              const a = document.createElement('a');
              a.href = l.href;
              a.target = '_blank';
              a.rel = 'noopener noreferrer';
              a.textContent = l.text;
              linkWrap.appendChild(a);
            });
            meta.appendChild(linkWrap);
          }

          if (p.high_priority) {
            meta.appendChild(el('span', 'meta-sep', '·'));
            const badgeText = (Number.isInteger(p.high_priority_rank) && p.high_priority_rank > 0) ? `#${p.high_priority_rank}` : '精选';
            meta.appendChild(el('span', 'hp', badgeText));
          }

          titleWrap.appendChild(meta);

          const scores = el('div', 'scores');
          const s = p.scores || {};
          const scoreItems = [
            ['overall', s.overall],
            ['rel', s.rel],
            ['qual', s.qual],
            ['nov', s.nov],
            ['impact', s.impact],
          ];
          scoreItems.forEach(([k, v]) => {
            const badge = el('span', 'badge');
            badge.appendChild(el('span', 'badge-label', k));
            const val = (typeof v === 'number' && Number.isFinite(v)) ? v.toFixed(1) : '0.0';
            badge.appendChild(el('span', 'badge-value', val));
            scores.appendChild(badge);
          });

          head.appendChild(tier);
          head.appendChild(titleWrap);
          head.appendChild(scores);
          card.appendChild(head);

          const tags = el('div', 'tags');
          (Array.isArray(p.tags) ? p.tags : []).slice(0, 10).forEach(t => {
            tags.appendChild(el('span', 'tag', t));
          });
          card.appendChild(tags);

          if (p.tldr) card.appendChild(el('div', 'tldr', p.tldr));
          if (p.tldr_zh) {
            const t = el('div', 'tldr zh', p.tldr_zh);
            card.appendChild(t);
          }

          const details = document.createElement('details');
          details.className = 'details';
          const summary = document.createElement('summary');
          summary.textContent = 'Abstract / 筛选理由';
          details.appendChild(summary);
          const body = el('div', 'details-body');
          details.appendChild(body);
          details.addEventListener('toggle', () => {
            if (!details.open) return;
            if (body.dataset.loaded === '1') return;
            body.dataset.loaded = '1';
            if (p.keep_reason) {
              const kr = el('div', 'keep-reason');
              const b = document.createElement('b');
              b.textContent = 'Keep reason:';
              kr.appendChild(b);
              kr.appendChild(document.createTextNode(' ' + p.keep_reason));
              body.appendChild(kr);
            }
            if (p.interest_match_reason) {
              const ir = el('div', 'keep-reason');
              const b2 = document.createElement('b');
              b2.textContent = 'Interest match:';
              ir.appendChild(b2);
              ir.appendChild(document.createTextNode(' ' + p.interest_match_reason));
              body.appendChild(ir);
            }
            if (p.abstract) {
              const pre = el('pre', 'abstract');
              pre.textContent = p.abstract;
              body.appendChild(pre);
            }
          });
          card.appendChild(details);

          return card;
        }

        function renderMore(sectionKey, n) {
          const keys = SECTIONS[sectionKey] || [];
          const grid = document.getElementById(`grid-${sectionKey}`);
          if (!grid) return;
          const st = state[sectionKey] || { i: 0 };
          const batch = Math.max(1, n || DEFAULT_BATCH);
          const end = Math.min(keys.length, st.i + batch);
          const frag = document.createDocumentFragment();
          for (let idx = st.i; idx < end; idx++) {
            const k = keys[idx];
            const p = PAPERS[k];
            if (!p) continue;
            frag.appendChild(renderPaperCard(p));
          }
          grid.appendChild(frag);
          st.i = end;
          state[sectionKey] = st;

          const btn = document.querySelector(`[data-load-more="${CSS.escape(sectionKey)}"]`);
          if (btn) {
            const left = keys.length - st.i;
            btn.textContent = left > 0 ? `加载更多（剩余 ${left}）` : '已加载全部';
            btn.disabled = left <= 0;
            btn.style.opacity = left <= 0 ? '0.5' : '1';
          }
        }

        document.querySelectorAll('[data-load-more]').forEach(btn => {
          btn.addEventListener('click', () => {
            const key = btn.getAttribute('data-load-more');
            if (!key) return;
            renderMore(key, DEFAULT_BATCH);
          });
        });

        // 初次渲染：每个区块先渲染一小批，避免打开页面瞬间卡死
        ['hp', 'S', 'A', 'B', 'C', 'dropped'].forEach(k => {
          if (!Array.isArray(SECTIONS[k]) || SECTIONS[k].length === 0) {
            const btn = document.querySelector(`[data-load-more="${CSS.escape(k)}"]`);
            if (btn) btn.style.display = 'none';
            return;
          }
          const init = (k === 'hp') ? 20 : (k === 'dropped' ? 30 : 25);
          renderMore(k, init);
        });
      })();
    """

    html = f"""
    <!doctype html>
    <html lang="zh">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>{escape(title)}</title>
      <style>{css}</style>
      <script type="application/json" id="papers-data">{_safe_json_in_script(paper_map)}</script>
      <script type="application/json" id="sections-data">{_safe_json_in_script(sections)}</script>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <div class="header-top">
            <div class="header-info">
              <h1>{escape(title)}</h1>
              <div class="header-meta">
                <span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                  {escape(gen_time)}
                </span>
                <span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                  数据源: arXiv API
                </span>
              </div>
            </div>
            <div class="stats">
              <div class="stat-item">
                <div class="stat-value">{len(papers)}</div>
                <div class="stat-label">总数</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{len(kept)}</div>
                <div class="stat-label">保留</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{len(dropped)}</div>
                <div class="stat-label">丢弃</div>
              </div>
            </div>
          </div>
        </div>
        {brief_html}
        {charts_html}
        {render_section('高优精选', 'hp', len(sections.get('hp') or []), '控制在 10-20 篇，建议优先阅读')}
        {render_section('S 级', 'S', len(sections.get('S') or []), '强相关 + 高质量，优先阅读')}
        {render_section('A 级', 'A', len(sections.get('A') or []), '值得看，建议快速浏览')}
        {render_section('B 级', 'B', len(sections.get('B') or []), '可挑选，按兴趣取舍')}
        {render_section('C 级', 'C', len(sections.get('C') or []), '低优先级，备用')}
        <div class="sec">
          <div class="sec-header">
            <h2>被丢弃的论文</h2>
            <span class="sec-count">{len(dropped)}</span>
            <span class="sec-desc">keep=false</span>
          </div>
          <div class="dropped-info">默认折叠显示。若你希望也纳入报告，可以在 main.py 调整 keep 策略。</div>
          <details class="details"><summary>展开查看</summary>
            <div class="grid" id="grid-dropped"></div>
            <div class="sec-actions"><button class="btn" data-load-more="dropped">加载更多</button></div>
          </details>
        </div>
      </div>
      <script>{js}</script>
    </body>
    </html>
    """

    os.makedirs(output_dir, exist_ok=True)
    output_filepath = os.path.join(output_dir, f"{formatted_date}.html")
    try:
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(html)
        logging.info(f"Successfully generated HTML: {output_filepath}")
    except IOError as e:
        logging.error(f"Error writing HTML file {output_filepath}: {e}")

# Example usage (for testing purposes):
if __name__ == '__main__':
    # Create dummy data and directories for local testing
    dummy_papers = [
        {
            "title": "Awesome Paper 1 on Image Generation",
            "summary": "This paper introduces a revolutionary technique for generating images...",
            "authors": ["Author A", "Author B"],
            "url": "https://arxiv.org/pdf/2301.00001"
        },
        {
            "title": "Video Generation with Diffusion Models",
            "summary": "Exploring the use of diffusion models for high-fidelity video generation...",
            "authors": ["Author C"],
            "url": "https://arxiv.org/pdf/2301.00002"
        }
    ]
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dummy_json_dir = os.path.join(project_root, 'daily_json')
    dummy_html_dir = os.path.join(project_root, 'daily_html')
    dummy_template_dir = os.path.join(project_root, 'templates')
    dummy_template_name = 'paper_template.html'

    os.makedirs(dummy_json_dir, exist_ok=True)
    os.makedirs(dummy_html_dir, exist_ok=True)

    today_str = date.today().isoformat()
    dummy_json_filename = f"{today_str}.json"
    dummy_json_filepath = os.path.join(dummy_json_dir, dummy_json_filename)

    with open(dummy_json_filepath, 'w', encoding='utf-8') as f:
        json.dump(dummy_papers, f, indent=4)

    logging.basicConfig(level=logging.INFO) # Add basic config for testing
    logging.info(f"Running example generation...")
    generate_html_from_json(
        json_file_path=dummy_json_filepath,
        template_dir=dummy_template_dir,
        template_name=dummy_template_name,
        output_dir=dummy_html_dir
    )
    logging.info("Example generation finished.")
