from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import requests

from backend.app.config import get_settings
from backend.app.models import InsiderTransaction
from backend.app.services.cache import TTLCache
from backend.app.services.logging import log_api_call

SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"

_cache: TTLCache[list[InsiderTransaction]] | None = None
_ticker_cache: dict[str, int] | None = None


def _cache_instance() -> TTLCache[list[InsiderTransaction]]:
    global _cache
    if _cache is None:
        _cache = TTLCache(get_settings().cache_ttl_seconds)
    return _cache


def _headers() -> dict[str, str]:
    return {"User-Agent": get_settings().sec_user_agent, "Accept-Encoding": "gzip, deflate"}


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _float(element: ET.Element | None) -> float:
    try:
        return float(_text(element))
    except (TypeError, ValueError):
        return 0.0


def get_ticker_cik_map() -> dict[str, int]:
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache
    log_api_call("SEC", SEC_TICKERS)
    response = requests.get(SEC_TICKERS, headers=_headers(), timeout=20)
    response.raise_for_status()
    data = response.json()
    _ticker_cache = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    return _ticker_cache


def fetch_form4_transactions(tickers: list[str], lookback_days: int = 60) -> list[InsiderTransaction]:
    normalized = sorted({ticker.upper() for ticker in tickers})
    cache_key = f"form4:{','.join(normalized)}:{lookback_days}"
    cached = _cache_instance().get(cache_key)
    if cached is not None:
        return cached

    cik_map = get_ticker_cik_map()
    cutoff = date.today() - timedelta(days=lookback_days)
    transactions: list[InsiderTransaction] = []
    for ticker in normalized:
        cik = cik_map.get(ticker)
        if cik is None:
            continue
        transactions.extend(_fetch_ticker_form4(ticker, cik, cutoff))
    _cache_instance().set(cache_key, transactions)
    return transactions


def _fetch_ticker_form4(ticker: str, cik: int, cutoff: date) -> list[InsiderTransaction]:
    padded_cik = str(cik).zfill(10)
    submissions_url = f"{SEC_DATA}/submissions/CIK{padded_cik}.json"
    log_api_call("SEC", submissions_url)
    response = requests.get(submissions_url, headers=_headers(), timeout=20)
    response.raise_for_status()
    recent = response.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    transactions: list[InsiderTransaction] = []
    for form, accession, filing_date_text, primary_doc in zip(forms, accessions, filing_dates, primary_docs):
        if form != "4":
            continue
        filing_date = datetime.strptime(filing_date_text, "%Y-%m-%d").date()
        if filing_date < cutoff:
            break
        try:
            transactions.extend(_fetch_form4_xml(ticker, cik, accession, primary_doc, filing_date, cutoff))
        except (requests.RequestException, ET.ParseError, ValueError):
            continue
    return transactions


def _fetch_form4_xml(
    fallback_ticker: str,
    cik: int,
    accession: str,
    primary_doc: str,
    filing_date: date,
    cutoff: date,
) -> list[InsiderTransaction]:
    root = _fetch_form4_root(cik, accession, primary_doc)

    issuer = root.find("issuer")
    ticker = _text(issuer.find("issuerTradingSymbol") if issuer is not None else None) or fallback_ticker
    company_name = _text(issuer.find("issuerName") if issuer is not None else None)

    owner = root.find("reportingOwner")
    insider_name = _text(owner.find("reportingOwnerId/rptOwnerName") if owner is not None else None)
    relationship = owner.find("reportingOwnerRelationship") if owner is not None else None
    title = _relationship_title(relationship)

    parsed: list[InsiderTransaction] = []
    for transaction in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(transaction.find("transactionCoding/transactionCode"))
        acquired = _text(transaction.find("transactionAmounts/transactionAcquiredDisposedCode/value"))
        if code != "P" or acquired != "A":
            continue
        tx_date_text = _text(transaction.find("transactionDate/value"))
        tx_date = datetime.strptime(tx_date_text, "%Y-%m-%d").date()
        if tx_date < cutoff:
            continue
        shares = _float(transaction.find("transactionAmounts/transactionShares/value"))
        price = _float(transaction.find("transactionAmounts/transactionPricePerShare/value"))
        value = shares * price
        parsed.append(
            InsiderTransaction(
                ticker=ticker.upper(),
                company_name=company_name,
                insider_name=insider_name,
                insider_title=title,
                transaction_date=tx_date,
                filing_date=filing_date,
                trade_type=code,
                shares=shares,
                price=price,
                value=value,
                accession_number=accession,
            )
        )
    return parsed


def _fetch_form4_root(cik: int, accession: str, primary_doc: str) -> ET.Element:
    last_error: Exception | None = None
    for document in _candidate_primary_docs(primary_doc):
        accession_path = accession.replace("-", "")
        url = f"{SEC_ARCHIVES}/{cik}/{accession_path}/{document}"
        log_api_call("SEC", url)
        response = requests.get(url, headers=_headers(), timeout=20)
        try:
            response.raise_for_status()
            return ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise ValueError("No SEC Form 4 document candidates found")


def _candidate_primary_docs(primary_doc: str) -> list[str]:
    normalized = primary_doc.strip("/")
    candidates = [normalized]
    if "/" in normalized:
        candidates.append(normalized.rsplit("/", 1)[-1])
    return list(dict.fromkeys(candidates))


def _relationship_title(relationship: ET.Element | None) -> str:
    if relationship is None:
        return ""
    parts: list[str] = []
    if _text(relationship.find("isDirector")) == "1":
        parts.append("Director")
    if _text(relationship.find("isOfficer")) == "1":
        officer_title = _text(relationship.find("officerTitle"))
        parts.append(officer_title or "Officer")
    if _text(relationship.find("isTenPercentOwner")) == "1":
        parts.append("10% Owner")
    if _text(relationship.find("isOther")) == "1":
        parts.append(_text(relationship.find("otherText")) or "Other")
    return ", ".join(parts)
