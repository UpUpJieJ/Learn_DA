from fastapi import status

from app.core.exceptions.base_exceptions import ValidationException


def validate_playground_code(code: str) -> str:
    cleaned_code = code.strip()
    if not cleaned_code:
        raise ValidationException(
            message="code cannot be empty",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return cleaned_code
