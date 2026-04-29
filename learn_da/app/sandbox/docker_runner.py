import time

from config.settings import settings

from .schemas import SandboxExecutionResult


class DockerSandboxRunner:
    def execute(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        started_at = time.perf_counter()

        if not settings.SANDBOX_DOCKER_ENABLED:
            raise RuntimeError("Docker sandbox is disabled")

        try:
            import docker
        except ImportError as exc:
            raise RuntimeError("docker SDK is not installed") from exc

        timeout_seconds = timeout or settings.SANDBOX_TIMEOUT_SECONDS
        docker_host = settings.SANDBOX_DOCKER_HOST
        if docker_host:
            client = docker.DockerClient(base_url=docker_host)
        else:
            client = docker.from_env()

        container = None
        try:
            container = client.containers.run(
                image=settings.SANDBOX_DOCKER_IMAGE,
                command=["python", "-c", code],
                mem_limit=f"{settings.SANDBOX_MEMORY_LIMIT_MB}m",
                cpu_period=100000,
                cpu_quota=settings.SANDBOX_CPU_QUOTA,
                detach=True,
                network_mode="none",
                read_only=True,
                stderr=True,
                stdout=True,
                remove=False,
                working_dir="/tmp",
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            )
            result = container.wait(timeout=timeout_seconds)
            output = container.logs(stdout=True, stderr=False).decode("utf-8")
            errors = container.logs(stdout=False, stderr=True).decode("utf-8")
            status = "success" if result.get("StatusCode", 1) == 0 else "error"
            execution_time_ms = int((time.perf_counter() - started_at) * 1000)
            return SandboxExecutionResult(
                status=status,
                stdout=output,
                stderr=errors,
                execution_time=execution_time_ms,
                used_sandbox="docker",
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            client.close()
