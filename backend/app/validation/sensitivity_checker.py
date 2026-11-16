import re


SENSITIVE_TERMS = re.compile(
    r"\b(health|medical|diagnos|medication|religion|politic|ethnic|race|"
    r"sexual|orientation|disability|income|salary|financial|criminal|"
    r"immigration|pregnan|mental health|salud|m[eé]dic|diagn[oó]stic|"
    r"medicaci[oó]n|religi[oó]n|pol[ií]tic|etnia|raza|sexualidad|"
    r"discapacidad|ingreso|salario|financier|antecedentes penales|"
    r"inmigraci[oó]n|embarazo)\w*\b",
    re.IGNORECASE,
)


def is_sensitive_question(question: str) -> bool:
    return SENSITIVE_TERMS.search(question) is not None
