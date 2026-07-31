"""
Phase 2: 可验证练习闭环 - Practice 模块
"""

from .models import ExerciseAttempt
from .repository import PracticeRepository
from .service import PracticeService
from .validator import verify, VerificationResult

__all__ = [
    "ExerciseAttempt",
    "PracticeRepository",
    "PracticeService",
    "verify",
    "VerificationResult",
]
