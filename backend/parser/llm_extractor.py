"""
llm_extractor.py
────────────────
Calls Gemini 2.5 Flash to extract structured ProductRecord data from
raw crawled text. Handles JSON parsing errors gracefully and respects
the Gemini free-tier 15 RPM limit with a 4-second inter-call delay.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from ..crawler.models import CrawlRecord
from .field_validator import compute_confidence
from .pdf_table_parser import extract_tables_text

logger = logging.getLogger(__name__)

# Minimum characters for a page to be worth parsing
MIN_TEXT_LENGTH = 200

# Delay between Gemini calls to stay under 15 RPM free-tier limit
GEMINI_INTER_CALL_DELAY = 4.0

EXTRACTION_PROMPT = """\
You are a construction chemicals expert. Extract structured product information
from the MYK Laticrete content below and return it as a single JSON object.

CONTENT:
{content}

Return a JSON object with EXACTLY these keys (use null for unknown values):
{{
  "sku": "string or null",
  "product_name": "string (required)",
  "product_family": "one of: tile_adhesive | specialty_adhesive | stone_adhesive | grout | waterproofing | surface_prep | stone_care | cleaning | screed | sound_control | cement_additive | 3d_mortar",
  "description": "string or null",
  "technical_specs": {{
    "open_time": "string with units or null",
    "pot_life": "string with units or null",
    "coverage_rate": "string with units or null",
    "compressive_strength": "string with units or null",
    "shear_bond_strength": "string with units or null",
    "application_thickness": "string with units or null",
    "cure_time": "string with units or null",
    "mixing_ratio": "string with units or null",
    "temperature_range": "string with units or null"
  }},
  "grade_classification": "string or null (e.g. C2TE S1, C1, etc.)",
  "substrate_compatibility": ["list", "of", "substrates"],
  "tile_compatibility": ["list", "of", "tile", "types"],
  "recommended_use_cases": ["list", "of", "use", "cases"],
  "packaging": {{
    "sizes": ["list", "of", "pack", "sizes"],
    "shelf_life": "string or null"
  }}
}}

Rules:
- Include units in ALL numeric values (e.g. "20-30 minutes", "5 kg/m²")
- Use null for any field you cannot find — do NOT guess
- Return ONLY valid JSON — no markdown, no commentary
"""


def _build_llm():
    """Instantiate LLM (Gemini 2.5 Flash, Groq, or OpenRouter fallback)."""
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    # Load .env from backend/ relative to this file, then from repo root
    _here = Path(__file__).resolve()
    for candidate in [
        _here.parents[1] / ".env",          # backend/.env  (parents[1] = backend/)
        _here.parents[2] / ".env",          # repo root .env (parents[2] = scraper/)
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break

    # 1. Groq Free Tier — fastest, try first
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_base="https://api.groq.com/openai/v1",
            openai_api_key=groq_key,
            model_name="llama-3.3-70b-versatile",
            temperature=0.0
        )

    # 2. Gemini 2.5 Flash — 1M tokens/day free, high quality JSON extraction
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=api_key,
            max_retries=1,
        )

    # 3. OpenRouter Free Tier — last resort
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=openrouter_key,
            model_name="meta-llama/llama-3-8b-instruct:free",
            temperature=0.0
        )

    raise EnvironmentError(
        "No LLM API key found. Set GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY in backend/.env."
    )


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` fences Gemini sometimes adds."""
    text = text.strip()
    # Remove opening fence
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    # Remove closing fence
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _truncate(text: str, max_chars: int = 8000) -> str:
    """Truncate text to fit within Gemini context budget."""
    if len(text) <= max_chars:
        return text
    # Keep first 6000 + last 2000 chars to preserve both header and spec tables
    return text[:6000] + "\n...[TRUNCATED]...\n" + text[-2000:]


