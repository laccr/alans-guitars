from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

KNOWN_BRANDS: tuple[str, ...] = (
    "Fender",
    "Gibson",
    "Martin",
    "Taylor",
    "Gretsch",
    "Rickenbacker",
    "Guild",
    "Epiphone",
    "Squier",
    "Jackson",
    "Charvel",
    "ESP",
    "LTD",
    "Ibanez",
    "PRS",
    "Paul Reed Smith",
    "Music Man",
    "Ernie Ball",
    "Schecter",
    "Yamaha",
    "Washburn",
    "Dean",
    "B.C. Rich",
    "Hagstrom",
    "Hofner",
    "Höfner",
    "Eastman",
    "Collings",
    "Santa Cruz",
    "Bourgeois",
    "Huss & Dalton",
    "Larrivee",
    "Larrivée",
    "Goodall",
    "Lowden",
    "Furch",
    "Cordoba",
    "Córdoba",
    "Takamine",
    "Seagull",
    "Godin",
    "Recording King",
    "Blueridge",
    "National",
    "Dobro",
    "Danelectro",
    "Silvertone",
    "Harmony",
    "Kay",
    "Supro",
    "Vox",
    "Magnatone",
    "Mosrite",
    "Hamer",
    "G&L",
    "Suhr",
    "Tom Anderson",
    "Anderson",
    "Knaggs",
    "Nik Huber",
    "Huber",
    "James Tyler",
    "Tyler",
    "Don Grosh",
    "Grosh",
    "Reverend",
    "Eastwood",
    "Heritage",
    "Hahn",
    "Nash",
    "K-Line",
    "Fano",
    "DeArmond",
    "Carvin",
    "Kiesel",
    "Steinberger",
)


_YEAR_RE = re.compile(r"\b(19[2-9]\d|20[0-2]\d)\b")
_DECADE_RE = re.compile(r"\b(19[2-9]0|20[0-2]0)s\b", re.IGNORECASE)
_FINISH_HINTS: tuple[str, ...] = (
    "sunburst",
    "3-tone sunburst",
    "two-tone sunburst",
    "tobacco burst",
    "honey burst",
    "cherry burst",
    "vintage burst",
    "black",
    "white",
    "olympic white",
    "vintage white",
    "candy apple red",
    "fiesta red",
    "dakota red",
    "shell pink",
    "surf green",
    "sea foam green",
    "sonic blue",
    "lake placid blue",
    "ice blue metallic",
    "ocean turquoise",
    "shoreline gold",
    "burgundy mist",
    "natural",
    "blonde",
    "butterscotch",
    "ash",
    "mahogany",
    "korina",
    "tv yellow",
    "goldtop",
    "gold top",
    "wine red",
    "cherry red",
    "ebony",
    "alpine white",
    "antique white",
    "pelham blue",
    "sparkle",
    "metallic",
)


@dataclass
class NormalizedTitle:
    brand: str | None
    model: str | None
    year: int | None
    year_confidence: float
    finish: str | None


def _find_brand(text: str) -> str | None:
    lower = text.lower()
    # Prefer longest match so "Paul Reed Smith" beats "PRS" when both appear.
    best: str | None = None
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if brand.lower() in lower:
            if best is None or len(brand) > len(best):
                best = brand
            break
    return best


def _find_year(text: str) -> tuple[int | None, float]:
    """Return (year, confidence). Decade-only references get low confidence."""
    current_year = datetime.now().year
    m = _YEAR_RE.search(text)
    if m:
        y = int(m.group(1))
        if 1920 <= y <= current_year + 1:
            return y, 0.85
    dm = _DECADE_RE.search(text)
    if dm:
        y = int(dm.group(1))
        return y, 0.35
    return None, 0.0


def _find_finish(text: str) -> str | None:
    lower = text.lower()
    best: str | None = None
    for finish in sorted(_FINISH_HINTS, key=len, reverse=True):
        if finish in lower and (best is None or len(finish) > len(best)):
            best = finish
    return best


def _find_model(text: str, brand: str | None) -> str | None:
    """Best-effort extraction of the chunk between the brand and a year/condition marker.

    This is intentionally light. The matcher does fuzzy comparison, so we just need
    a reasonable substring — we don't need a curated model catalog.
    """
    if not brand:
        return None
    pattern = re.escape(brand)
    m = re.search(pattern + r"\s+(.+?)(?:\s+(?:19|20)\d{2}|\s+-\s|$)", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip(" -")
        candidate = re.sub(r"\s+", " ", candidate)
        if 1 <= len(candidate) <= 80:
            return candidate
    return None


def normalize_title(title: str, description: str | None = None) -> NormalizedTitle:
    """Parse a raw listing title (+ optional description) into structured fields."""
    text = title if description is None else f"{title} {description}"
    brand = _find_brand(text)
    year, year_conf = _find_year(text)
    finish = _find_finish(text)
    model = _find_model(text, brand)
    return NormalizedTitle(
        brand=brand, model=model, year=year, year_confidence=year_conf, finish=finish
    )
