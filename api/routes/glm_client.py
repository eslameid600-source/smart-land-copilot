"""
============================================================
 Smart Land Management Copilot — GLM LLM Client v4.0
============================================================
Handles the "Generation" half of the RAG pipeline and the
Advanced Investment Rating & Matchmaking analysis.

Three prompt modes:
  1. CHAT MODE            — Standard RAG (user query + retrieved context)
  2. MATCHMAKING          — Investor criteria + ranked compatibility results
  3. ADVISORY_REPORT      — Rigorous feasibility report from Smart Match (NEW)

Default model: GLM-5 Turbo (via OpenRouter-compatible API)

Environment Variables
---------------------
  GLM_API_KEY    — Your API key
  GLM_BASE_URL   — API base URL (default: OpenRouter)
  GLM_MODEL      — Model identifier (default: glm-5-turbo)
============================================================
"""

import os
import json
import logging
import requests
from typing import Generator, List, Optional

logger = logging.getLogger(__name__)


# ----------------------------------------------------------
# 1. CONFIGURATION
# ----------------------------------------------------------

def _get_config() -> dict:
    """Load API configuration from environment variables."""
    return {
        "api_key": os.environ.get("GLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", "")),
        "base_url": os.environ.get(
            "GLM_BASE_URL",
            "https://openrouter.ai/api/v1",
        ),
        "model": os.environ.get("GLM_MODEL", "glm-5-turbo"),
    }


# ----------------------------------------------------------
# 2. PROMPT ENGINEERING — Three Modes
# ----------------------------------------------------------

SYSTEM_PROMPT_CHAT = """\
You are the "Smart Land Management Copilot" — an expert investment \
advisory AI specializing in Egyptian land and real estate markets. \
Your role is to help investors evaluate land parcels for their \
project needs by providing data-driven, professional feasibility insights.

RULES:
1. Base your analysis ONLY on the retrieved land records provided below. \
   Do NOT fabricate data or make up land parcels that are not in the database.
2. For each recommended land, discuss: location advantages, soil suitability, \
   infrastructure readiness, pricing, and alignment with the investor's project type.
3. If no lands match the query, clearly state that and suggest what criteria \
   to relax (e.g., "Consider expanding your search to neighboring governorates").
4. Keep your tone professional, concise, and investment-focused.
5. Use EGP for all monetary values. Mention relevant Egyptian laws or \
   investment incentives when applicable (e.g., Investment Law No. 72/2017).
6. Structure your response with clear headings and bullet points for readability.
7. Always end with a disclaimer that this is an AI-generated advisory and \
   the investor should verify with the New Urban Communities Authority (NUCA) \
   or the General Authority for Investment (GAFI).
"""

SYSTEM_PROMPT_MATCHMAKING = """\
You are the "Smart Land Management Copilot" — a proactive investment \
matchmaking AI for Egyptian land markets.  An investor has specified \
their exact requirements, and the system has ranked ALL available \
lands by compatibility percentage.

YOUR TASK:
1. Start by saying (in Arabic and English):
   "Based on your specified criteria, here are the best lands in Egypt \
   that match your investment requirements, ranked by compatibility."
2. For each of the TOP 3-5 lands (those with highest compatibility), \
   provide a detailed analysis covering:
   - Why this land matches the investor's criteria (strengths)
   - Any gaps or shortcomings (e.g., missing a utility, area slightly small)
   - Economic advantages (proximity to ports, highways, tax incentives)
   - If the land is an AUCTION, highlight the auction date, starting price, \
     and whether it represents good value vs. direct-sale alternatives.
3. Compare the top 2 options and make a final recommendation.
4. If auction lands appear, advise the investor on auction strategy.
5. Use EGP for all monetary values.
6. End with the standard NUCA/GAFI disclaimer.
"""

