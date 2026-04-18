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


INTEREST_TABLE: list[dict[str, str]] = [
    # --- RL ---
    {"field": "RL", "subfield": "MultiModal RL", "description": "Techniques & algorithms related to RL in multi-modal environments."},
    {"field": "RL", "subfield": "SFT v.s. RL", "description": "Theories/algorithms/findings related to understanding/bridging the gap between SFT and RL."},
    {"field": "RL", "subfield": "RL Infra", "description": "Building RL infrastructures."},
    {"field": "RL", "subfield": "RLHF", "description": "Theories/algorithms/findings about RL with human feedback."},
    {"field": "RL", "subfield": "RLVF", "description": "Theories/algorithms/findings about RL with verifiable feedback."},
    {"field": "RL", "subfield": "RL Efficiency", "description": "Improving the sampling complexity of RL."},
    {"field": "RL", "subfield": "Unsupervised/Self-Play RL", "description": "RL without external rewards."},
    {"field": "RL", "subfield": "RL Theory", "description": "Fundamental theories about RL."},
    {"field": "RL", "subfield": "Beyond Trial & Error", "description": "Improving RL training beyond trial and error."},
    {"field": "RL", "subfield": "Agentic RL", "description": "RL with tools and agentic environments."},
    {"field": "RL", "subfield": "Classic RL", "description": "Bandit/Tabular/MDP learning techniques and theories."},
    {"field": "RL", "subfield": "RL & Robotics", "description": "Applying RL to embodied AI."},
    {"field": "RL", "subfield": "RL for Diffusion", "description": "Training Diffusion Model/Policy with RL."},
    {"field": "RL", "subfield": "RL + Distillation", "description": "Combining RL techniques with distillation."},
    # --- General LLM ---
    {"field": "General LLM", "subfield": "(Continuous) Pre-training", "description": "Findings/algorithms."},
    {"field": "General LLM", "subfield": "Scaling Laws", "description": "Various scaling laws."},
    {"field": "General LLM", "subfield": "Decoding Strategy", "description": "Improving AR performance beyond random sampling."},
    # --- Trustworthy LLM ---
    {"field": "Trustworthy LLM", "subfield": "RLHF Theory/Understanding", "description": "Theories into the process of RLHF."},
    {"field": "Trustworthy LLM", "subfield": "Agentic Safety", "description": "Studying safety in an agentic environment."},
    {"field": "Trustworthy LLM", "subfield": "Privacy/Fairness/Faithfulness of LLMs", "description": "Privacy/fairness concerns of LLMs."},
    # --- Agents ---
    {"field": "Agents", "subfield": "Building Agents/workflow", "description": "Techniques relating to building Agentic workflow."},
    {"field": "Agents", "subfield": "Scaling Test-time Compute", "description": "Theories/techniques about scaling test-time compute."},
    # --- Multimodal LLM ---
    {"field": "Multimodal LLM", "subfield": "Architectures", "description": "Architectural design of multimodal LLMs."},
    # --- Diffusion LLM ---
    {"field": "Diffusion LLM", "subfield": "Principles and Implementations", "description": "Principles and Architectures for Diffusion LLM."},
    {"field": "Diffusion LLM", "subfield": "Post Training", "description": "Post-training Methods for Diffusion LLMs."},
    # --- World Models ---
    {"field": "World Models", "subfield": "Principles and Implementations", "description": "Building Neural Networks that Approximate the Real World."},
]


# --- 你关心的“高信号”要素（用于在 LLM 打分后做二次校准）---
# 目的：
# - 防止 LLM 给太多 paper 打高分
# - 将“LLM/MLLM 的 RL / world model / 突破性进展 / 大牛作者”显式提升

