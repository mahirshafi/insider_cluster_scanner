from __future__ import annotations

from dataclasses import field
from datetime import date
from typing import Any

try:
    from pydantic import BaseModel as _PydanticBaseModel, Field as _PydanticField
except ModuleNotFoundError:
    _PydanticBaseModel = None

    def _PydanticField(default: Any = None, default_factory: Any = None, **_: Any) -> Any:
        if default_factory is not None:
            return field(default_factory=default_factory)
        return default


if _PydanticBaseModel is not None:
    BaseModel = _PydanticBaseModel
    Field = _PydanticField
else:
    class BaseModel:
        def __init__(self, **kwargs: Any) -> None:
            annotations = getattr(self, "__annotations__", {})
            for name in annotations:
                class_value = getattr(type(self), name, None)
                if hasattr(class_value, "default_factory"):
                    value = class_value.default_factory()
                else:
                    value = class_value
                setattr(self, name, kwargs.pop(name, value))
            for name, value in kwargs.items():
                setattr(self, name, value)

        def model_dump(self) -> dict[str, Any]:
            return dict(self.__dict__)

    Field = _PydanticField


class InsiderTransaction(BaseModel):
    ticker: str
    company_name: str = ""
    insider_name: str
    insider_title: str = ""
    transaction_date: date
    filing_date: date | None = None
    trade_type: str
    shares: float = 0
    price: float = 0
    value: float = 0
    accession_number: str | None = None


class ScanFilters(BaseModel):
    max_filing_delay_days: int = Field(default=14, ge=0, le=365)
    lookback_days: int = Field(default=730, ge=60, le=1095)
    tickers: list[str] | None = None


class PeerMultiple(BaseModel):
    ticker: str
    pe_forward: float | None = None
    pb: float | None = None
    ps: float | None = None


class ValuationSnapshot(BaseModel):
    current_price: float | None = None
    avg_target: float | None = None
    high_target: float | None = None
    low_target: float | None = None
    pe_forward: float | None = None
    pb: float | None = None
    ps: float | None = None
    market_cap: int | None = None
    peers: list[PeerMultiple] = Field(default_factory=list)


class ScanResult(BaseModel):
    ticker: str
    company_name: str
    cluster_tier: int
    signal: str
    cluster_size: int
    total_cluster_value: float
    average_purchase_value: float
    cluster_window_days: int
    has_csuite_buyer: bool
    has_senior_officer: bool
    inactivity_months: int | None = None
    inactivity_flag: bool = False
    rationale: list[str]
    insiders: list[InsiderTransaction]


JsonDict = dict[str, Any]