SYSTEM_PROMPT_ADVISORY = """\
You are the "Smart Land Management Copilot" — a senior investment \
advisory AI producing rigorous, institutional-grade feasibility reports \
for the Egyptian real estate market. You are now generating an \
"Advisory Feasibility Report" based on the system's advanced \
Investment Rating and Matchmaking results.

CONTEXT: The platform has analyzed ALL land parcels in its database \
against the investor's exact criteria using a 7-dimension scoring engine \
(Usage, Area, Price, Utilities, Land Quality Rating, Auction Status, \
Governorate). Each land has been assigned a Compatibility Score (0-100%) \
and a Land Quality Rating (AAA/AA/A/B) based on utilities availability \
and proximity to highways and seaports.

REPORT STRUCTURE (MUST follow this exactly):

## 1. Executive Summary (Arabic + English)
   - 2-3 sentence overview of findings
   - Total lands analyzed, top matches count

## 2. Investor Profile Assessment
   - Restate the investor's criteria
   - Classify the investor's likely profile: Strategic Developer or Financial Buyer
   - Note the risk tolerance and investment horizon implications

## 3. Top Match Analysis (for each of the top 3-5 matches)
For EACH matched land, provide:

### [Land ID] — [Location] (Compatibility: X% | Quality: Y)
   **Match Strengths:**
   - List each matching dimension with its score contribution
   - Explain WHY this land suits the investor's project capability
   - Highlight infrastructure readiness (utilities, roads, grid capacity)

   **Gap Analysis & Mitigation:**
   - List each warning/gap
   - Provide specific mitigation strategies for each gap
   - Estimate remediation cost if applicable (in EGP)

   **Investment Viability:**
   - Total investment required (land + estimated development)
   - ROI projection based on market trend
   - Risk factors (geological, environmental, regulatory)
   - Auction strategy IF this is a Public Auction listing

## 4. Comparative Analysis
   - Side-by-side comparison table of top 3 options
   - Rank by: compatibility, value-for-money, risk-adjusted return
   - Identify the "Best Value" and "Lowest Risk" options

## 5. Strategic Recommendation
   - Clear recommendation: which land to pursue and why
   - If auction: bidding strategy (max bid, walk-away price)
   - Next steps: due diligence checklist, NUCA/GAFI verification
   - Potential deal structuring (phased acquisition, joint venture)

## 6. Disclaimer
   - Standard NUCA/GAFI verification disclaimer
   - Market data as-of-date notice

CRITICAL RULES:
1. Use ONLY the matched land data provided below. Do NOT fabricate parcels.
2. Reference Land Quality Ratings explicitly (AAA = Prime, AA = High, A = Standard, B = Basic).
3. All monetary values in EGP.
4. Reference Egyptian laws: Investment Law No. 72/2017, Real Estate Tax Law.
5. Be specific — use actual numbers from the data, not vague estimates.
6. The report must be actionable — an investor should be able to make a \
   decision after reading it.
7. Write in professional English with Arabic section headers where appropriate.
"""


def build_rag_prompt(user_query: str, context_text: str) -> list:
    """Construct messages for standard chat-based RAG."""
    user_message = f"""\
Below are the land records retrieved from the Egyptian Land Database that are \
most relevant to the investor's query.

--- BEGIN RETRIEVED CONTEXT ---
{context_text}
--- END RETRIEVED CONTEXT ---

INVESTOR QUERY:
"{user_query}"

Please provide a professional feasibility analysis based ONLY on the above \
land records. Recommend the best matches, explain why they fit, and highlight \
any risks or considerations."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT_CHAT},
        {"role": "user", "content": user_message},
    ]


def build_matchmaking_prompt(
    criteria_summary: str,
    context_text: str,
) -> list:
    """
    Construct messages for the proactive matchmaking scenario.

    Parameters
    ----------
    criteria_summary : Human-readable summary of what the investor selected
    context_text     : Formatted land records with compatibility percentages
    """
    user_message = f"""\
An investor has used the "Proactive Investor Matchmaking" feature and specified \
the following exact criteria:

--- INVESTOR CRITERIA ---
{criteria_summary}
--- END CRITERIA ---

The system has analyzed ALL lands in the database and ranked them by compatibility. \
Here are the results:

--- BEGIN RANKED LAND RESULTS ---
{context_text}
--- END RANKED LAND RESULTS ---

Please provide a comprehensive matchmaking analysis as described in your \
instructions. Focus on the highest-compatible lands, highlight any AUCTION \
opportunities, and make a clear final recommendation."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT_MATCHMAKING},
        {"role": "user", "content": user_message},
    ]


