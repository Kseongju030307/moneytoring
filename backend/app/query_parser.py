import json
import re
from typing import Any, Dict

from app.llm_client import generate_text
from app.prompts import build_parser_prompt


def default_parsed_query() -> Dict[str, Any]:
    return {
        "quarters": [],
        "metrics": [],
        "business_units": [],
        "intent": "general",
    }


def parse_json_response(text: str) -> Dict[str, Any]:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return json.loads(text)


def parse_query_with_llm(question: str) -> Dict[str, Any]:
    prompt = build_parser_prompt(question)
    raw_text = generate_text(prompt, temperature=0)
    return parse_json_response(raw_text)


def parse_query(question: str) -> Dict[str, Any]:
    result = default_parsed_query()

    try:
        parsed = parse_query_with_llm(question)
        result.update(parsed)
    except Exception:
        return result

    quarters = result.get("quarters", [])
    metrics = result.get("metrics", [])
    business_units = result.get("business_units", [])

    if isinstance(quarters, str):
        quarters = [quarters]
    if isinstance(metrics, str):
        metrics = [metrics]
    if isinstance(business_units, str):
        business_units = [business_units]

    result["quarters"] = quarters
    result["metrics"] = metrics
    result["business_units"] = business_units

    if result.get("intent") not in ["general", "financial"]:
        result["intent"] = "general"

    return result