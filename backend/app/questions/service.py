from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget
from backend.app.ai.model_router import ModelRouter
from backend.app.questions.prompts import QUESTION_ANALYZER_PROMPT_VERSION, QUESTION_ANALYZER_SYSTEM_PROMPT
from backend.app.questions.schemas import QuestionAnalysis, QuestionAnalyzeRequest, QuestionType
from backend.app.validation.sensitivity_checker import is_sensitive_question


class QuestionAnalyzer:
    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router

    def analyze(
        self,
        db: Session,
        profile_id: str | None,
        question: QuestionAnalyzeRequest,
        call_budget: ModelCallBudget | None = None,
    ) -> QuestionAnalysis:
        if is_sensitive_question(question.question_text):
            return QuestionAnalysis(
                question_text=question.question_text,
                instructions=[],
                question_type=QuestionType.UNKNOWN,
                options=question.options,
                required=question.required,
                max_length=question.max_length,
                language="unknown",
                requests_personal_information=True,
                needs_additional_context=True,
            )
        result = self.model_router.complete_json(
            db,
            profile_id=profile_id,
            operation=QUESTION_ANALYZER_PROMPT_VERSION,
            system_prompt=QUESTION_ANALYZER_SYSTEM_PROMPT,
            user_payload=question.model_dump(),
            call_budget=call_budget,
        )
        payload = dict(result.data)
        payload.update(
            question_text=question.question_text,
            options=question.options,
            required=question.required,
            max_length=question.max_length,
        )
        return QuestionAnalysis.model_validate(payload)
