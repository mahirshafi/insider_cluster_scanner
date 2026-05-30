from datetime import date, timedelta

from backend.app.models import InsiderTransaction, ScanFilters
from backend.app.scanner import _scan_universe
from backend.app.services.cluster import detect_clusters
from backend.app.services.sec_fetcher import _candidate_primary_docs


def tx(name: str, day_offset: int, value: float, title: str = "Director") -> InsiderTransaction:
    day = date(2026, 5, 1) + timedelta(days=day_offset)
    return InsiderTransaction(
        ticker="TEST",
        company_name="Test Corp",
        insider_name=name,
        insider_title=title,
        transaction_date=day,
        filing_date=day,
        trade_type="P",
        shares=value / 10,
        price=10,
        value=value,
    )


def test_detects_strong_cluster():
    clusters = detect_clusters([
        tx("Alice", 0, 250_000, "CEO"),
        tx("Bob", 1, 200_000, "Director"),
        tx("Carol", 2, 210_000, "CFO"),
    ])

    assert clusters["TEST"].signal == "Strong Cluster"
    assert clusters["TEST"].tier == 1
    assert clusters["TEST"].has_csuite_buyer is True


def test_detects_moderate_cluster_when_strong_rules_do_not_match():
    clusters = detect_clusters([
        tx("Alice", 0, 110_000, "Chief Accounting Officer"),
        tx("Bob", 16, 100_000, "Director"),
        tx("Carol", 20, 120_000, "Director"),
    ])

    assert clusters["TEST"].signal == "Moderate Cluster"
    assert clusters["TEST"].tier == 2


def test_detects_weak_watchlist_cluster():
    clusters = detect_clusters([
        tx("Alice", 0, 50_000, "Director"),
        tx("Bob", 35, 75_000, "Director"),
        tx("Carol", 45, 90_000, "Director"),
    ])

    assert clusters["TEST"].signal == "Weak Cluster"
    assert clusters["TEST"].tier == 3


def test_flags_six_month_inactivity_before_cluster():
    clusters = detect_clusters([
        tx("Older Buyer", -220, 100_000, "Director"),
        tx("Alice", 0, 250_000, "CEO"),
        tx("Bob", 1, 200_000, "Director"),
        tx("Carol", 2, 210_000, "CFO"),
    ])

    assert clusters["TEST"].inactivity_flag is True
    assert clusters["TEST"].inactivity_months == 7


def test_requires_recent_filing_inside_cluster():
    clusters = detect_clusters(
        [
            tx("Alice", 0, 250_000, "CEO"),
            tx("Bob", 1, 200_000, "Director"),
            tx("Carol", 2, 210_000, "CFO"),
        ],
        min_recent_filing_date=date(2026, 6, 1),
    )

    assert clusters == {}


def test_sec_xsl_primary_doc_falls_back_to_raw_xml():
    assert _candidate_primary_docs("xslF345X06/form4.xml") == ["xslF345X06/form4.xml", "form4.xml"]


def test_exchange_prefixed_tickers_are_normalized():
    assert _scan_universe(
        ScanFilters(tickers=["NASDAQ:ALRM", "NASDAQ:CBNK", ""]),
        default_tickers=["DEFAULT"],
    ) == ["ALRM", "CBNK"]
