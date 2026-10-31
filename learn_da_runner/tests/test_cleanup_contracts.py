from unittest.mock import MagicMock, patch

from runner.local_provider import LocalSubprocessProvider
from runner.provider import DockerExecutionProvider
from runner.schemas import RunnerExecutionRequest, RunnerSessionRequest


def test_containerized_runner_uses_daemon_visible_workspace(tmp_path):
    """The Docker daemon cannot read a Runner container's private /tmp."""
    from pathlib import Path
    from types import SimpleNamespace
    from runner.settings import runner_settings

    shared = tmp_path / "shared-with-daemon"
    shared.mkdir()
    config = runner_settings.model_dump()
    config["RUNNER_WORK_ROOT"] = str(shared)
    client = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b""

    def run(**kwargs):
        source = Path(next(iter(kwargs["volumes"])))
        assert source.parent == shared
        assert (source / "driver.py").is_file()
        assert kwargs["volumes"][str(source)]["mode"] == "ro"
        return container

    client.containers.run.side_effect = run
    request = RunnerSessionRequest(
        requestId="22222222-2222-2222-2222-222222222222",
        cells=[{"cellId": "c1", "code": "x=1"}],
    )
    with patch("runner.provider.runner_settings", SimpleNamespace(**config)):
        provider = DockerExecutionProvider()
        provider._client = client
        result = provider.execute_session(request)
    assert result["errorType"] == "driver_protocol_error", result
    assert not list(shared.iterdir()), "Session files must be cleaned after execution"


def test_docker_stdout_and_stderr_are_separate():
    client = MagicMock()
    container = client.containers.run.return_value
    container.wait.return_value = {"StatusCode": 1}
    def logs(*, stdout, stderr):
        return b"ordinary output\n" if stdout and not stderr else b"ValueError: real failure\n" if stderr and not stdout else b"mixed output\n"
    container.logs.side_effect = logs
    provider = DockerExecutionProvider()
    provider._client = client
    result = provider.execute(RunnerExecutionRequest(requestId="22222222-2222-2222-2222-222222222222", code="raise ValueError()", source="playground"))
    assert result["stdout"] == "ordinary output\n"
    assert result["stderr"] == "ValueError: real failure\n"


def test_local_session_exception_kills_and_reaps_child():
    child = MagicMock()
    child.wait.side_effect = [RuntimeError("wait failed"), 0]
    child.poll.return_value = None
    request = RunnerSessionRequest(requestId="22222222-2222-2222-2222-222222222222",
                                   cells=[{"cellId":"c1", "code":"x=1"}])
    with patch("runner.local_provider.subprocess.Popen", return_value=child):
        result = LocalSubprocessProvider().execute_session(request)
    assert result["status"] == "error"
    child.kill.assert_called_once()
    assert child.wait.call_count == 2


def test_provider_pins_image_id_instead_of_resolving_mutable_tag_each_run():
    client=MagicMock()
    client.images.get.return_value.id="sha256:first"
    container=client.containers.run.return_value
    container.wait.return_value={"StatusCode":0}
    container.logs.return_value=b""
    provider=DockerExecutionProvider()
    provider._client=client
    request=RunnerExecutionRequest(requestId="22222222-2222-2222-2222-222222222222",code="print(1)",source="playground")
    provider.execute(request)
    client.images.get.return_value.id="sha256:changed-tag"
    provider.execute(request)
    assert [call.kwargs["image"] for call in client.containers.run.call_args_list] == ["sha256:first","sha256:first"]
    client.images.get.assert_called_once()
