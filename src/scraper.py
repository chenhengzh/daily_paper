import arxiv
import logging
import re
from datetime import date, timedelta, datetime, timezone
from typing import List, Dict, Optional, Any, Iterable, Tuple

try:
    # py3.9+
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


DEFAULT_KEYWORDS: list[str] = [
    "LLM",
    "Personalization",
    "Tool",
    "Agent",
]

# 研究方向相关的默认分类（可通过 main.py 参数覆盖）。
DEFAULT_CATEGORIES: list[str] = [
    "cs.AI",
    "cs.LG",
    "cs.CL",
    "stat.ML",
    "cs.RO",
    "cs.MA",
    "cs.NE",
]


def _ensure_tzaware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _local_tz() -> timezone:
    # 使用系统本地时区（macOS 上通常可用）。
    return datetime.now().astimezone().tzinfo or timezone.utc


def _day_window_utc(specified_date: date, tzinfo: Optional[timezone] = None) -> Tuple[datetime, datetime]:
    """给定本地日期，返回 [start,end) 的 UTC 时间窗口。"""
    tzinfo = tzinfo or _local_tz()
    start_local = datetime.combine(specified_date, datetime.min.time()).replace(tzinfo=tzinfo)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _fmt_arxiv_dt(dt: datetime) -> str:
    # arXiv API 的 submittedDate 过滤使用 YYYYMMDDHHMM
    return _ensure_tzaware(dt).astimezone(timezone.utc).strftime("%Y%m%d%H%M")


_ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(?P<id>\d{4}\.\d{4,5})(?:v\d+)?")


def _extract_arxiv_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = _ARXIV_ID_RE.search(url)
    if m:
        return m.group("id")
    return None


def _build_keyword_block(keywords: Iterable[str]) -> str:
    """将关键词构造成 ti/abs 的 OR 查询。

    说明：
    - 对短关键词（如 LLM / RL）也同时匹配 ti/abs
    - 对包含空格的关键词使用引号做短语匹配
    """
    terms: list[str] = []
    for raw in keywords:
        k = (raw or "").strip()
        if not k:
            continue
        if "\"" in k:
            k = k.replace('"', "")
        if " " in k:
            q = f'"{k}"'
        else:
            q = k
        terms.append(f"ti:{q}")
        terms.append(f"abs:{q}")

    # 做一点“鲁棒性增强”：对常见缩写补齐。
    low = {t.lower() for t in keywords if t}
    if "reinforcement learning" in low and "rl" not in low:
        terms.extend(["ti:RL", "abs:RL"])
    if "world models" in low and "world model" not in low:
        terms.extend(['ti:"world model"', 'abs:"world model"'])
    if "agents" in low and "agent" not in low:
        terms.extend(["ti:agent", "abs:agent"])

    if not terms:
        return ""
    return "(" + " OR ".join(terms) + ")"


def _build_category_block(categories: Optional[Iterable[str]]) -> str:
    if not categories:
        return ""
    cats = [c.strip() for c in categories if c and c.strip()]
    if not cats:
        return ""
    return "(" + " OR ".join([f"cat:{c}" for c in cats]) + ")"




