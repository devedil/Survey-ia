import re


def split_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    words = []
    for word in re.findall(r"\S+", text):
        if len(word) > chunk_size:
            words.extend(word[index : index + chunk_size] for index in range(0, len(word), chunk_size))
        else:
            words.append(word)
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        length = 0
        while end < len(words):
            next_length = len(words[end]) + (1 if end > start else 0)
            if length + next_length > chunk_size and end > start:
                break
            length += next_length
            end += 1

        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break

        next_start = end
        retained = 0
        while next_start > start and retained + len(words[next_start - 1]) + (1 if retained else 0) <= overlap:
            next_start -= 1
            retained += len(words[next_start]) + (1 if retained else 0)
        start = next_start if next_start > start else end
    return chunks
