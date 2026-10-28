#!/usr/bin/env python3
"""
Build the data file for the searchable model browser (docs/index.html).

Parses README.md and writes docs/models.json with every provider and model.
Uses only the Python standard library.

Usage:
    python scripts/build_site.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
OUTPUT = ROOT / "docs" / "models.json"

SECTIONS = {
    "Replenishable Providers": "replenishable",
    "Non-Replenishable Providers": "non-replenishable",
}

PROVIDER_RE = re.compile(r"^### \[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)")
FIELD_RE = re.compile(r"^\S+ \*\*(?P<label>[^*:]+):\*\*\s*(?P<value>.*)$")
CAPABILITY_ROW_RE = re.compile(r"^\| \*\*Status\*\* \|")
MODEL_ROW_RE = re.compile(r"^\| (?P<ids>`[^|]+`) *\|(?P<rest>.*)\|\s*$")
CAPABILITY_NAMES = ["tool_calls", "schema", "error_handling", "rate_limit_safe"]
CAPABILITY_SYMBOLS = {"✅": "yes", "⚠️": "partial", "❌": "no"}


def parse_context(value):
    """Convert '128K' / '1M' / 'Varies' into a token count (None when unknown)."""
    match = re.fullmatch(r"([\d.]+)\s*([KM])", value.strip(), re.IGNORECASE)
    if not match:
        return None
    number, unit = float(match.group(1)), match.group(2).upper()
    return int(number * (1_000 if unit == "K" else 1_000_000))


def parse_latency(value):
    """Convert '~1.4s' / '~850ms' into seconds (None when unknown)."""
    match = re.search(r"([\d.]+)\s*(ms|s)\b", value)
    if not match:
        return None
    number = float(match.group(1))
    return round(number / 1000 if match.group(2) == "ms" else number, 3)


def strip_markdown(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("`", "").replace("**", "").strip()


def parse_readme(text):
    providers = []
    section = None
    provider = None
    expect_description = False

    for line in text.splitlines():
        if line.startswith("## "):
            section = SECTIONS.get(line[3:].strip())
            provider = None
            continue
        if section is None:
            continue

        match = PROVIDER_RE.match(line)
        if match:
            provider = {
                "name": match.group("name"),
                "url": match.group("url"),
                "anchor": re.sub(r"[^a-z0-9 -]", "", match.group("name").lower()).replace(" ", "-"),
                "type": section,
                "description": "",
                "quota": "",
                "base_url": "",
                "base_url_note": "",
                "verified": "",
                "capabilities": {},
                "models": [],
            }
            providers.append(provider)
            expect_description = True
            continue
        if provider is None:
            continue

        stripped = line.strip()
        if expect_description and stripped:
            if not stripped.startswith("|"):
                provider["description"] = strip_markdown(stripped)
            expect_description = False
            continue

        match = FIELD_RE.match(stripped)
        if match:
            label, value = match.group("label"), match.group("value")
            if label == "Free Tier Quota":
                provider["quota"] = strip_markdown(value)
            elif label == "Base URL":
                url = re.search(r"`([^`]+)`", value)
                provider["base_url"] = url.group(1) if url else strip_markdown(value)
                provider["base_url_note"] = strip_markdown(value[url.end():] if url else "").strip("() ")
            elif label == "Verified":
                provider["verified"] = strip_markdown(value)
            continue

        if CAPABILITY_ROW_RE.match(stripped):
            cells = [c.strip() for c in stripped.strip("|").split("|")[1:]]
            provider["capabilities"] = {
                name: CAPABILITY_SYMBOLS.get(cell, "unknown")
                for name, cell in zip(CAPABILITY_NAMES, cells)
            }
            continue

        match = MODEL_ROW_RE.match(stripped)
        if match:
            cells = [c.strip() for c in match.group("rest").split("|")]
            if len(cells) < 3:
                continue
            context, best_for, latency = cells[0], strip_markdown(cells[1]), cells[2]
            ids = re.findall(r"`([^`]+)`", match.group("ids"))
            provider["models"].append({
                "id": ids[0],
                "aliases": ids[1:],
                "context": context,
                "context_tokens": parse_context(context),
                "best_for": best_for,
                "latency": latency,
                "latency_s": parse_latency(latency),
            })

    return providers


def main():
    providers = parse_readme(README.read_text(encoding="utf-8"))
    if not providers:
        sys.exit("No providers found in README.md -- has the format changed?")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"providers": providers}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    model_count = sum(len(p["models"]) for p in providers)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(providers)} providers, {model_count} models")
    for p in providers:
        if not p["models"] or not p["base_url"]:
            print(f"  warning: {p['name']} has {len(p['models'])} models, base URL {p['base_url'] or 'missing'}")


if __name__ == "__main__":
    main()