# 领域大牛（可按你个人偏好继续补充/删减）
NOTABLE_AUTHORS: set[str] = {
    # RL
    "Richard S. Sutton",
    "Richard Sutton",
    "David Silver",
    "Sergey Levine",
    "Pieter Abbeel",
    "John Schulman",
    "Shane Legg",
    "Doina Precup",
    "Satinder Singh",
    "Chelsea Finn",
    "Yarin Gal",
    # LLM / Agents
    "Ilya Sutskever",
    "Andrej Karpathy",
    "Percy Liang",
    "Denny Zhou",
    "Noam Shazeer",
    "Yoshua Bengio",
    "Yann LeCun",
    "Geoffrey Hinton",
}

# 强相关关键词：偏向 LLM/MLLM 的 RL / world model / agent / test-time compute
HIGH_SIGNAL_KEYWORDS: list[str] = [
    # RL for LLM/MLLM
    "rlhf",
    "rlaif",
    "rlvf",
    "reinforcement learning",
    "policy optimization",
    "ppo",
    "dpo",
    "orpo",
    "grpo",
    "ipo",
    "preference optimization",
    "reward model",
    "verifiable",
    "process reward",
    "outcome reward",
    "self-play",
    "online rl",
    "off-policy",
    # World model / model-based
    "world model",
    "latent dynamics",
    "model-based",
    "dreamer",
    "imagination",
    "planning",
    "long-horizon",
    "temporal abstraction",
    # Agents / test-time compute
    "agent",
    "tool use",
    "test-time compute",
    "reasoning",
    "planning",
    "memory",
    # Multimodal
    "multimodal",
    "mllm",
    "vision-language",
    "video",
    "robot",
    "embodied",
    # Theory / principled insights / large-scale phenomena
    "theorem",
    "proof",
    "convergence",
    "regret",
    "generalization",
    "generalisation",
    "sample complexity",
    "lower bound",
    "upper bound",
    "information-theoretic",
    "principled",
    "mechanistic",
    "phenomenon",
    "phase transition",
    "emergent",
    "scaling law",
    "universality",
    "invariant",
    # Insight / phenomenon-driven analysis (e.g., temporal reasoning)
    "temporal reasoning",
    "tokenization",
    "tokenisation",
    "subword",
    "bpe",
    "calendar",
    "multilingual",
    "low-resource",
    "diagnostic",
    "what really controls",
    "representation of time",
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

# 明显低信号（用于轻微降权/更严格 keep）：注意不要过度惩罚 survey/benchmark（有时也很重要）
LOW_SIGNAL_KEYWORDS: list[str] = [
    "case study",
    "application",
    "industrial",
    "deployment",
    "edge device",
    "hyperparameter",
    "ablation only",
    "dataset",
    "benchmark",
    "leaderboard",
    "survey",
    "tutorial",
    # governance / role-play simulations (often too scenario-specific)
    "governance",
    "corruption",
    "role-play",
    "roleplay",
    # "foundation/guide" type writing (often tutorial-like, sometimes low-signal)
    "foundations",
    "foundation",
    "primer",
    "guide",
    "introduction",
    # outdated / classic-theory framing (heuristic)
    "epsilon-greedy",
    "single-index",
    "single-index bandit",
    "schrödinger bridge",
    "schrodinger bridge",
    # narrow/specific applications (often low generality)
    "real-world",
    "in the wild",
    "deployment",
    "industrial",
    "clinical",
    "medical",
    "radiology",
    "electronic health record",
    "smart city",
    "traffic",
    "agriculture",
    "recommendation system",
    "edge",
    "iot",
    "underwater",
    "aerial",
    "uav",
    "satellite",
]


# 你不太想优先看的方向：用于 postprocess 的轻微降权（不是强过滤）
DEEMPHASIZED_KEYWORDS: list[str] = [
    # safety/alignment & security-only work
    "safety",
    "alignment",
    "jailbreak",
    "red teaming",
    "guardrail",
    "policy compliance",
    "toxic",
    "harmful",
    "prompt injection",
    "security awareness",
    "privacy",
    "fairness",
    "bias",
]


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


def interests_markdown() -> str:
    lines = [
        "# My Paper Selection Principles",
        "- Prefer general technical innovation, deep and broadly impactful insights, and large-scale phenomenon discovery (can be theory-leaning).",
        "- Be critical: distinguish real innovation/new findings from concept stacking, superficial framing, or overly specific scenarios.",
        "- De-emphasize safety/alignment/security-only papers and narrow agent behavior case studies unless they uncover general principles.",
        "- Use ICML/ICLR/NeurIPS standards: credible methods (theory or strong empirical evidence), clear problem, and meaningful contribution.",
        "\n# My Paper Interest Taxonomy",
    ]
    for r in INTEREST_TABLE:
        lines.append(f"- {r['field']} / {r['subfield']}: {r['description']}")
    return "\n".join(lines)


def arxiv_query_keywords(max_terms: int = 24) -> list[str]:
    """用于 arXiv 查询的关键词（要短、强覆盖，避免 query 过长）。"""
    base = [
        "LLM",
        "language model",
        "RL",
        "Reinforcement Learning",
        "RLHF",
        "RLAIF",
        "verifiable reward",
        "self-play",
        "bandit",
        "MDP",
        "SFT",
        "pre-training",
        "scaling law",
        "decoding",
        "Agent",
        "tool use",
        "test-time compute",
        "world model",
        "model-based",
        "multimodal",
        "robotics",
        "diffusion",
        "distillation",
        "privacy",
        "fairness",
        "faithfulness",
        "safety",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for k in base:
        kk = k.strip()
        if not kk:
            continue
        low = kk.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(kk)
        if len(out) >= int(max_terms):
            break
    return out


DEFAULT_INTERESTS = interests_markdown()
DEFAULT_ARXIV_KEYWORDS = arxiv_query_keywords()


def _heuristic_fallback(papers: list, interests: str) -> list:
    """当未配置 LLM key 时的兜底：用简单关键词匹配填充基础字段，保证流水线可跑通。"""
    # interests 是 markdown 文本，这里抽取一些关键 token 做兜底匹配
    keys = [
        "llm",
        "language model",
        "reinforcement learning",
        "rlhf",
        "rlvf",
        "agent",
        "world model",
        "multimodal",
        "diffusion",
        "robotics",
        "safety",
        "privacy",
        "fairness",
        "faithfulness",
        "scaling law",
        "pre-training",
        "decoding",
        "distillation",
    ]
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
        p.setdefault("clarity_score", 5)
        p.setdefault("potential_impact_score", 5)
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


async def _repair_to_valid_json(*, namespace: str, raw: str) -> str:
    """当模型输出非严格 JSON 时，做一次轻量修复调用。"""
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
You are a careful, time-constrained AI researcher who triages arXiv papers for daily reading.

# Goal
Given ONLY the title and abstract, do a coarse screening and a preliminary rating.

# Input
Paper Title: %s
Paper Abstract: %s

# My Research Interests (for relevance + classification)
%s

# Coarse Screening Rules
- Mark keep=false if the paper is clearly low-signal for a researcher (e.g., vague claims, no method details, obvious incremental engineering without insight, weak/empty abstract, purely dataset/benchmark with little novelty, or off-topic).
- Mark keep=false for obvious low-quality items: theses/dissertations/technical reports, rambling single-author manuscripts with weak evidence, or extremely niche application-only papers.
- IMPORTANT CALIBRATION: be selective. In a typical day, only a small fraction should be high priority.
  - Only ~5%% of papers deserve overall_priority_score >= 8.0
  - Only ~10%% of papers deserve overall_priority_score >= 7.5
  - If you are unsure, give a conservative score (6-7) and/or keep=false.
- I care MOST about: general technical innovation and broadly impactful insights (can be theory-leaning), plus important large-scale phenomenon discoveries.
- De-emphasize: safety/alignment/security-only papers, and narrow agent case studies (unless they reveal general principles).
- Be critical at ICML/ICLR/NeurIPS standards: is it real novelty with substance (theory/proof or strong empirical evidence), or just concept stacking / narrow scenario engineering?
- If the abstract is ambiguous but potentially important, prefer keep=true with lower confidence, but do NOT give a high overall score.

# Output Requirements (MUST)
- Output JSON only (RFC8259). No markdown, no code fences, no trailing commas.
- Use numbers 1-10 for scores.
- keep must be a boolean.

# Output JSON Schema
{
  "keep": true,
  "keep_reason": "...",
  "interest_field": "RL",
  "interest_subfield": "RLHF",
  "interest_match_reason": "...",
  "tldr": "...",
  "tldr_zh": "...",
  "tags": ["..."],
  "relevance_score": 1,
  "quality_score": 1,
  "novelty_claim_score": 1,
  "clarity_score": 1,
  "potential_impact_score": 1,
  "overall_priority_score": 1
}

# Scoring Hints
- relevance_score: alignment with my interests.
- quality_score: how rigorous/credible the contribution seems from abstract (method + eval signals).
- novelty_claim_score: strength of novelty claim.
- overall_priority_score: prioritize papers that are BOTH relevant AND high-quality.
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
    p["clarity_score"] = _clamp_score(p.get("clarity_score", 0))
    p["potential_impact_score"] = _clamp_score(p.get("potential_impact_score", 0))
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
    low_hits = _keyword_hits(text, LOW_SIGNAL_KEYWORDS)
    deemph_hits = _keyword_hits(text, DEEMPHASIZED_KEYWORDS)
    concept_hits = _keyword_hits(text, CONCEPT_STACKING_KEYWORDS)
    evidence_hits = _keyword_hits(text, EVIDENCE_KEYWORDS)
    author_hits = _author_hits(p)
    n_authors = _author_count(p)

    # 轻量打分修正：高信号 + 大牛略微加分；明显低信号轻微减分
    boost = 0.0
    boost += min(0.8, 0.15 * len(hs_hits))
    boost += min(0.4, 0.10 * len(bt_hits))
    boost += 0.35 if author_hits else 0.0

    # 低信号惩罚：benchmark/dataset 属于“软惩罚”（有时也可能是高质量 insight 论文）
    soft_low = {"dataset", "benchmark", "leaderboard"}
    soft_cnt = 0
    heavy_cnt = 0
    for h in low_hits:
        hl = (h or "").strip().lower()
        if hl in soft_low:
            soft_cnt += 1
        else:
            heavy_cnt += 1
    boost -= min(0.7, 0.15 * float(heavy_cnt) + 0.05 * float(soft_cnt))

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

    # “窄场景工程 + 低实质”更严格下压
    if len(low_hits) >= 2 and len(evidence_hits) == 0 and p["quality_score"] <= 6.0:
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
    p["signal_low_keywords"] = low_hits[:10]
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
                "clarity_score": 0,
                "potential_impact_score": 0,
                "tldr": "",
                "tldr_zh": "",
                "tags": [],
            }
        )
        return paper

    prompt = rating_prompt_template % (title, abstract, interests)
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
            raw = await default_chat_completion_text(
                namespace="paper_rating",
                messages=messages,
                max_tokens=4096,
                temperature=0.3,
            )
            raw2 = _extract_json_object(raw)
            try:
                data = json.loads(raw2)
            except json.JSONDecodeError:
                repaired = await _repair_to_valid_json(namespace="paper_rating_repair", raw=raw2)
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

            paper.update(data)
            logging.info(
                f"评分 {idx+1}/{total}: keep={paper.get('keep')} score={paper.get('overall_priority_score')} title='{title[:60]}'"
            )
            return paper

        except Exception as e:
            last_err = e
            logging.warning(
                f"评分失败 {idx+1}/{total} attempt={attempt+1}/{api_retries} title='{title[:60]}': {e}"
            )

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
    - 可选：`AZURE_ENDPOINT` / `AZURE_MODEL_NAME` / `AZURE_QPM` 等
    """
    interests = interests or DEFAULT_INTERESTS
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
    rated = rate_papers(test_papers, interests=DEFAULT_INTERESTS)
    print(json.dumps(rated[0], ensure_ascii=False, indent=2))
