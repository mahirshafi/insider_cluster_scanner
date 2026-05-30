from __future__ import annotations

from datetime import date, timedelta

from backend.app.config import get_settings
from backend.app.models import ScanFilters, ScanResult
from backend.app.services.cluster import detect_clusters
from backend.app.services.sec_fetcher import fetch_form4_transactions


def run_scan(filters: ScanFilters) -> list[ScanResult]:
    settings = get_settings()
    tickers = _scan_universe(filters, settings.scan_tickers)
    transactions = fetch_form4_transactions(tickers=tickers, lookback_days=filters.lookback_days)
    min_recent_filing_date = date.today() - timedelta(days=filters.max_filing_delay_days)
    clusters = detect_clusters(transactions, min_recent_filing_date=min_recent_filing_date)

    results: list[ScanResult] = []
    for ticker, cluster in clusters.items():
        results.append(
            ScanResult(
                ticker=ticker,
                company_name=cluster.company_name,
                cluster_tier=cluster.tier,
                signal=cluster.signal,
                cluster_size=len({tx.insider_name for tx in cluster.transactions}),
                total_cluster_value=cluster.total_value,
                average_purchase_value=cluster.average_value,
                cluster_window_days=cluster.window_days,
                has_csuite_buyer=cluster.has_csuite_buyer,
                has_senior_officer=cluster.has_senior_officer,
                inactivity_months=cluster.inactivity_months,
                inactivity_flag=cluster.inactivity_flag,
                rationale=cluster.rationale,
                insiders=sorted(cluster.transactions, key=lambda tx: tx.transaction_date, reverse=True),
            )
        )
    return sorted(
        results,
        key=lambda item: (item.cluster_tier, item.inactivity_flag is False, -item.total_cluster_value),
    )


def _scan_universe(filters: ScanFilters, default_tickers: list[str]) -> list[str]:
    if filters.tickers:
        return sorted({_normalize_ticker(ticker) for ticker in filters.tickers if _normalize_ticker(ticker)})
    return default_tickers


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if ":" in normalized:
        normalized = normalized.rsplit(":", 1)[-1]
    return normalized.replace(".", "-")
