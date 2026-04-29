from app.playground.schemas import ExecuteCodeRequest
from app.playground.service import PlaygroundService
from app.sandbox.schemas import SandboxExecutionResult


class CapturingSandbox:
    def __init__(self, result: SandboxExecutionResult):
        self.result = result
        self.executed_code = ""

    def execute(self, code: str) -> SandboxExecutionResult:
        self.executed_code = code
        return self.result


def test_execute_parses_dataframe_marker_and_cleans_stdout():
    sandbox = CapturingSandbox(
        SandboxExecutionResult(
            status="success",
            stdout=(
                "before\n"
                '__LEARN_DA_DATAFRAME__{"columns":["name","score"],'
                '"rows":[{"name":"Alice","score":95}],'
                '"rowCount":1,"truncated":false}\n'
                "after\n"
            ),
            stderr="",
            execution_time=12,
            used_sandbox="test",
        )
    )
    service = PlaygroundService(sandbox_service=sandbox)

    result = service.execute(ExecuteCodeRequest(code="df = make_df()"))

    assert result.result_type == "dataframe"
    assert result.dataframe is not None
    assert result.dataframe.columns == ["name", "score"]
    assert result.dataframe.rows == [{"name": "Alice", "score": 95}]
    assert result.dataframe.row_count == 1
    assert result.stdout == "before\nafter\n"


def test_execute_marks_error_results_as_error_type():
    sandbox = CapturingSandbox(
        SandboxExecutionResult(
            status="error",
            stdout="",
            stderr="NameError: name 'df' is not defined",
            execution_time=4,
            used_sandbox="test",
        )
    )
    service = PlaygroundService(sandbox_service=sandbox)

    result = service.execute(ExecuteCodeRequest(code="print(df)"))

    assert result.result_type == "error"
    assert result.dataframe is None


def test_execute_appends_dataframe_probe_to_user_code():
    sandbox = CapturingSandbox(
        SandboxExecutionResult(
            status="success",
            stdout="plain output\n",
            stderr="",
            execution_time=5,
            used_sandbox="test",
        )
    )
    service = PlaygroundService(sandbox_service=sandbox)

    service.execute(ExecuteCodeRequest(code="print('ok')"))

    assert "print('ok')" in sandbox.executed_code
    assert "__LEARN_DA_DATAFRAME__" in sandbox.executed_code
    assert "__learn_da_candidates = ('result', 'df')" in sandbox.executed_code
