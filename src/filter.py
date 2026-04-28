import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional, List, Tuple

try:
    from remote_llm_api import default_chat_completion_text, RemoteLLMConfig
except ModuleNotFoundError:
    # 兼容通过 `import src.filter` 的方式运行：确保 src 目录在 sys.path 中
    import os
    import sys

    _SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)
    from remote_llm_api import default_chat_completion_text, RemoteLLMConfig


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 你关心的“高信号”要素（用于在 LLM 打分后做二次校准）---
# 目的：
# - 防止 LLM 给太多 paper 打高分
# - 将“LLM/MLLM 的 RL / world model / 突破性进展 / 大牛作者”显式提升

# 领域大牛（可按你个人偏好继续补充/删减）
NOTABLE_AUTHORS: set[str] = set()

HIGH_SIGNAL_KEYWORDS: list[str] = [
    "Agent",
]

# “突破性/强声明”提示词：不保证真突破，但可作为优先级提升信号
BREAKTHROUGH_CLAIM_KEYWORDS: list[str] = [
    "state-of-the-art",
    "sota",
    "first",
    "novel",
    "breakthrough",
    "surpass",
    "outperform",
    "significant",
    "dramatically",
    "orders of magnitude",
]


DEEMPHASIZED_KEYWORDS: list[str] = []

# 明显低质量/不需要的内容：强过滤
LOW_QUALITY_TITLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bphd\b", re.IGNORECASE),
    re.compile(r"\bdissertation\b", re.IGNORECASE),
    re.compile(r"\bdoctoral\b", re.IGNORECASE),
    re.compile(r"\bthesis\b", re.IGNORECASE),
    re.compile(r"\bmaster'?s\b", re.IGNORECASE),
    re.compile(r"\btechnical report\b", re.IGNORECASE),
]


# “堆砌概念/形式化但缺乏可验证实质”的粗糙信号
CONCEPT_STACKING_KEYWORDS: list[str] = [
    "framework",
    "taxonomy",
    "paradigm",
    "foundations",
    "foundation",
    "teleological",
    "intentional",
    "structural causal",
    "formalization",
    "formulation",
    "unified",
    "novel concept",
    "we introduce the notion",
]


# 可信度/实质性信号（理论或实证皆可）
EVIDENCE_KEYWORDS: list[str] = [
    "theorem",
    "proof",
    "proposition",
    "lemma",
    "corollary",
    "convergence",
    "regret",
    "lower bound",
    "upper bound",
    "guarantee",
    "ablation",
    "experiment",
    "evaluation",
    "empirical",
]


DEFAULT_ARXIV_KEYWORDS: list[str] = [
    "Agent",
]


def _heuristic_fallback(papers: list, interests: str) -> list:
    """当未配置 LLM key 时的兜底：用简单关键词匹配填充基础字段，保证流水线可跑通。"""
    keys = [k.lower() for k in DEFAULT_ARXIV_KEYWORDS]
    for p in papers:
        text = f"{p.get('title','')}\n{p.get('summary','')}".lower()
        hit = sum(1 for k in keys if k and k in text)
        rel = min(10, 2 + hit * 2)
        p.setdefault("keep", True)
        p.setdefault("keep_reason", "no_llm_key: heuristic fallback")
        p.setdefault("interest_field", "Unknown")
        p.setdefault("interest_subfield", "Unknown")
        p.setdefault("interest_match_reason", "heuristic fallback")
        p.setdefault("tags", [])
        p.setdefault("tldr", "")
        p.setdefault("tldr_zh", "")
        p.setdefault("relevance_score", rel)
        p.setdefault("quality_score", 5)
        p.setdefault("novelty_claim_score", 5)
        p.setdefault("overall_priority_score", round((rel * 0.6 + 5 * 0.4), 1))
    return papers


def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        # 兼容 ```json / ```
        s = re.sub(r"^```[a-zA-Z]*\n", "", s)
        s = re.sub(r"\n```$", "", s)
        s = s.strip()
    return s