def build_advisory_report_prompt(
    criteria_summary: str,
    match_context: str,
) -> list:
    """
    Construct messages for the Advisory-Grade Feasibility Report.

    This is the most advanced prompt mode, used by the "Investor Smart Match"
    dashboard. It takes structured match results with per-dimension scores
    and generates a full institutional-grade report.

    Parameters
    ----------
    criteria_summary : Human-readable summary of investor criteria
    match_context    : Formatted match results from
                       rag/search_engine.format_match_results_for_llm()
    """
    user_message = f"""\
An investor has used the "Investor Smart Match" feature with the following criteria:

--- INVESTOR CRITERIA ---
{criteria_summary}
--- END CRITERIA ---

The system's Advanced Compatibility Scoring Engine (7-dimension, 100-point scale) \
has analyzed ALL lands and produced the following ranked results with per-dimension \
score breakdowns:

--- BEGIN MATCH ENGINE RESULTS ---
{match_context}
--- END MATCH ENGINE RESULTS ---

Please generate the full Advisory Feasibility Report as described in your \
system instructions. Focus on the top matches, provide specific numbers \
from the data, and make a clear actionable recommendation."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT_ADVISORY},
        {"role": "user", "content": user_message},
    ]


# ----------------------------------------------------------
# 3. API CALL (Non-Streaming)
# ----------------------------------------------------------

def call_glm_api(
    user_query: str,
    context_text: str,
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """Call the GLM API and return the full response string."""
    config = _get_config()

    if not config["api_key"]:
        return _mock_response(user_query, context_text)

    messages = build_rag_prompt(user_query, context_text)

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"API call failed: {e}\n\nPlease check your GLM_API_KEY and network connection."


# ----------------------------------------------------------
# 4. API CALL (Streaming) — CHAT MODE
# ----------------------------------------------------------

def stream_glm_api(
    user_query: str,
    context_text: str,
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> Generator[str, None, None]:
    """Streaming variant for standard chat — yields text chunks."""
    config = _get_config()

    if not config["api_key"]:
        mock = _mock_response(user_query, context_text)
        for chunk in _chunk_text(mock):
            yield chunk
        return

    messages = build_rag_prompt(user_query, context_text)
    yield from _stream_messages(messages, config, temperature, max_tokens)


# ----------------------------------------------------------
# 5. API CALL (Streaming) — MATCHMAKING MODE
# ----------------------------------------------------------

def stream_matchmaking_api(
    criteria_summary: str,
    context_text: str,
    temperature: float = 0.4,
    max_tokens: int = 3000,
) -> Generator[str, None, None]:
    """
    Streaming variant for the proactive matchmaking scenario.
    Uses a specialized system prompt and a larger max_tokens
    budget since the analysis is more detailed.
    """
    config = _get_config()

    if not config["api_key"]:
        mock = _mock_matchmaking_response(criteria_summary, context_text)
        for chunk in _chunk_text(mock):
            yield chunk
        return

    messages = build_matchmaking_prompt(criteria_summary, context_text)
    yield from _stream_messages(messages, config, temperature, max_tokens)


# ----------------------------------------------------------
# 6. API CALL (Streaming) — ADVISORY REPORT MODE (NEW)
# ----------------------------------------------------------

def stream_advisory_report(
    criteria_summary: str,
    match_context: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """
    Streaming variant for the Advisory-Grade Feasibility Report.

    This is the premium output mode used by the Investor Smart Match
    dashboard. It produces a comprehensive, institutional-grade report
    with the largest token budget and lowest temperature for maximum
    analytical rigor.

    Parameters
    ----------
    criteria_summary : Human-readable investor criteria string
    match_context    : Structured match results from
                       rag/search_engine.format_match_results_for_llm()
    temperature      : Low (0.3) for consistent, analytical output
    max_tokens       : 4096 for full report length
    """
    config = _get_config()

    if not config["api_key"]:
        mock = _mock_advisory_report(criteria_summary, match_context)
        for chunk in _chunk_text(mock):
            yield chunk
        return

    messages = build_advisory_report_prompt(criteria_summary, match_context)
    yield from _stream_messages(messages, config, temperature, max_tokens)


def call_advisory_report(
    criteria_summary: str,
    match_context: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Non-streaming variant of the advisory report (for programmatic use)."""
    config = _get_config()

    if not config["api_key"]:
        return _mock_advisory_report(criteria_summary, match_context)

    messages = build_advisory_report_prompt(criteria_summary, match_context)

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"Advisory Report API call failed: {e}"


