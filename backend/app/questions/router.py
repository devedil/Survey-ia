from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget, ModelCallLimitError
from backend.app.ai.dependencies import get_model_router
from backend.app.ai.model_router import ModelConfigurationError, ModelProviderError, ModelRouter
from backend.app.core.database import get_db
from backend.app.profiles.repository import get_profile
from backend.app.questions.schemas import QuestionAnalysis, QuestionAnalyzeRequest
from backend.app.questions.service import QuestionAnalyzer

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("/analyze", response_model=QuestionAnalysis)
def analyze(
    payload: QuestionAnalyzeRequest,
    profile_id: str | None = None,
    db: Session = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
) -> QuestionAnalysis:
    if profile_id is not None and get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        return QuestionAnalyzer(model_router).analyze(
            db,
            profile_id,
            payload,
            ModelCallBudget(model_router.settings.max_calls_per_question),
        )
    except ModelCallLimitError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
    except ModelConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ModelProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model returned an invalid question analysis") from error
