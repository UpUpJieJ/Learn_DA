"""诊断 Docker stdio 注入路径的探针脚本。

背景：runner 的 Docker 后端需要把判定材料（refs / runtime 源码 / nonce）送进容器，
且不能让学员子进程读到。Part2 原计划走 attach_socket 的 stdin，但服务器实测
容器收不到数据。本脚本跑四组对照实验，判定：

  d1  docker-py attach_socket(stdin=1&stdout=1) —— 数据到底进没进容器（用 tr 变换
      区分「容器真处理过」与「daemon 回显假象」）；
  d2  attach_socket(stdin=1 only)               —— 只挂 stdin 是否也能送达；
  d3  docker CLI attach                          —— CLI 路径是否送达；
  d4  put_archive 注入 + 容器内 chmod/truncate/unlink —— Plan B 可行性
      （含 /tmp tmpfs 的 sticky 位与 65532 属主校验）；
  d5  （d1 成功才跑）attach 通道传 300KB 大包 + md5sum 校验 —— 大输入不卡死。

用法（服务器上）：
    cd /tmp/part2-verify/pkg && ../venv/bin/python scripts/probe_docker_stdio.py
"""

from __future__ import annotations

import hashlib
import io
import socket
import subprocess
import tarfile
import threading
import time

import docker

IMAGE = "polars-duckdb-sandbox:pl1.39.3-duck1.5.1-arrow25.0.1"
c = docker.from_env()


def rm(*names: str) -> None:
    subprocess.run(["docker", "rm", "-f", *names], capture_output=True)


def cli_logs(name: str) -> str:
    r = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
    return (r.stdout + " | " + r.stderr).strip()


