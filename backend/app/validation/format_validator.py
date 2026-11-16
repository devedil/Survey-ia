from datetime import date

from backend.app.answers.schemas import AnswerFormat
from backend.app.questions.schemas import QuestionAnalysis, QuestionType


ANSWER_FORMAT_BY_QUESTION = {
    QuestionType.SINGLE_CHOICE: AnswerFormat.SINGLE_CHOICE,
    QuestionType.MULTIPLE_CHOICE: AnswerFormat.MULTIPLE_CHOICE,
    QuestionType.NUMBER: AnswerFormat.NUMBER,
    QuestionType.NUMERIC_SCALE: AnswerFormat.NUMBER,
    QuestionType.DATE: AnswerFormat.DATE,
    QuestionType.YES_NO: AnswerFormat.BOOLEAN,
}


def validate_answer_format(
    answer: str,
    answer_format: AnswerFormat,
    analysis: QuestionAnalysis,
) -> tuple[bool, str | None]:
    normalized = answer.strip()
    expected_format = ANSWER_FORMAT_BY_QUESTION.get(analysis.question_type, AnswerFormat.TEXT)
    if answer_format != expected_format:
        return False, "Answer format does not match the question type"
    if analysis.max_length is not None and len(answer) > analysis.max_length:
        return False, f"Answer exceeds the {analysis.max_length}-character limit"

    if analysis.question_type in {QuestionType.SINGLE_CHOICE, QuestionType.YES_NO}:
        options = analysis.options or (["yes", "no"] if analysis.question_type == QuestionType.YES_NO else [])
        if options and normalized.casefold() not in {option.casefold() for option in options}:
            return False, "Answer is not one of the available options"

    if analysis.question_type == QuestionType.MULTIPLE_CHOICE and analysis.options:
        selected = {value.strip().casefold() for value in normalized.split(",") if value.strip()}
        allowed = {option.casefold() for option in analysis.options}
        if not selected or not selected.issubset(allowed):
            return False, "Answer contains options that are not available"

    if analysis.question_type == QuestionType.NUMBER:
        try:
            float(normalized)
        except ValueError:
            return False, "Answer must be a number"

    if analysis.question_type == QuestionType.NUMERIC_SCALE:
        try:
            value = float(normalized)
        except ValueError:
            return False, "Answer must be a number"
        numeric_options = []
        for option in analysis.options:
            try:
                numeric_options.append(float(option))
            except ValueError:
                continue
        if len(numeric_options) >= 2 and not min(numeric_options) <= value <= max(numeric_options):
            return False, "Answer is outside the available numeric scale"

    if analysis.question_type == QuestionType.DATE:
        try:
            date.fromisoformat(normalized)
        except ValueError:
            return False, "Answer must use the ISO date format YYYY-MM-DD"

    if analysis.question_type == QuestionType.YES_NO:
        allowed = {option.casefold() for option in analysis.options} or {"yes", "no", "true", "false"}
        if normalized.casefold() not in allowed:
            return False, "Answer must be one of the valid yes/no values"

    return True, None
