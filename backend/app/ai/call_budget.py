class ModelCallLimitError(RuntimeError):
    pass


class ModelCallBudget:
    def __init__(self, maximum_calls: int):
        self.maximum_calls = maximum_calls
        self.calls_used = 0

    @property
    def exhausted(self) -> bool:
        return self.calls_used >= self.maximum_calls

    def consume(self) -> None:
        if self.exhausted:
            raise ModelCallLimitError("Maximum model calls per question reached")
        self.calls_used += 1
