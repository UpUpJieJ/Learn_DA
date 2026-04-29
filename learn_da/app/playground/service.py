import json

from app.sandbox import SandboxService

from .schemas import (
    DataFrameResult,
    ExecuteCodeRequest,
    ExecuteCodeResponse,
    FormatCodeRequest,
    FormatCodeResponse,
)
from .validators import validate_playground_code


DATAFRAME_MARKER = "__LEARN_DA_DATAFRAME__"
DATAFRAME_PREVIEW_LIMIT = 50


class PlaygroundService:
    def __init__(self, sandbox_service: SandboxService | None = None):
        self.sandbox_service = sandbox_service or SandboxService()

    def execute(self, payload: ExecuteCodeRequest) -> ExecuteCodeResponse:
        code = validate_playground_code(payload.code)
        result = self.sandbox_service.execute(self._with_dataframe_probe(code))
        cleaned_stdout, dataframe = self._extract_dataframe_result(result.stdout)
        result_type = self._resolve_result_type(result.status, dataframe)
        return ExecuteCodeResponse(
            status=result.status,
            stdout=cleaned_stdout,
            stderr=result.stderr,
            execution_time=result.execution_time,
            used_sandbox=result.used_sandbox,
            result_type=result_type,
            dataframe=dataframe,
        )

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