def extract_product_from_record(
    record: CrawlRecord,
    llm = None,
) -> Optional[dict]:
    """
    Extract a structured product dict from a CrawlRecord using Gemini.

    Args:
        record: A CrawlRecord from the crawler output.
        llm:    Optional pre-built LLM instance (for batching without re-init).

    Returns:
        A dict matching the ProductRecord schema, or None if the page is
        unsuitable (too short, no product info, or JSON parse failure).
    """
    # Skip pages that are clearly not product pages
    if not record.text or len(record.text) < MIN_TEXT_LENGTH:
        logger.debug("Skipping %s — text too short (%d chars)", record.url, len(record.text or ""))
        return None

    if llm is None:
        llm = _build_llm()

    # Augment PDF content with reformatted table text
    content = record.text
    if record.content_type == "pdf":
        table_text = extract_tables_text(record.text)
        if table_text:
            content = f"TABLES:\n{table_text}\n\nFULL TEXT:\n{content}"

    content = _truncate(content)
    prompt = EXTRACTION_PROMPT.format(content=content)
    data = None
    try:
        response = llm.invoke(prompt)
        raw = _strip_json_fences(response.content)
        data = json.loads(raw)
    except Exception as exc:
        exc_str = str(exc)
        if "429" in exc_str or "rate_limit" in exc_str or "quota" in exc_str:
            import os
            groq_key = os.environ.get("GROQ_API_KEY")
            if groq_key:
                logger.warning("Groq TPD limit reached for %s. Attempting silent fallback to llama-3.1-8b-instant...", record.url)
                try:
                    from langchain_openai import ChatOpenAI
                    import time
                    fallback_llm = ChatOpenAI(
                        openai_api_base="https://api.groq.com/openai/v1",
                        openai_api_key=groq_key,
                        model_name="llama-3.1-8b-instant",
                        temperature=0.0,
                        max_retries=5
                    )
                    # Try up to 3 times to handle 429 TPM limit
                    for attempt in range(3):
                        try:
                            response = fallback_llm.invoke(prompt)
                            raw = _strip_json_fences(response.content)
                            data = json.loads(raw)
                            break
                        except Exception as inner_exc:
                            inner_str = str(inner_exc)
                            if "429" in inner_str or "rate_limit" in inner_str:
                                logger.warning("Fallback LLM (Llama 8B) rate limited. Sleeping 15s before retry (attempt %d/3)...", attempt + 1)
                                if attempt == 2:
                                    raise inner_exc
                                time.sleep(15)
                            else:
                                raise inner_exc
                except Exception as fallback_exc:
                    logger.warning("Fallback Llama 8B also failed for %s: %s — trying Gemini 2.5 Flash...", record.url, fallback_exc)
                    # Final fallback: Gemini (try 2.5-flash first, then 1.5-flash)
                    gemini_key = os.environ.get("GEMINI_API_KEY")
                    if gemini_key:
                        try:
                            gemini_llm = ChatGoogleGenerativeAI(
                                model="gemini-2.5-flash",
                                temperature=0,
                                google_api_key=gemini_key,
                                max_retries=0,
                            )
                            response = gemini_llm.invoke(prompt)
                            raw = _strip_json_fences(response.content)
                            data = json.loads(raw)
                            logger.info("Gemini 2.5 Flash fallback succeeded for %s", record.url)
                        except Exception as gemini_exc:
                            logger.warning("Gemini 2.5 Flash failed: %s — trying Gemini Flash fallback...", gemini_exc)
                            try:
                                gemini_llm = ChatGoogleGenerativeAI(
                                    model="gemini-flash-latest",
                                    temperature=0,
                                    google_api_key=gemini_key,
                                    max_retries=1,
                                )
                                response = gemini_llm.invoke(prompt)
                                raw = _strip_json_fences(response.content)
                                data = json.loads(raw)
                                logger.info("Gemini Flash fallback succeeded for %s", record.url)
                            except Exception as gemini_flash_exc:
                                logger.error("Gemini Flash fallback also failed for %s: %s", record.url, gemini_flash_exc)
                                return None
                    else:
                        logger.error("All LLM fallbacks exhausted for %s", record.url)
                        return None
            else:
                logger.error("LLM call failed for %s: %s", record.url, exc)
                return None
        else:
            # Handle JSON parse errors or try partial salvage
            try:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                else:
                    return None
            except Exception:
                logger.error("LLM call failed for %s: %s", record.url, exc)
                return None

    # Guard: product_name is required
    if not data.get("product_name"):
        logger.debug("No product_name extracted from %s — skipping", record.url)
        return None

    # Enrich with provenance + scoring
    data["source_urls"] = [record.url]
    data["extracted_at"] = datetime.now(timezone.utc).isoformat()
    data["extraction_confidence"] = compute_confidence(data)
    data["needs_human_review"] = data["extraction_confidence"] < 0.6
    data.setdefault("version", 1)

    return data


def extract_batch(
    records: list,
    delay_seconds: Optional[float] = None,
) -> list[dict]:
    """
    Extract products from a batch of CrawlRecords, respecting rate limits.

    Args:
        records:       List of CrawlRecord objects.
        delay_seconds: Sleep between LLM calls (auto-tuned if None).

    Returns:
        List of successfully extracted product dicts (failures silently dropped).
    """
    llm = _build_llm()

    # Self-tuning rate limit delay based on the active provider
    if delay_seconds is None:
        import os
        if os.environ.get("GROQ_API_KEY"):
            # Groq free tier allows 30 RPM -> 4.2s delay helps avoid TPM (token rate limits)!
            delay_seconds = 4.2
            logger.info("Auto-tuning LLM rate limit delay to %.1fs for Groq provider", delay_seconds)
        elif os.environ.get("OPENROUTER_API_KEY"):
            delay_seconds = 1.0
            logger.info("Auto-tuning LLM rate limit delay to %.1fs for OpenRouter provider", delay_seconds)
        else:
            delay_seconds = GEMINI_INTER_CALL_DELAY
            logger.info("Auto-tuning LLM rate limit delay to %.1fs for Gemini provider", delay_seconds)

    results = []

    for i, record in enumerate(records):
        logger.info(
            "Parsing [%d/%d]: %s", i + 1, len(records), record.url
        )
        product = extract_product_from_record(record, llm=llm)
        if product:
            results.append(product)
        else:
            logger.info("  → No product extracted (skipped)")

        # Rate limit: sleep between calls, except after the last one
        if i < len(records) - 1:
            time.sleep(delay_seconds)

    logger.info("Extracted %d/%d products from batch", len(results), len(records))
    return results
