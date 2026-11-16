from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget
from backend.app.ai.model_router import ModelRouter
from backend.app.answers.generator import AnswerGenerator
from backend.app.answers.memory_manager import Evidence, MemoryManager
from backend.app.answers.schemas import (
    AnswerFormat,
    AnswerProposal,
    AnswerProposeRequest,
    SupportStatus,
)
from backend.app.questions.schemas import QuestionAnalysis, QuestionAnalyzeRequest
from backend.app.questions.service import QuestionAnalyzer
from backend.app.validation.consistency_checker import find_fact_contradictions, normalize_fact_value
from backend.app.validation.sensitivity_checker import is_sensitive_question


ANSWER_FORMAT_BY_QUESTION = {
    "single_choice": AnswerFormat.SINGLE_CHOICE,
    "multiple_choice": AnswerFormat.MULTIPLE_CHOICE,
    "number": AnswerFormat.NUMBER,
    "numeric_scale": AnswerFormat.NUMBER,
    "date": AnswerFormat.DATE,
    "yes_no": AnswerFormat.BOOLEAN,
}


class AnswerService:
    def __init__(self, model_router: ModelRouter, memory_manager: MemoryManager):
        self.model_router = model_router
        self.memory_manager = memory_manager
        self.question_analyzer = QuestionAnalyzer(model_router)
        self.answer_generator = AnswerGenerator(model_router)
        self.call_budget = ModelCallBudget(model_router.settings.max_calls_per_question)

    def analyze(
        self,
        db: Session,
        profile_id: str | None,
        question: QuestionAnalyzeRequest,
        call_budget: ModelCallBudget | None = None,
    ) -> QuestionAnalysis:
        return self.question_analyzer.analyze(db, profile_id, question, call_budget)

    def propose(self, db: Session, request: AnswerProposeRequest) -> AnswerProposal:
        analysis = self.analyze(
            db,
            request.profile_id,
            QuestionAnalyzeRequest(
                question_text=request.question_text,
                options=request.options,
                required=request.required,
                max_length=request.max_length,
            ),
            self.call_budget,
        )
        empty = dict(
            suggested_answer="",
            confidence=0.0,
            sources=[],
            needs_user_input=True,
            needs_review=True,
            answer_format=ANSWER_FORMAT_BY_QUESTION.get(analysis.question_type.value, AnswerFormat.TEXT),
            question_analysis=analysis,
        )
        if is_sensitive_question(analysis.question_text):
            return AnswerProposal(
                **empty,
                support_status=SupportStatus.SENSITIVE,
                review_reason="Sensitive personal information requires direct user review",
            )

        evidence = self.memory_manager.retrieve(
            db,
            request.profile_id,
            analysis.question_text,
            call_budget=self.call_budget,
        )
        facts = [
            {"field_name": item.label, "value": item.content.partition(": ")[2]}
            for item in evidence
            if item.source_type == "profile_fact" and ": " in item.content
        ]
        question_value = normalize_fact_value(analysis.question_text)
        relevant_facts = [
            fact for fact in facts if normalize_fact_value(fact["field_name"]) in question_value
        ]
        conflicts = set(find_fact_contradictions(relevant_facts))
        if conflicts:
            conflicting_evidence = [
                item
                for item in evidence
                if item.source_type == "profile_fact" and item.label in conflicts
            ]
            return AnswerProposal(
                **{
                    **empty,
                    "sources": [
                        {
                            "source_type": item.source_type,
                            "source_id": item.source_id,
                            "excerpt": item.content,
                        }
                        for item in conflicting_evidence
                    ],
                },
                support_status=SupportStatus.CONTRADICTORY,
                review_reason="Conflicting verified profile facts require user resolution",
            )

        if not evidence:
            return AnswerProposal(
                **empty,
                support_status=SupportStatus.INSUFFICIENT,
                review_reason="No verified profile facts or indexed document evidence was found",
            )

        max_context_chars = self.model_router.settings.max_input_tokens_per_call * 3
        payload_evidence = []
        context_chars = len(analysis.question_text)
        for item in evidence:
            serialized_size = len(item.content) + len(item.label) + len(item.source_id) + 32
            if context_chars + serialized_size > max_context_chars:
                break
            payload_evidence.append(item.as_payload())
            context_chars += serialized_size
        if not payload_evidence:
            return AnswerProposal(
                **empty,
                support_status=SupportStatus.INSUFFICIENT,
                review_reason="Evidence exceeded the configured context limit",
            )
        if self.call_budget.exhausted:
            return AnswerProposal(
                **empty,
                support_status=SupportStatus.INSUFFICIENT,
                review_reason="The configured model-call limit leaves no call for answer generation",
            )
        return self.answer_generator.generate(
            db,
            request.profile_id,
            analysis,
            payload_evidence,
            self.call_budget,
        )
