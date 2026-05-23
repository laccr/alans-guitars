from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class QuerySpec(BaseModel):
    """User's search criteria for a specific guitar.

    This is the single contract every scraper, matcher, and outreach template depends on.
    Keep it stable.
    """

    brand: str | None = Field(default=None, description="e.g. 'Fender', 'Gibson', 'Martin'.")
    model: str | None = Field(default=None, description="e.g. 'Jaguar', 'Les Paul Standard'.")

    year_min: int | None = Field(default=None, ge=1900, le=2100)
    year_max: int | None = Field(default=None, ge=1900, le=2100)

    finish: str | None = Field(
        default=None,
        description="Free text finish/color, e.g. 'sunburst', 'candy apple red'.",
    )

    conditions: list[str] = Field(
        default_factory=list,
        description="Acceptable conditions, e.g. ['new', 'used', 'vintage', 'mint']. Empty = any.",
    )

    max_price_usd: float | None = Field(default=None, ge=0)
    min_price_usd: float | None = Field(default=None, ge=0)

    must_have: list[str] = Field(
        default_factory=list,
        description="Substrings that must appear in title or description (case-insensitive).",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Substrings whose presence disqualifies a listing.",
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="Free-form extra keywords passed to upstream search APIs.",
    )

    all_original_only: bool = Field(
        default=False,
        description=(
            "If True, exclude listings whose titles/descriptions indicate refins, partscasters, "
            "or non-original electronics."
        ),
    )

    @model_validator(mode="after")
    def _validate_ranges(self) -> QuerySpec:
        if self.year_min is not None and self.year_max is not None and self.year_min > self.year_max:
            raise ValueError("year_min cannot exceed year_max")
        if (
            self.min_price_usd is not None
            and self.max_price_usd is not None
            and self.min_price_usd > self.max_price_usd
        ):
            raise ValueError("min_price_usd cannot exceed max_price_usd")
        return self

    def display(self) -> str:
        parts: list[str] = []
        if self.brand:
            parts.append(self.brand)
        if self.model:
            parts.append(self.model)
        if self.year_min or self.year_max:
            parts.append(f"{self.year_min or '?'}-{self.year_max or '?'}")
        if self.finish:
            parts.append(self.finish)
        if self.max_price_usd:
            parts.append(f"<=${self.max_price_usd:,.0f}")
        return " ".join(parts) or "(any guitar)"
