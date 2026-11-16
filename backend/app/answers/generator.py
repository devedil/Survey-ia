from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget
from backend.app.ai.model_router import ModelRouter
from backend.app.answers.prompts import ANSWER_GENERATOR_PROMPT_VERSION, ANSWER_GENERATOR_SYSTEM_PROMPT
from backend.app.answers.schemas import AnswerProposal, AnswerSource, SupportStatus
from backend.app.questions.schemas import QuestionAnalysis
from backend.app.validation.format_validator import validate_answer_format


class AnswerGenerator:
    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router

    def generate(
        self,
        db: Session,
        profile_id: str,
        analysis: QuestionAnalysis,
        evidence: list[dict[str, str]],
        call_budget: ModelCallBudget | None = None,
    ) -> AnswerProposal:
        result = self.model_router.complete_json(
            db,
            profile_id=profile_id,
            operation=ANSWER_GENERATOR_PROMPT_VERSION,
            system_prompt=ANSWER_GENERATOR_SYSTEM_PROMPT,
            user_payload={
                "question": analysis.model_dump(mode="json"),
                "evidence": evidence,
            },
            call_budget=call_budget,
        )
        payload = dict(result.data)
        payload["question_analysis"] = analysis.model_dump(mode="json")
        proposal = AnswerProposal.model_validate(payload)

        evidence_by_id = {item["source_id"]: item for item in evidence}
        valid_sources: list[AnswerSource] = []
        for source in proposal.sources:
            item = evidence_by_id.get(source.source_id)
            if (
                item is not None
                and source.source_type == item["source_type"]
                and source.excerpt.strip()
                and source.excerpt.strip().casefold() in item["content"].casefold()
            ):
                valid_sources.append(source)

        if proposal.support_status == SupportStatus.SUPPORTED and not valid_sources:
            return proposal.model_copy(
                update={
                    "suggested_answer": "",
                    "support_status": SupportStatus.INSUFFICIENT,
                    "confidence": 0.0,
                    "sources": [],
                    "needs_user_input": True,
                    "needs_review": True,
                    "review_reason": "No verifiable source excerpt supports the proposed answer",
                }
            )

        proposal = proposal.model_copy(update={"sources": valid_sources})
        if proposal.support_status != SupportStatus.SUPPORTED:
            return proposal.model_copy(
                update={
                    "suggested_answer": "",
                    "sources": valid_sources if proposal.support_status == SupportStatus.CONTRADICTORY else [],
                    "needs_user_input": True,
                    "needs_review": True,
                }
            )

        valid_format, reason = validate_answer_format(
            proposal.suggested_answer,
            proposal.answer_format,
            analysis,
        )
        if not valid_format:
            return proposal.model_copy(
                update={
                    "suggested_answer": "",
                    "support_status": SupportStatus.INSUFFICIENT,
                    "confidence": 0.0,
                    "sources": [],
                    "needs_user_input": True,
                    "needs_review": True,
                    "review_reason": reason,
                }
            )
        return proposal.model_copy(
            update={
                "needs_review": True,
                "review_reason": proposal.review_reason or "Review the evidence-backed suggestion before use",
            }
        )