def _extract_json_object(s: str) -> str:
    s = _strip_code_fences(s)
    # 取第一个 { 到最后一个 } 的子串，提升解析成功率
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        return s[i : j + 1]
    return s


async def _repair_to_valid_json(*, namespace: str, raw: str) -> tuple[str, dict]:
    """当模型输出非严格 JSON 时，做一次轻量修复调用。Returns (text, usage)."""
    messages = [
        {
            "role": "system",
            "content": "You convert the user's content into strictly valid JSON (RFC8259). Output JSON only, no code fences.",
        },
        {"role": "user", "content": raw},
    ]
    return await default_chat_completion_text(
        namespace=namespace,
        messages=messages,
        max_tokens=1200,
        temperature=0.0,
    )


rating_prompt_template = """
# Role
You are a senior AI researcher triaging arXiv papers for a colleague's daily reading list. Filter ruthlessly and score honestly — most papers should not make the cut.

# Researcher's Interests
%s

# Paper to Evaluate
Title: %s
Abstract: %s

# Triage Rules (apply in order)
1. **Relevance gate**: If the paper does not address any of the researcher's stated interests, set keep=false immediately. Do not inflate scores to compensate.
2. **Quality gate**: Reject (keep=false) papers that are clearly low-signal — vague or empty abstracts, purely incremental engineering with no novel insight, dataset/benchmark papers with no methodological contribution, theses/dissertations/technical reports, or rambling single-author manuscripts.
3. **Calibration**: Apply ICML/ICLR/NeurIPS reviewer standards. Ask whether there is genuine novelty backed by theory or strong empirical evidence, not just concept stacking or narrow application.
   - Only ~5%% of papers warrant overall_priority_score >= 8.0
   - Only ~10%% warrant overall_priority_score >= 7.5
   - When uncertain, assign a conservative score (5-6) rather than a generous one.
4. **Ambiguous cases**: If the abstract hints at something potentially important but is unclear, prefer keep=true with a low-to-mid score rather than discarding.

# Scoring Dimensions (1-10 each)
- **relevance_score**: How well the paper aligns with the researcher's stated interests.
- **quality_score**: Rigor and credibility — method clarity, evaluation strength, theoretical grounding.
- **novelty_claim_score**: Originality and strength of the novelty claim.
- **impact_score**: Potential to change how the field thinks or builds things.
- **overall_priority_score**: Holistic read priority; weight relevance and quality most heavily.

# Output Fields
- **keep**: boolean. False if the paper fails the relevance or quality gate.
- **keep_reason**: one sentence explaining the keep/reject decision.
- **interest_field**: the most relevant top-level interest area from the researcher's list (or "Other").
- **interest_subfield**: a more specific sub-topic within that field.
- **interest_match_reason**: one sentence on why (or why not) this paper matches the interests.
- **tldr**: one English sentence (<=30 words) capturing the core contribution.
- **tldr_zh**: 3-5 Chinese sentences covering: (1) the problem or gap, (2) the proposed method or key finding with concrete detail, (3) main results, (4) significance. Be specific — avoid openers like "本文提出了一种方法".
- **summary_zh**: 5-8 Chinese sentences. A technical mini-review: motivation and background, method in mechanistic terms (architecture/algorithm/training), key quantitative results, limitations or open questions, and why this work matters. Write as a knowledgeable researcher, not a translator.
- **tags**: list of short keyword strings.

# Output Format
Respond with a single valid JSON object (RFC 8259). No markdown, no code fences, no trailing commas.

{
  "keep": true,
  "keep_reason": "...",
  "interest_field": "...",
  "interest_subfield": "...",
  "interest_match_reason": "...",
  "tldr": "...",
  "tldr_zh": "...",
  "summary_zh": "...",
  "tags": ["..."],
  "relevance_score": 1,
  "quality_score": 1,
  "novelty_claim_score": 1,
  "impact_score": 1,
  "overall_priority_score": 1
}
"""


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _clamp_score(x: Any, lo: float = 1.0, hi: float = 10.0) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    if v < lo:
        return float(lo)
    if v > hi:
        return float(hi)
    return float(v)