def fetch_daily_papers(
    *,
    specified_date: Optional[date] = None,
    keywords: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    max_results: int = 800,
) -> List[Dict[str, Any]]:
    """抓取“某一天”内提交的、与关键词相关的论文。

    设计目标：
    - 关键词覆盖 LLM / RL / World Models / Agents
    - 通过 submittedDate 过滤 + published_date 二次过滤，增强鲁棒性
    - 失败时自动降级（例如拆分查询）
    """

    if specified_date is None:
        specified_date = datetime.now(_local_tz()).date()

    # keywords: None 表示用默认关键词；[] 表示不限制关键词（仅按分类+日期拉取）
    kw = DEFAULT_KEYWORDS if keywords is None else keywords
    cats = DEFAULT_CATEGORIES if categories is None else categories

    start_utc, end_utc = _day_window_utc(specified_date)
    start_str = _fmt_arxiv_dt(start_utc)
    end_str = _fmt_arxiv_dt(end_utc)

    kw_block = _build_keyword_block(kw)
    cat_block = _build_category_block(cats)
    date_block = f"submittedDate:[{start_str} TO {end_str}]"

    blocks = [b for b in [cat_block, kw_block, date_block] if b]
    query = " AND ".join(blocks)
    logging.info(f"Using arXiv query: {query}")

    def _run_query(q: str) -> List[Dict[str, Any]]:
        client = arxiv.Client(page_size=200, delay_seconds=1, num_retries=3)
        search = arxiv.Search(query=q, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
        out: list[dict[str, Any]] = []
        for r in client.results(search):
            abs_url = getattr(r, "entry_id", "")
            arxiv_id = _extract_arxiv_id(abs_url or "")
            published = _ensure_tzaware(getattr(r, "published", datetime.now(timezone.utc)))
            # 二次过滤：确保在目标日期窗口内（以本地“日”定义）
            if not (start_utc <= published.astimezone(timezone.utc) < end_utc):
                continue
            out.append(
                {
                    "arxiv_id": arxiv_id,
                    "title": getattr(r, "title", ""),
                    "summary": (getattr(r, "summary", "") or "").strip(),
                    "url": abs_url,
                    "abs_url": abs_url,
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None,
                    "published_date": getattr(r, "published", None),
                    "updated_date": getattr(r, "updated", None),
                    "categories": getattr(r, "categories", []) or [],
                    "authors": [a.name for a in (getattr(r, "authors", []) or [])],
                }
            )
        return out

    papers: list[dict[str, Any]] = []
    try:
        papers = _run_query(query)
    except Exception as e:
        # 降级策略：拆分为每个 category 独立查询再合并（避免 query 太长/解析失败）
        logging.warning(f"Primary arXiv query failed, fallback to per-category queries: {e}")
        merged: list[dict[str, Any]] = []
        cats_fallback = cats or []
        for c in cats_fallback:
            cat_q = _build_category_block([c])
            blocks2 = [b for b in [cat_q, kw_block, date_block] if b]
            q2 = " AND ".join(blocks2)
            try:
                merged.extend(_run_query(q2))
            except Exception as e2:
                logging.warning(f"Per-category query failed cat={c}: {e2}")
        papers = merged

    # 若带关键词查询结果为 0，做一次“无关键词”的保底拉取，避免关键词 miss 造成漏抓。
    if (not papers) and kw:
        logging.info("Keyword query returned 0 results; fallback to category+date only query.")
        blocks3 = [b for b in [cat_block, date_block] if b]
        q3 = " AND ".join(blocks3)
        try:
            papers = _run_query(q3)
        except Exception as e3:
            logging.warning(f"Fallback category+date query failed: {e3}")

    # 去重（以 arxiv_id 优先，其次 abs_url）
    dedup: dict[str, dict[str, Any]] = {}
    for p in papers:
        k = p.get("arxiv_id") or p.get("abs_url") or p.get("url") or p.get("title")
        if not k:
            continue
        if k not in dedup:
            dedup[k] = p

    out = list(dedup.values())
    # 以发布时间降序，方便后续 debug
    out.sort(key=lambda x: _ensure_tzaware(x.get("published_date") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    logging.info(f"Fetched {len(out)} papers for {specified_date.isoformat()} (after dedup & date filter).")
    return out

if __name__ == '__main__':
    example_date = date(2025, 4, 26)
    logging.info(f"Fetching papers for {example_date.strftime('%Y-%m-%d')}...")
    latest_papers = fetch_daily_papers(specified_date=example_date, max_results=500)
    if latest_papers:
        logging.info(f"--- Found {len(latest_papers)} Papers ---")
        for i, paper in enumerate(latest_papers):
            print(f"{i+1}. {paper['title']}. published_date: {paper['published_date']}.")
    else:
        print(f"No papers found for {example_date} or an error occurred.")