def cli_state(name: str) -> str:
    r = subprocess.run(
        ["docker", "inspect", name, "--format", "{{.State.Status}} exit={{.State.ExitCode}}"],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


def wait_exit(name: str, timeout: float = 10.0) -> str:
    for _ in range(int(timeout * 4)):
        st = cli_state(name)
        if st.startswith("exited"):
            return st
        time.sleep(0.25)
    return cli_state(name)


print("=== d1: docker-py attach stdin=1 stdout=1 stream=1, tr a-z A-Z ===")
rm("d1")
d1 = c.containers.run("busybox", ["sh", "-c", "tr a-z A-Z"], detach=True, stdin_open=True, name="d1")
time.sleep(0.5)
sock = c.api.attach_socket(d1.id, params={"stdin": 1, "stdout": 1, "stream": 1})
raw = getattr(sock, "_sock", sock)
chunks: list[bytes] = []


def reader() -> None:
    raw.settimeout(6)
    try:
        while True:
            data = raw.recv(4096)
            if not data:
                chunks.append(b"<EOF>")
                break
            chunks.append(data)
    except Exception as exc:  # noqa: BLE001
        chunks.append(("<ERR %s>" % exc).encode())


t = threading.Thread(target=reader, daemon=True)
t.start()
raw.sendall(b"hello-d1")
time.sleep(1.5)
raw.shutdown(socket.SHUT_WR)
t.join(7)
try:
    sock.close()
except Exception:  # noqa: BLE001
    pass
time.sleep(0.5)
socket_out = b"".join(chunks)
print("socket:", socket_out)
print("logs:", cli_logs("d1"))
print("state:", wait_exit("d1"))
d1_ok = b"HELLO-D1" in socket_out or "HELLO-D1" in cli_logs("d1")

print()
print("=== d2: docker-py attach stdin=1 only, tr a-z A-Z ===")
rm("d2")
d2 = c.containers.run("busybox", ["sh", "-c", "tr a-z A-Z"], detach=True, stdin_open=True, name="d2")
time.sleep(0.5)
sock2 = c.api.attach_socket(d2.id, params={"stdin": 1, "stream": 1})
raw2 = getattr(sock2, "_sock", sock2)
raw2.sendall(b"hello-d2")
time.sleep(1.0)
raw2.shutdown(socket.SHUT_WR)
time.sleep(1.0)
try:
    sock2.close()
except Exception:  # noqa: BLE001
    pass
print("logs:", cli_logs("d2"))
print("state:", wait_exit("d2"))

print()
print("=== d3: docker CLI attach, tr a-z A-Z ===")
rm("d3")
c.containers.run("busybox", ["sh", "-c", "tr a-z A-Z"], detach=True, stdin_open=True, name="d3")
time.sleep(0.5)
r = subprocess.run(
    ["sh", "-c", "printf 'hello-d3' | timeout 5 docker attach d3"],
    capture_output=True,
    text=True,
)
print("attach stdout:", r.stdout.strip(), "| attach stderr:", r.stderr.strip()[:120])
print("logs:", cli_logs("d3"))
print("state:", wait_exit("d3"))

print()
print("=== d4: put_archive 注入 + chmod/truncate/unlink（provider 同款约束）===")
rm("d4")
D4_CODE = (
    "import os, pathlib, time\n"
    "p = pathlib.Path('/tmp/.in')\n"
    "ok = False\n"
    "for _ in range(200):\n"
    "    if p.exists():\n"
    "        ok = True\n"
    "        break\n"
    "    time.sleep(0.05)\n"
    "if not ok:\n"
    "    print('INPUT-NOT-FOUND')\n"
    "    raise SystemExit(0)\n"
    "import stat\n"
    "print('TMP-MODE', oct(stat.S_IMODE(os.stat('/tmp').st_mode)))\n"
    "data = p.read_text()\n"
    "print('READ-OK', len(data), data[:10])\n"
    "os.chmod(p, 0o600)\n"
    "with open(p, 'wb') as f:\n"
    "    f.write(b'')\n"
    "print('TRUNCATED')\n"
    "try:\n"
    "    p.unlink()\n"
    "    print('UNLINKED')\n"
    "except OSError as e:\n"
    "    print('UNLINK-FAIL', e.errno, e.strerror)\n"
    "print('AFTER', 'gone' if not p.exists() else repr(p.read_bytes()))\n"
)
d4 = c.containers.run(
    IMAGE,
    ["python", "-X", "utf8", "-B", "-c", D4_CODE],
    detach=True,
    name="d4",
    user="65532:65532",
    network_mode="none",
    read_only=True,
    cap_drop=["ALL"],
    security_opt=["no-new-privileges"],
    mem_limit="256m",
    pids_limit=64,
    tmpfs={"/tmp": "size=64m"},
)
time.sleep(0.5)
content = b'{"refs": "SECRET-MATERIAL"}'
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as tf:
    info = tarfile.TarInfo(".in")
    info.size = len(content)
    info.mode = 0o400
    info.uid = 65532
    info.gid = 65532
    info.uname = ""
    info.gname = ""
    tf.addfile(info, io.BytesIO(content))
ok, err = d4.put_archive("/tmp", buf.getvalue())
print("put_archive ok:", ok, err if not ok else "")
wait_res = d4.wait(timeout=30)
print("exit:", wait_res)
print("logs:", cli_logs("d4"))

if d1_ok:
    print()
    print("=== d5: attach 通道 300KB 大包 + md5sum 校验 ===")
    rm("d5")
    d5 = c.containers.run(
        "busybox", ["sh", "-c", "md5sum"], detach=True, stdin_open=True, name="d5"
    )
    time.sleep(0.5)
    sock5 = c.api.attach_socket(d5.id, params={"stdin": 1, "stdout": 1, "stream": 1})
    raw5 = getattr(sock5, "_sock", sock5)
    payload = bytes(range(256)) * 1200  # 300KB
    out: list[bytes] = []

    def reader5() -> None:
        raw5.settimeout(15)
        try:
            while True:
                data = raw5.recv(65536)
                if not data:
                    out.append(b"<EOF>")
                    break
                out.append(data)
        except Exception as exc:  # noqa: BLE001
            out.append(("<ERR %s>" % exc).encode())

    t5 = threading.Thread(target=reader5, daemon=True)
    t5.start()
    raw5.sendall(payload)
    raw5.shutdown(socket.SHUT_WR)
    t5.join(16)
    try:
        sock5.close()
    except Exception:  # noqa: BLE001
        pass
    raw_out = b"".join(out)
    # 去掉 8 字节流帧头再比对 md5
    body = raw_out[8:] if raw_out[:1] == b"\x01" else raw_out
    print("expect md5:", hashlib.md5(payload).hexdigest())
    print("socket out:", raw_out[:80], "...")
    print("logs:", cli_logs("d5"))
    print("state:", wait_exit("d5"))

rm("d1", "d2", "d3", "d4", "d5")
print()
print("VERDICT d1(attach stdin+stdout delivers):", d1_ok)