def _text_for_match(p: Dict[str, Any]) -> str:
    title = (p.get("title") or "").strip()
    abstract = (p.get("summary") or "").strip()
    return f"{title}\n{abstract}".lower()


def _author_hits(p: Dict[str, Any]) -> list[str]:
    authors = p.get("authors") or []
    if not isinstance(authors, list):
        return []
    norm_authors = {_norm_name(a) for a in authors if isinstance(a, str) and a.strip()}
    hits: list[str] = []
    for a in NOTABLE_AUTHORS:
        if _norm_name(a) in norm_authors:
            hits.append(a)
    return hits


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for k in keywords:
        kk = (k or "").strip().lower()
        if not kk:
            continue
        # 支持非常轻量的“正则式子串”（仅用于极少数模式），失败则退回普通包含判断
        try:
            if "\\" in kk or any(ch in kk for ch in ["(", ")", "[", "]", "?", "+", "*"]):
                if re.search(kk, text):
                    hits.append(k)
            else:
                if kk in text:
                    hits.append(k)
        except Exception:
            if kk in text:
                hits.append(k)
    return hits


def _author_count(p: Dict[str, Any]) -> int:
    authors = p.get("authors") or []
    if isinstance(authors, list):
        return sum(1 for a in authors if isinstance(a, str) and a.strip())
    return 0


