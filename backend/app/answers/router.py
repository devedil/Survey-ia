from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallLimitError
from backend.app.ai.dependencies import get_memory_manager, get_model_router
from backend.app.ai.model_router import ModelConfigurationError, ModelProviderError, ModelRouter
from backend.app.answers.memory_manager import MemoryManager
from backend.app.answers.schemas import AnswerProposal, AnswerProposeRequest
from backend.app.answers.service import AnswerService
from backend.app.core.database import get_db
from backend.app.documents.embedding_service import EmbeddingConfigurationError
from backend.app.profiles.repository import get_profile

router = APIRouter(prefix="/answers", tags=["answers"])


@router.post("/propose", response_model=AnswerProposal)
def propose(
    payload: AnswerProposeRequest,
    db: Session = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> AnswerProposal:
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        return AnswerService(model_router, memory_manager).propose(db, payload)
    except ModelConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except EmbeddingConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ModelProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except ModelCallLimitError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model returned an invalid answer proposal") from error
