"""
NLP Parsing Engine — in-process, zero-latency metric extraction.

Returns a ParseResult with:
  metric_name  — extracted or matched name
  value        — first numeric value found
  confidence   — 0.0–1.0 parse confidence (independent of metric existence)
  outcome      — 'auto-parse' | 'ambiguous' | 'unrecognized'

Confidence semantics:
  >= threshold   → auto-parse (Entry Processor decides existing vs new metric)
  <  threshold   → unrecognized (Stage 2: would create ParseAttempt)
"""
import re
from dataclasses import dataclass, field
from typing import Literal

from rapidfuzz import fuzz, process as fuzz_process

_NUMBER_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\b")

# Common measurement words stripped from metric name candidates
_UNIT_RE = re.compile(
    r"\b(?:kg|kgs|lbs?|lb|km|mi|miles?|cm|mm|m|min|mins?|minutes?|hours?|hrs?|"
    r"steps?|reps?|sets?|cal|kcal|bpm|mmhg|mg|dl|ml|l)\b",
    re.IGNORECASE,
)

# Stopwords that add no metric-name signal
_STOP_RE = re.compile(
    r"\b(?:today|yesterday|this|morning|evening|night|just|now|did|i|my|a|an|the|"
    r"was|is|are|have|had|got|about|around|approximately|approx)\b",
    re.IGNORECASE,
)

# Minimum similarity score (0–100) to consider a name an EXISTING metric match
_SAME_METRIC_SIMILARITY = 75

# Minimum similarity score to include a metric as an ambiguous candidate
_AMBIGUOUS_FLOOR = 40


def fuzzy_match_metrics(
    typed_name: str,
    known_metrics: list[str],
    threshold: int,
) -> list[str]:
    """
    Return metric names from known_metrics whose token_set_ratio against
    typed_name meets or exceeds threshold (0–100 scale, SU-010).

    Kept strictly separate from the existing parse() disambiguation logic
    (_SAME_METRIC_SIMILARITY / _AMBIGUOUS_FLOOR) to avoid cross-contamination.
    Results are ordered by score descending.
    """
    if not known_metrics or not typed_name.strip():
        return []
    results = fuzz_process.extract(
        typed_name.strip().lower(),
        [m.lower() for m in known_metrics],
        scorer=fuzz.token_set_ratio,
        limit=None,
    )
    # Map lowercased names back to original casing via position
    lower_to_original = {m.lower(): m for m in known_metrics}
    return [
        lower_to_original[name]
        for name, score, _ in results
        if score >= threshold
    ]


@dataclass
class ParseResult:
    metric_name: str | None = None
    value: float | None = None
    dimension_assignments: dict | None = None
    confidence: float = 0.0
    outcome: Literal["auto-parse", "ambiguous", "unrecognized"] = "unrecognized"
    candidate_metrics: list[str] = field(default_factory=list)


def parse(text: str, known_metrics: list[str], threshold: float) -> ParseResult:
    """
    Parse free-text into a structured metric entry.

    known_metrics — names of metrics already created by this user.
    threshold     — confidence threshold from settings (SU-002).
    """
    # 1. Extract first numeric value
    num_match = _NUMBER_RE.search(text)
    if num_match is None:
        return ParseResult(outcome="unrecognized", confidence=0.0)

    value = float(num_match.group(1).replace(",", "."))

    # 2. Build metric name candidate from the remaining text
    name_candidate = _NUMBER_RE.sub(" ", text)
    name_candidate = _UNIT_RE.sub(" ", name_candidate)
    name_candidate = _STOP_RE.sub(" ", name_candidate)
    name_candidate = " ".join(name_candidate.split()).strip().lower()

    if not name_candidate:
        # Only a number — cannot determine metric, unrecognized
        return ParseResult(value=value, outcome="unrecognized", confidence=0.2)

    # 3. Parse confidence = how clearly the text signals a name+value structure
    #    Simple heuristic: confident if we have both a value and a name candidate
    confidence = 0.82

    if confidence < threshold:
        return ParseResult(
            metric_name=name_candidate,
            value=value,
            confidence=confidence,
            outcome="unrecognized",
        )

    # 4. Match against existing metrics (independent of parse confidence)
    if known_metrics:
        # Collect all candidates with their scores for disambiguation
        all_results = fuzz_process.extract(
            name_candidate, known_metrics, scorer=fuzz.token_sort_ratio, limit=5
        )
        if all_results:
            best_name, best_score, _ = all_results[0]
            if best_score >= _SAME_METRIC_SIMILARITY:
                # Confident match to an existing metric
                return ParseResult(
                    metric_name=best_name,
                    value=value,
                    confidence=confidence,
                    outcome="auto-parse",
                )
            # Partial match — collect candidates above ambiguity floor for disambiguation
            candidates = [name for name, score, _ in all_results if score >= _AMBIGUOUS_FLOOR]
            if candidates:
                return ParseResult(
                    metric_name=name_candidate,
                    value=value,
                    confidence=confidence,
                    outcome="ambiguous",
                    candidate_metrics=candidates,
                )
        # No match good enough → new metric name (auto-create flow)
    # No existing metrics OR no match → auto-create flow
    return ParseResult(
        metric_name=name_candidate,
        value=value,
        confidence=confidence,
        outcome="auto-parse",
    )