def _postprocess_one(p: Dict[str, Any]) -> Dict[str, Any]:
    """对 LLM 输出做一次“偏好校准 + 稳健性增强”。

    目标不是替代 LLM 判断，而是：
    - 让“你最关心的方向”更稳定地被置顶
    - 限制过度乐观的打分（避免 7/8 滥发）
    """

    # 统一分数类型 & 截断
    p["relevance_score"] = _clamp_score(p.get("relevance_score", 0))
    p["quality_score"] = _clamp_score(p.get("quality_score", 0))
    p["novelty_claim_score"] = _clamp_score(p.get("novelty_claim_score", 0))
    p["impact_score"] = _clamp_score(p.get("impact_score", 0))

    p["overall_priority_score"] = _clamp_score(p.get("overall_priority_score", 0))

    text = _text_for_match(p)
    title_low = (p.get("title") or "").strip().lower()

    # 强过滤：明显不需要的类型（博士/论文等）
    for pat in LOW_QUALITY_TITLE_PATTERNS:
        if pat.search(title_low):
            p["keep"] = False
            reason = (p.get("keep_reason") or "").strip()
            p["keep_reason"] = (reason + " | ").strip() + "post_filter: thesis/dissertation/technical report"
            # 直接下压分数，避免误入高优
            p["overall_priority_score"] = _clamp_score(min(p["overall_priority_score"], 3.0))
            p["relevance_score"] = _clamp_score(min(p["relevance_score"], 4.0))
            p["quality_score"] = _clamp_score(min(p["quality_score"], 4.0))
            break

    hs_hits = _keyword_hits(text, HIGH_SIGNAL_KEYWORDS)
    bt_hits = _keyword_hits(text, BREAKTHROUGH_CLAIM_KEYWORDS)
    deemph_hits = _keyword_hits(text, DEEMPHASIZED_KEYWORDS)
    concept_hits = _keyword_hits(text, CONCEPT_STACKING_KEYWORDS)
    evidence_hits = _keyword_hits(text, EVIDENCE_KEYWORDS)
    author_hits = _author_hits(p)
    n_authors = _author_count(p)

    # 轻量打分修正：高信号 + 大牛略微加分
    boost = 0.0
    boost += min(0.8, 0.15 * len(hs_hits))
    boost += min(0.4, 0.10 * len(bt_hits))
    boost += 0.35 if author_hits else 0.0

    # 降权：safety/alignment/security-only & 过度具体 case
    boost -= min(0.6, 0.12 * len(deemph_hits))

    # 可信度/实质性：有 theorem/proof/strong eval 等则略微提升
    boost += min(0.5, 0.12 * len(evidence_hits))

    # “堆砌概念”且缺乏可验证实质时，下压
    if len(concept_hits) >= 3 and len(evidence_hits) == 0:
        boost -= 0.6

    # 单作者 + "foundation/guide" 风格：强烈不优先（按你的偏好直接倾向丢弃）
    keep = bool(p.get("keep", True))
    if keep and n_authors == 1 and (not author_hits):
        if any(k in title_low for k in ["foundation", "foundations", "primer", "guide", "tutorial", "introduction"]):
            p["keep"] = False
            reason = (p.get("keep_reason") or "").strip()
            p["keep_reason"] = (reason + " | ").strip() + "post_filter: single-author foundation/guide-style"
            p["overall_priority_score"] = _clamp_score(min(p["overall_priority_score"], 4.5))

    # 过时/经典套路 bandit 理论（如 epsilon-greedy / single-index）下压：你更偏好新现象/新 insight
    if ("bandit" in text) and ("epsilon-greedy" in text or "single-index" in text):
        boost -= 0.8

    # 单作者：不是硬过滤，但在证据弱/分数偏乐观时更保守
    if n_authors == 1 and (not author_hits) and len(evidence_hits) == 0 and p["overall_priority_score"] >= 7.5:
        boost -= 0.4

    # 保守校准：若没有任何高信号命中，且 relevance/quality 偏低，则整体分数下压
    if (not hs_hits) and p["relevance_score"] <= 5.0 and p["quality_score"] <= 6.0:
        boost -= 0.4


    p["overall_priority_score"] = _clamp_score(p["overall_priority_score"] + boost)

    # 对 keep 做更严格的兜底：
    # - LLM keep=true 但 relevance 很低、且无高信号/大牛命中时，倾向丢弃
    keep = bool(p.get("keep", True))
    if keep and p["relevance_score"] <= 3.0 and (not hs_hits) and (not author_hits):
        p["keep"] = False
        reason = (p.get("keep_reason") or "").strip()
        p["keep_reason"] = (reason + " | ").strip() + "post_filter: low relevance & no high-signal"

    # 概念堆砌 + 缺乏证据 + 分数不低：倾向丢弃
    keep = bool(p.get("keep", True))
    if keep and len(concept_hits) >= 4 and len(evidence_hits) == 0 and p["overall_priority_score"] >= 6.8:
        p["keep"] = False
        reason = (p.get("keep_reason") or "").strip()
        p["keep_reason"] = (reason + " | ").strip() + "post_filter: concept stacking without evidence"

    # 记录信号，便于后续 HTML/统计
    p["signal_high_keywords"] = hs_hits[:12]
    p["signal_breakthrough_keywords"] = bt_hits[:12]
    p["signal_notable_authors"] = author_hits[:8]
    p["signal_deemphasized_keywords"] = deemph_hits[:10]
    p["signal_evidence_keywords"] = evidence_hits[:10]
    p["signal_concept_keywords"] = concept_hits[:10]
    return p


def _postprocess_scoring(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_postprocess_one(p) for p in papers]


