"""Safe division — pure-function implementation."""

from examples.safe_div.types import DivisionError, DivResult


class SafeDivService:
    def divide(self, dividend: int, divisor: int) -> DivResult:
        if divisor == 0:
            raise DivisionError
        quotient = dividend // divisor
        remainder = dividend % divisor
        return DivResult(quotient=quotient, remainder=remainder)
