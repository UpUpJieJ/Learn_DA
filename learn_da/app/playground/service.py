import json
import logging
from typing import Any

from app.practice.repository import PracticeRepository
from app.practice.service import PracticeService
from app.practice.validator import verify
from app.sandbox import SandboxService

from .schemas import (
    DataFrameResult,
    ExecuteCodeRequest,
    ExecuteCodeResponse,
    ExerciseVerification,
    FormatCodeRequest,
    FormatCodeResponse,
)
from .validators import validate_playground_code

log = logging.getLogger(__name__)

DATAFRAME_MARKER = "__LEARN_DA_DATAFRAME__"
DATAFRAME_PREVIEW_LIMIT = 50


class PlaygroundService:
    def __init__(
        self,
        sandbox_service: SandboxService,
        practice_service: PracticeService | None = None,
    ):
        self.sandbox_service = sandbox_service
        self.practice_service = practice_service

    async def execute(
        self, payload: ExecuteCodeRequest, *, visitor_id: str | None = None
    ) -> ExecuteCodeResponse:
        code = validate_playground_code(payload.code)
        result = await self.sandbox_service.execute(
            self._with_dataframe_probe(code),
            request_id=payload.request_id,
            source=payload.source,
        )
        cleaned_stdout, dataframe = self._extract_dataframe_result(result.stdout)
        result_type = self._resolve_result_type(result.status, dataframe)

        response = ExecuteCodeResponse(
            request_id=payload.request_id,
            execution_id=result.execution_id,
            source=payload.source,
            status=result.status,
            stdout=cleaned_stdout,
            stderr=result.stderr,
            error_type=result.error_type,
            duration_ms=result.duration_ms,
            output_truncated=result.output_truncated,
            result_type=result_type,
            dataframe=dataframe,
        )

        # Phase 2: 练习执行编排
        if (
            self.practice_service is not None
            and payload.lesson_slug
            and payload.exercise_id
            and visitor_id
        ):
            response = await self._orchestrate_exercise(
                payload=payload,
                response=response,
                cleaned_stdout=cleaned_stdout,
                dataframe=dataframe,
                visitor_id=visitor_id,
            )

        return response

    async def _orchestrate_exercise(
        self,
        *,
        payload: ExecuteCodeRequest,
        response: ExecuteCodeResponse,
        cleaned_stdout: str,
        dataframe: DataFrameResult | None,
        visitor_id: str,
    ) -> ExecuteCodeResponse:
        """编排练习执行：创建 Attempt → 判定 → 返回结果"""
        exercise_def = self.practice_service.get_exercise_definition(
            payload.lesson_slug, payload.exercise_id
        )
        if exercise_def is None:
            return response

        # 创建或重放 Attempt
        attempt, created = await self.practice_service.create_or_replay_attempt(
            visitor_id=visitor_id,
            request_id=str(payload.request_id),
            lesson_slug=payload.lesson_slug,
            exercise_id=payload.exercise_id,
            execution_id=str(response.execution_id),
            source=payload.source,
            language=payload.language,
            code=payload.code,
            execution_status=response.status,
            stdout=cleaned_stdout,
            stderr=response.stderr,
            duration_ms=response.duration_ms,
        )

        # 仅对新创建的 Attempt 进行判定
        if created:
            validator_def = exercise_def["validator"]
            result = verify(
                validator_type=validator_def["type"],
                expected=validator_def.get("expected"),
                stdout=cleaned_stdout,
                stderr=response.stderr,
                execution_status=response.status,
                dataframe=(dataframe.model_dump() if dataframe else None),
            )
            attempt.verification_status = result.status
            attempt.failure_reason = result.failure_reason

            response.attempt_id = attempt.id
            response.verification = ExerciseVerification(
                status=result.status,
                failure_reason=result.failure_reason,
                validator_type=result.validator_type,
            )
        else:
            # 重放：返回已有验证状态
            response.attempt_id = attempt.id
            response.verification = ExerciseVerification(
                status=attempt.verification_status,
                failure_reason=attempt.failure_reason,
                validator_type=(
                    exercise_def["validator"]["type"] if exercise_def else None
                ),
            )

        return response

    def format_code(self, payload: FormatCodeRequest) -> FormatCodeResponse:
        try:
            import black

            mode = black.FileMode()
            formatted = black.format_str(payload.code, mode=mode)
            return FormatCodeResponse(
                formatted=formatted,
                changed=formatted != payload.code,
            )
        except ImportError:
            return FormatCodeResponse(formatted=payload.code, changed=False)
        except Exception:
            return FormatCodeResponse(formatted=payload.code, changed=False)

    def _resolve_result_type(
        self,
        status: str,
        dataframe: DataFrameResult | None,
    ) -> str:
        if dataframe is not None:
            return "dataframe"
        if status in {"error", "timeout"}:
            return "error"
        return "text"

    def _extract_dataframe_result(
        self,
        stdout: str,
    ) -> tuple[str, DataFrameResult | None]:
        dataframe: DataFrameResult | None = None
        cleaned_lines: list[str] = []

        for line in stdout.splitlines(keepends=True):
            if line.startswith(DATAFRAME_MARKER):
                payload = line[len(DATAFRAME_MARKER) :].strip()
                try:
                    dataframe = DataFrameResult.model_validate(json.loads(payload))
                except (json.JSONDecodeError, ValueError, TypeError):
                    cleaned_lines.append(line)
                continue
            cleaned_lines.append(line)

        return "".join(cleaned_lines), dataframe

    def _with_dataframe_probe(self, code: str) -> str:
        return (
            f"{code}\n\n"
            "# --- Learn DA structured output probe ---\n"
            "try:\n"
            "    import json as __learn_da_json\n"
            "    __learn_da_candidates = ('result', 'df')\n"
            "    __learn_da_obj = None\n"
            "    for __learn_da_name in __learn_da_candidates:\n"
            "        if __learn_da_name in globals():\n"
            "            __learn_da_obj = globals()[__learn_da_name]\n"
            "            break\n"
            "    if __learn_da_obj is not None:\n"
            "        if hasattr(__learn_da_obj, 'collect') and callable(__learn_da_obj.collect):\n"
            "            __learn_da_obj = __learn_da_obj.collect()\n"
            "        if hasattr(__learn_da_obj, 'df') and callable(__learn_da_obj.df):\n"
            "            __learn_da_obj = __learn_da_obj.df()\n"
            "        __learn_da_payload = None\n"
            "        if hasattr(__learn_da_obj, 'to_dicts') and hasattr(__learn_da_obj, 'columns'):\n"
            f"            __learn_da_preview = __learn_da_obj.head({DATAFRAME_PREVIEW_LIMIT})\n"
            "            __learn_da_rows = __learn_da_preview.to_dicts()\n"
            "            __learn_da_payload = {\n"
            "                'columns': [str(__c) for __c in __learn_da_obj.columns],\n"
            "                'rows': __learn_da_rows,\n"
            "                'rowCount': int(getattr(__learn_da_obj, 'height', len(__learn_da_rows))),\n"
            f"                'truncated': int(getattr(__learn_da_obj, 'height', len(__learn_da_rows))) > {DATAFRAME_PREVIEW_LIMIT},\n"
            "            }\n"
            "        elif hasattr(__learn_da_obj, 'to_dict') and hasattr(__learn_da_obj, 'columns'):\n"
            f"            __learn_da_preview = __learn_da_obj.head({DATAFRAME_PREVIEW_LIMIT})\n"
            "            __learn_da_rows = __learn_da_preview.to_dict(orient='records')\n"
            "            __learn_da_payload = {\n"
            "                'columns': [str(__c) for __c in __learn_da_obj.columns],\n"
            "                'rows': __learn_da_rows,\n"
            "                'rowCount': int(len(__learn_da_obj)),\n"
            f"                'truncated': int(len(__learn_da_obj)) > {DATAFRAME_PREVIEW_LIMIT},\n"
            "            }\n"
            "        if __learn_da_payload is not None:\n"
            f"            print('{DATAFRAME_MARKER}' + __learn_da_json.dumps(__learn_da_payload, ensure_ascii=False, default=str))\n"
            "except Exception:\n"
            "    pass\n"
        )
