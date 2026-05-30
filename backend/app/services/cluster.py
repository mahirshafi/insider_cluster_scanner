from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from backend.app.models import InsiderTransaction

C_SUITE_KEYWORDS = (
    "CEO",
    "CFO",
    "COO",
    "CTO",
    "CIO",
    "CLO",
    "CMO",
    "CHIEF",
    "PRESIDENT",
)
SENIOR_OFFICER_KEYWORDS = C_SUITE_KEYWORDS + (
    "OFFICER",
    "VP",
    "VICE PRESIDENT",
    "TREASURER",
    "SECRETARY",
    "CHAIR",
)


@dataclass(frozen=True)
class ClusterDetection:
    ticker: str
    company_name: str
    tier: int
    signal: str
    transactions: list[InsiderTransaction]
    window_days: int
    total_value: float
    average_value: float
    has_csuite_buyer: bool
    has_senior_officer: bool
    inactivity_months: int | None
    inactivity_flag: bool
    rationale: list[str]


def detect_clusters(
    transactions: list[InsiderTransaction],
    min_recent_filing_date: date | None = None,
    inactivity_days: int = 183,
) -> dict[str, ClusterDetection]:
    purchases = [tx for tx in transactions if tx.trade_type == "P" and tx.value > 0]
    clusters: dict[str, ClusterDetection] = {}
    for ticker in sorted({tx.ticker for tx in purchases}):
        group = sorted((tx for tx in purchases if tx.ticker == ticker), key=lambda tx: tx.transaction_date)
        best = _best_ticker_cluster(group, min_recent_filing_date, inactivity_days)
        if best is not None:
            clusters[ticker] = best
    return clusters


def _best_ticker_cluster(
    group: list[InsiderTransaction],
    min_recent_filing_date: date | None,
    inactivity_days: int,
) -> ClusterDetection | None:
    matches: list[ClusterDetection] = []
    for window_days in (14, 30, 60):
        for start in group:
            end_date = start.transaction_date + timedelta(days=window_days)
            candidate = [tx for tx in group if start.transaction_date <= tx.transaction_date <= end_date]
            if min_recent_filing_date and not _has_recent_filing(candidate, min_recent_filing_date):
                continue
            detection = _classify_candidate(group, candidate, window_days, inactivity_days)
            if detection is not None:
                matches.append(detection)
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda item: (item.tier, item.inactivity_flag is False, -item.total_value, item.window_days),
    )[0]


def _classify_candidate(
    group: list[InsiderTransaction],
    candidate: list[InsiderTransaction],
    window_days: int,
    inactivity_days: int,
) -> ClusterDetection | None:
    distinct_insiders = {tx.insider_name for tx in candidate if tx.insider_name}
    if len(distinct_insiders) < 3:
        return None

    total_value = sum(tx.value for tx in candidate)
    average_value = total_value / len(candidate)
    has_csuite_buyer = any(_is_csuite(tx.insider_title) for tx in candidate)
    has_senior_officer = any(_is_senior_officer(tx.insider_title) for tx in candidate)

    tier = 0
    signal = ""
    rationale: list[str] = []
    if window_days <= 14 and average_value >= 200_000 and has_csuite_buyer:
        tier = 1
        signal = "Strong Cluster"
        rationale.append("3+ insiders bought within 14 days")
        rationale.append("Average purchase value is at least $200k")
        rationale.append("At least one C-suite buyer is present")
    elif window_days <= 30 and average_value >= 100_000 and has_senior_officer:
        tier = 2
        signal = "Moderate Cluster"
        rationale.append("3+ insiders bought within 30 days")
        rationale.append("Average purchase value is at least $100k")
        rationale.append("At least one senior officer is present")
    elif window_days <= 60 and total_value > 200_000:
        tier = 3
        signal = "Weak Cluster"
        rationale.append("3+ insiders bought within 60 days")
        rationale.append("Total cluster value is above $200k")
    else:
        return None

    cluster_start = min(tx.transaction_date for tx in candidate)
    inactivity_months, inactivity_flag = _inactivity(group, cluster_start, inactivity_days)
    if inactivity_flag and inactivity_months is None:
        rationale.append("No earlier open-market purchases found in the lookback period")
    elif inactivity_flag:
        rationale.append(f"Cluster follows roughly {inactivity_months} months without open-market purchases")

    return ClusterDetection(
        ticker=candidate[0].ticker,
        company_name=candidate[0].company_name,
        tier=tier,
        signal=signal,
        transactions=candidate,
        window_days=window_days,
        total_value=total_value,
        average_value=average_value,
        has_csuite_buyer=has_csuite_buyer,
        has_senior_officer=has_senior_officer,
        inactivity_months=inactivity_months,
        inactivity_flag=inactivity_flag,
        rationale=rationale,
    )


def _has_recent_filing(candidate: list[InsiderTransaction], min_recent_filing_date: date) -> bool:
    return any(tx.filing_date is None or tx.filing_date >= min_recent_filing_date for tx in candidate)


def _inactivity(
    group: list[InsiderTransaction],
    cluster_start: date,
    inactivity_days: int,
) -> tuple[int | None, bool]:
    prior_dates = [tx.transaction_date for tx in group if tx.transaction_date < cluster_start]
    if not prior_dates:
        return None, True
    days_since_prior = (cluster_start - max(prior_dates)).days
    return days_since_prior // 30, days_since_prior >= inactivity_days


def _is_csuite(title: str) -> bool:
    title_upper = title.upper()
    return any(keyword in title_upper for keyword in C_SUITE_KEYWORDS)


def _is_senior_officer(title: str) -> bool:
    title_upper = title.upper()
    return any(keyword in title_upper for keyword in SENIOR_OFFICER_KEYWORDS)