# ----------------------------------------------------------
# INTERNAL HELPERS
# ----------------------------------------------------------

def _stream_messages(messages, config, temperature, max_tokens):
    """Shared streaming logic for all three modes."""
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        with requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except requests.exceptions.RequestException as e:
        yield f"Streaming failed: {e}"


def _chunk_text(text: str, chunk_size: int = 6) -> Generator[str, None, None]:
    """Split text into small chunks for simulated streaming."""
    words = text.split(" ")
    buffer = ""
    for w in words:
        buffer += w + " "
        if len(buffer) > chunk_size:
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


# ----------------------------------------------------------
# MOCK RESPONSES (Prototype Fallback)
# ----------------------------------------------------------

def _mock_response(user_query: str, context_text: str) -> str:
    """Mock response for standard chat demo mode."""
    if "No matching land records" in context_text:
        return (
            "Based on your query, no matching land records were found in the current "
            "database. I recommend broadening your search criteria — for example, "
            "considering adjacent governorates or a wider range of land-use categories. "
            "Feel free to ask with different keywords."
        )

    return (
        "## Feasibility Analysis (Demo Mode)\n\n"
        "The following recommendations are based on the retrieved land records:\n\n"
        f"{context_text}\n\n"
        "**Note:** This is a mock response generated in demo mode (no API key configured). "
        "To receive AI-powered feasibility insights, set the `GLM_API_KEY` environment "
        "variable and restart the application.\n\n"
        "---\n"
        "*Disclaimer: This is an AI-generated advisory. Always verify with the "
        "New Urban Communities Authority (NUCA) or the General Authority for "
        "Investment and Free Zones (GAFI) before making investment decisions.*"
    )


def _mock_matchmaking_response(criteria_summary: str, context_text: str) -> str:
    """Mock response for matchmaking demo mode."""
    return (
        "## Proactive Matchmaking Report (Demo Mode)\n\n"
        f"**Your Criteria:** {criteria_summary}\n\n"
        "---\n\n"
        f"{context_text}\n\n"
        "---\n\n"
        "**Top Recommendation:** Based on the compatibility scores above, "
        "the highest-ranked land(s) best match your requirements. "
        "Review the compatibility percentage and match details for each option.\n\n"
        "**Auction Opportunities:** Check the lands marked as 'Public Auction' — "
        "they may offer better value than direct-sale options.\n\n"
        "**Note:** This is a mock response generated in demo mode (no API key configured). "
        "To receive AI-powered matchmaking analysis, set the `GLM_API_KEY` environment "
        "variable and restart the application.\n\n"
        "---\n"
        "*Disclaimer: This is an AI-generated advisory. Always verify with NUCA or GAFI.*"
    )


def _mock_advisory_report(criteria_summary: str, match_context: str) -> str:
    """Mock response for advisory report demo mode."""
    return (
        "## Advisory Feasibility Report (Demo Mode)\n"
        "=========================================\n\n"
        "### 1. Executive Summary\n"
        "The Smart Match engine has analyzed all available land parcels against "
        "your investment criteria. The top matches are presented below with "
        "detailed feasibility analysis.\n\n"
        f"**Investor Criteria:** {criteria_summary}\n\n"
        "---\n\n"
        f"{match_context}\n\n"
        "---\n\n"
        "### Strategic Recommendation\n"
        "Based on the compatibility scores and quality ratings above, the "
        "highest-ranked land(s) represent the best match for your investment "
        "profile. Review the per-dimension score breakdowns to understand "
        "each land's strengths and gaps.\n\n"
        "**Land Quality Ratings Explained:**\n"
        "- **AAA (Prime)**: All 4 utilities available, highway <= 3km, port <= 50km\n"
        "- **AA (High)**: 3+ utilities, highway <= 5km, port <= 100km\n"
        "- **A (Standard)**: 2+ utilities, highway <= 10km\n"
        "- **B (Basic)**: Below the above thresholds\n\n"
        "**Note:** This is a mock report generated in demo mode (no API key configured). "
        "To receive AI-powered advisory-grade feasibility reports, set the `GLM_API_KEY` "
        "environment variable and restart the application.\n\n"
        "---\n"
        "*Disclaimer: This is an AI-generated advisory. Always verify with NUCA or GAFI.*"
    )