async def _rate_one_paper(
    *,
    paper: Dict[str, Any],
    interests: str,
    idx: int,
    total: int,
    api_retries: int = 2,
) -> Dict[str, Any]:
    title = (paper.get("title") or "").strip()
    abstract = (paper.get("summary") or "").strip()
    if not title or not abstract:
        paper.update(
            {
                "keep": False,
                "keep_reason": "missing title/abstract",
                "overall_priority_score": 0,
                "relevance_score": 0,
                "quality_score": 0,
                "novelty_claim_score": 0,
                "impact_score": 0,
                "tldr": "",
                "tldr_zh": "",
                "summary_zh": "",
                "tags": [],
            }
        )
        return paper

    prompt = rating_prompt_template % (interests, title, abstract)
    messages = [
        {
            "role": "system",
            "content": "You are an AI researcher doing paper triage. Follow the user's output schema strictly.",
        },
        {"role": "user", "content": prompt},
    ]

    last_err: Optional[Exception] = None
    for attempt in range(max(1, api_retries)):
        try:
            raw, usage = await default_chat_completion_text(
                namespace="paper_rating",
                messages=messages,
                max_tokens=4096,
                temperature=0.3,
            )

            raw2 = _extract_json_object(raw)
            try:
                data = json.loads(raw2)
            except json.JSONDecodeError:
                repaired, _ = await _repair_to_valid_json(namespace="paper_rating_repair", raw=raw2)
                data = json.loads(_extract_json_object(repaired))

            if not isinstance(data, dict):
                raise ValueError("LLM output is not a JSON object")

            # 轻度清洗：避免 types 异常
            data.setdefault("tags", [])
            if not isinstance(data.get("tags"), list):
                data["tags"] = []

            data.setdefault("interest_field", "Unknown")
            data.setdefault("interest_subfield", "Unknown")
            data.setdefault("interest_match_reason", "")

            data.setdefault("tldr", "")
            data.setdefault("tldr_zh", "")
            data.setdefault("summary_zh", "")
            data.setdefault("impact_score", 0)

            paper.update(data)
            paper["_llm_input_tokens"] = usage.get("input_tokens", 0)
            paper["_llm_output_tokens"] = usage.get("output_tokens", 0)
            logging.info(
                f"评分 {idx+1}/{total}: keep={paper.get('keep')} score={paper.get('overall_priority_score')} title='{title[:60]}'"
            )
            return paper

        except Exception as e:
            last_err = e
            logging.warning(
                f"评分失败 {idx+1}/{total} attempt={attempt+1}/{api_retries} title='{title[:60]}': {e}"
            )
            if attempt < max(1, api_retries) - 1:
                wait = 60.0 if ("429" in str(e) or "rate" in str(e).lower()) else 5.0
                await asyncio.sleep(wait)

    paper.update(
        {
            "keep": False,
            "keep_reason": f"llm_error: {last_err}",
            "overall_priority_score": paper.get("overall_priority_score", 0) or 0,
            "tldr": paper.get("tldr", "") or "",
            "tldr_zh": paper.get("tldr_zh", "") or "",
            "tags": paper.get("tags", []) or [],
        }
    )
    return paper


async def _rate_papers_async(papers: List[Dict[str, Any]], interests: str) -> List[Dict[str, Any]]:
    total = len(papers)
    tasks = [
        _rate_one_paper(paper=p, interests=interests, idx=i, total=total)
        for i, p in enumerate(papers)
    ]
    return await asyncio.gather(*tasks)


def rate_papers(papers: list, interests: Optional[str] = None) -> list:
    """使用 `src/remote_llm_api.py` 的远程模型对论文做“粗筛 + 初步评分”。

    依赖环境变量：
    - `AZURE_API_KEY`（或 `OPENAI_API_KEY`）
    - 可选：`AZURE_ENDPOINT` / `LLM_MODEL_NAME` / `LLM_QPM` 等
    """
    interests = interests or ""
    logging.info(f"开始对 {len(papers)} 篇论文做粗筛与评分...")

    # 若没有配置 key，直接回退到启发式，避免主流程崩溃。
    cfg = RemoteLLMConfig()
    if not getattr(cfg, "AZURE_API_KEY", ""):
        logging.warning("未检测到 `AZURE_API_KEY`（或 `OPENAI_API_KEY`），跳过 LLM 评分，使用启发式兜底。")
        return _postprocess_scoring(_heuristic_fallback(papers, interests))

    # CLI 场景：直接 asyncio.run 即可。若在 notebook/已有 event loop 中，请改用 `_rate_papers_async`。
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        rated = asyncio.run(_rate_papers_async(papers, interests))
        return _postprocess_scoring(rated)
    raise RuntimeError(
        "rate_papers() cannot be called inside a running event loop; use await _rate_papers_async(papers, interests)"
    )


if __name__ == '__main__':
    test_papers = [
        {
            "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
            "summary": "We introduce ReAct, a paradigm that combines reasoning traces and task-specific actions to improve LLM agents...",
        }
    ]
    rated = rate_papers(test_papers, interests="")
    print(json.dumps(rated[0], ensure_ascii=False, indent=2))
