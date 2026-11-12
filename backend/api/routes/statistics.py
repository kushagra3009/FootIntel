"""Statistical results & econometric robustness endpoints (Analyses 6 & 7)."""

from typing import Literal
from fastapi import APIRouter, Query

from api.schemas import ErrorResponse, StatisticalResultsResponse
from api.services.analytics_service import get_statistical_results

router = APIRouter(prefix="/api/v1/statistics", tags=["Statistical Results"])

SectionFilter = Literal["all", "6A", "6B", "6C", "6D", "6E", "6F", "07"]


@router.get(
    "",
    response_model=StatisticalResultsResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get validated correlation, regression, and robustness statistics",
    description=(
        "Return Pearson r, Spearman rho, OLS slopes, R², naive & Liang-Zeger club-clustered "
        "p-values/95% CIs, Season/Club/Two-Way Fixed Effects, Club-Averaged Cross-Section, "
        "sub-period stability checks, and Domestic-vs-UCL Steiger z-tests."
    ),
)
def statistical_results(
    section: SectionFilter = Query(
        default="all",
        description="Optional section filter: all, 6A, 6B, 6C, 6D, 6E, 6F, or 07.",
    ),
) -> StatisticalResultsResponse:
    return get_statistical_results(section=section)

