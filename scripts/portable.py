"""Offline demo launcher for the application's private Windows Python runtime."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPException
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import webbrowser
import zipfile


sys.dontwritebytecode = True
ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.13.13"
PYTHON_ZIP_SHA256 = "8766a8775746235e23cf5aee5027ab1060bb981d93110577adcf3508aa0cbd55"
MODEL_NAME = "Qwen3.5-4B-Q4_K_M.gguf"
MODEL_SIZE = 2740937888
MODEL_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
LLAMA_ZIP = "llama-b11814-bin-win-vulkan-x64.zip"
LLAMA_SIZE = 36867710
LLAMA_SHA256 = "0df9335f755538317d59b3442d9b28d68635742f381cdec743221c8dca7a4040"
MODEL_ALIAS = "signal-lab-tutor"
WARMUP_TIMEOUT_SECONDS = 120
# Repeated synthetic padding exercises roughly the same prefill size as guidance.
# It contains no application context, user records, assessment items, or results.
WARMUP_PROMPT = (
    "Synthetic startup warmup. This fixed generated text prepares the local runtime. Reply OK only.\n"
    + " a" * 800
)


class PortableError(RuntimeError):
    """An actionable failure that must not start or reuse an unknown service."""


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_file(path: Path, size: int, digest: str, label: str) -> None:
    if not path.is_file() or path.stat().st_size != size or sha256(path) != digest:
        raise PortableError(f"{label} is missing or differs from the verified release: {path}")


def archive_members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, Path]]:
    """Validate Windows and POSIX names before creating any output files."""
    members = []
    names = set()
    for item in archive.infolist():
        raw = item.filename.replace("\\", "/")
        relative = PurePosixPath(raw)
        parts = relative.parts
        if (not parts or raw.startswith("/") or "\x00" in raw or
                any(part in ("..", ".") or ":" in part or part.rstrip(" .") != part for part in parts) or
                stat.S_ISLNK(item.external_attr >> 16)):
            raise PortableError(f"Unsafe archive path: {item.filename!r}")
        key = "/".join(parts).casefold()
        if key in names:
            raise PortableError(f"Duplicate archive path: {item.filename!r}")
        names.add(key)
        members.append((item, Path(*parts)))
    return members


def ensure_runtime(archive_path: Path, destination: Path, size: int = LLAMA_SIZE,
                   digest: str = LLAMA_SHA256) -> Path:
    """Extract a verified ZIP once and reject a modified existing runtime."""
    validate_file(archive_path, size, digest, "llama.cpp archive")
    with zipfile.ZipFile(archive_path) as archive:
        members = archive_members(archive)
        if destination.exists():
            for item, relative in members:
                target = destination / relative
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise PortableError(f"Runtime path escapes its directory: {target}")
                if item.is_dir():
                    continue
                expected = hashlib.sha256(archive.read(item)).hexdigest()
                validate_file(target, item.file_size, expected, "Extracted llama.cpp file")
            expected_files = {relative.as_posix().casefold() for item, relative in members if not item.is_dir()}
            for target in destination.rglob("*"):
                if target.is_file() and target.relative_to(destination).as_posix().casefold() not in expected_files:
                    raise PortableError(f"Unexpected file in the llama.cpp cache: {target}")
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="llama-extract-", dir=destination.parent))
        try:
            for item, relative in members:
                target = staging / relative
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, target.open("xb") as output:
                        while block := source.read(1024 * 1024):
                            output.write(block)
            staging.rename(destination)
        except BaseException:
            # Leave partial extraction under its unique name for diagnosis; it is never executed.
            raise
    return destination


def read_lock(path: Path) -> dict[str, str]:
    locked = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line)
        if not match:
            raise PortableError(f"The dependency lock is not an exact version pin: {line}")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in locked:
            raise PortableError(f"Duplicate dependency in lock: {name}")
        locked[name] = match[2]
    if not locked:
        raise PortableError("The dependency lock is empty")
    return locked


def verify_python_runtime(root: Path) -> dict:
    runtime = root / "runtime" / "python"
    manifest = json.loads((runtime / "portable-runtime.json").read_text(encoding="utf-8"))
    if sys.version.split()[0] != PYTHON_VERSION or manifest["python_archive_sha256"] != PYTHON_ZIP_SHA256:
        raise PortableError("The private Python runtime does not match the pinned release")
    locked = read_lock(root / "backend" / "requirements.lock.txt")
    if manifest["packages"] != locked:
        raise PortableError("The private runtime was built for a different dependency lock")
    for name, version in locked.items():
        distribution = importlib.metadata.distribution(name)
        if distribution.version != version or not Path(distribution.locate_file("")).resolve().is_relative_to(runtime):
            raise PortableError(f"Dependency {name} is not the private locked version {version}")
    for relative, expected in manifest["files"].items():
        target = runtime / relative
        if not target.resolve().is_relative_to(runtime):
            raise PortableError(f"Runtime inventory path escapes its directory: {relative}")
        validate_file(target, expected["size"], expected["sha256"], "Private Python file")
    return {"python": sys.version, "executable": sys.executable, "sys_path": sys.path,
            "locked_packages": len(locked), "runtime_files_verified": len(manifest["files"])}


def assert_ports_available(ports: list[int]) -> None:
    if len(set(ports)) != len(ports):
        raise PortableError("The application and model ports must differ")
    sockets = []
    try:
        for port in ports:
            listener = socket.socket()
            sockets.append(listener)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise PortableError(f"Port {port} is already in use; choose another port. Existing services were left running.") from error
    finally:
        for listener in sockets:
            listener.close()


def build_environment(root: Path, data: Path, run: Path, model_port: int,
                      inherited: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if inherited is None else inherited)
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
        environment.pop(name, None)
    temp = run / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    environment.update({"TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp),
                        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                        "SIGNAL_LAB_DB_PATH": str(data / "portable.sqlite3"),
                        "SIGNAL_LAB_STUDY_ASSIGNMENTS": "",
                        "SIGNAL_LAB_TUTOR_MODEL": MODEL_ALIAS,
                        "SIGNAL_LAB_TUTOR_PORT": str(model_port)})
    return environment


def wait_for_health(child: subprocess.Popen, url: str, timeout: float,
                    ready_log: Path | None = None, ready_text: str | None = None) -> dict:
    address = urlsplit(url)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = child.poll()
        if code is not None:
            raise PortableError(f"Owned service exited during startup (exit code {code}): {url}")
        if ready_log is not None and ready_text not in ready_log.read_text(encoding="utf-8", errors="replace"):
            time.sleep(0.1)
            continue
        connection = HTTPConnection(address.hostname, address.port, timeout=min(1, timeout))
        try:
            connection.request("GET", address.path)
            response = connection.getresponse()
            body = response.read(65536)
            if response.status == 200:
                result = json.loads(body)
                # The child must still be alive after responding, never reuse a stale port.
                time.sleep(0.15)
                if child.poll() is not None:
                    raise PortableError(f"Owned service exited during startup (exit code {child.returncode}): {url}")
                if result.get("status") == "ok":
                    return result
        except (OSError, HTTPException, ValueError):
            pass
        finally:
            connection.close()
        time.sleep(0.2)
    raise PortableError(f"Service did not become healthy within {timeout:g} seconds: {url}")


def warmup_model(port: int, log: Path) -> dict:
    """Prepare a cold model before exposing the app; never create a tutor call."""
    payload = {
        "model": MODEL_ALIAS,
        "messages": [{"role": "user", "content": WARMUP_PROMPT}],
        "stream": False,
        "max_tokens": 2,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    report = {"source": "synthetic_startup_warmup", "is_user_guidance": False,
              "status": "in_progress", "timeout_seconds": WARMUP_TIMEOUT_SECONDS,
              "max_tokens": payload["max_tokens"]}
    log.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Running synthetic startup warmup (not user guidance)...", flush=True)
    started = time.monotonic()
    connection = HTTPConnection("127.0.0.1", port, timeout=WARMUP_TIMEOUT_SECONDS)
    try:
        connection.request("POST", "/v1/chat/completions", json.dumps(payload).encode("utf-8"),
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        body = response.read(65537)
        if response.status != 200:
            raise ValueError(f"model returned HTTP {response.status}")
        if len(body) > 65536:
            raise ValueError("model response exceeded the warmup size limit")
        envelope = json.loads(body)
        message = envelope["choices"][0]["message"]["content"]
        if not isinstance(message, str) or not message.strip():
            raise ValueError("model returned no completion text")
        usage = envelope["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        report.update({"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens})
        if type(prompt_tokens) is not int or not 800 <= prompt_tokens <= 900:
            raise ValueError(f"synthetic prefill was outside 800-900 tokens: {prompt_tokens!r}")
        if type(completion_tokens) is not int or not 1 <= completion_tokens <= payload["max_tokens"]:
            raise ValueError("model returned invalid completion usage")
        report["status"] = "completed"
    except (OSError, HTTPException, ValueError, KeyError, IndexError, TypeError) as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        raise PortableError(f"Synthetic startup warmup failed: {error}; see {log}") from error
    finally:
        connection.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Synthetic startup warmup completed ({prompt_tokens} prompt tokens, "
          f"{report['elapsed_seconds']:.3f}s; not user guidance).", flush=True)
    return report


@dataclass
class OwnedProcess:
    name: str
    process: subprocess.Popen
    stop_file: Path | None = None


def stop_owned_processes(children: list[OwnedProcess], timeout: float = 5) -> None:
    for owned in reversed(children):
        child = owned.process
        if child.poll() is not None:
            continue
        try:
            if owned.stop_file is not None:
                owned.stop_file.touch()
            elif os.name == "nt" and getattr(child, "_portable_process_group", False):
                try:
                    child.send_signal(signal.CTRL_BREAK_EVENT)
                except OSError:
                    # A headless parent may have no Windows console for a control event.
                    child.terminate()
            else:
                child.terminate()
            try:
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=timeout)
        except ProcessLookupError:
            pass


def serve_backend(port: int, stop_file: Path) -> int:
    import uvicorn
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port,
                                          workers=1, reload=False))

    def watch_stop():
        while not stop_file.is_file():
            time.sleep(0.1)
        server.should_exit = True

    threading.Thread(target=watch_stop, daemon=True).start()
    server.run()
    return 0 if server.started else 1


def numerical_check(root: Path, data: Path) -> dict:
    import numpy
    import scipy
    import sqlite3
    import fastapi
    from fastapi.testclient import TestClient
    from app.main import create_app

    result = {"numpy": numpy.__version__, "scipy": scipy.__version__,
              "fastapi": fastapi.__version__, "sqlite": sqlite3.sqlite_version}
    with TestClient(create_app(database_path=data / "check.sqlite3")) as client:
        health = client.get("/api/health")
        response = client.post("/api/experiments/run", json={
            "experiment_type": "sampling_aliasing",
            "params": {"frequency_hz": 50, "sample_rate_hz": 400},
        })
        if health.status_code != 200 or response.status_code != 200:
            raise PortableError(f"Bundled API check failed: {health.status_code}, {response.status_code}")
        metrics = response.json()["metrics"]
        if abs(metrics["alias_frequency_hz"] - 50) > 1e-9 or abs(metrics["peak_frequency_hz"] - 50) > 1e-9:
            raise PortableError(f"Bundled S1 numeric check failed: {metrics}")
        result.update({"health": health.json(), "S1": metrics, "frontend_status": client.get("/").status_code})
        if result["frontend_status"] != 200:
            raise PortableError("The prebuilt frontend could not be served")
    return result


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Port must be an integer") from error
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1024 and 65535")
    return port


def main() -> int:
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    parser = argparse.ArgumentParser(description="Start the offline Signal Lab demo with its private runtime.")
    parser.add_argument("--cpu", action="store_true", help="Use the CPU instead of the default Vulkan GPU")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=port_number, default=8000)
    parser.add_argument("--model-port", type=port_number, default=8081)
    parser.add_argument("--model-path", type=Path, help="Verified GGUF path; relative paths resolve from this project")
    parser.add_argument("--data-dir", type=Path, help="Project-local demo data/log directory (default .cache/portable)")
    parser.add_argument("--check", action="store_true", help="Check all bundled artifacts and compute S1 without starting servers")
    parser.add_argument("--skip-warmup", action="store_true", help="Skip synthetic startup warmup for performance diagnostics")
    parser.add_argument("--stop-file", type=Path, help="Optional project-local marker; create it to stop a headless demo")
    parser.add_argument("--_serve-backend", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_stop-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._serve_backend:
        if not args._stop_file:
            parser.error("Internal backend mode requires a stop file")
        return serve_backend(args.port, args._stop_file)

    children = []
    run = None
    try:
        if os.name != "nt" or sys.maxsize <= 2**32:
            raise PortableError("This demo package requires Windows x64")
        private_python = ROOT / "runtime" / "python" / "python.exe"
        if Path(sys.executable).resolve() != private_python.resolve():
            raise PortableError("Run 开始演示.cmd or runtime\\python\\python.exe scripts\\portable.py")
        data = args.data_dir or ROOT / ".cache" / "portable"
        data = (ROOT / data).resolve() if not data.is_absolute() else data.resolve()
        if not data.is_relative_to(ROOT):
            raise PortableError("Demo data must stay inside this project")
        stop_requested = None
        if args.stop_file:
            stop_requested = (ROOT / args.stop_file).resolve() if not args.stop_file.is_absolute() else args.stop_file.resolve()
            if not stop_requested.is_relative_to(ROOT) or stop_requested.exists():
                raise PortableError("The optional stop marker must be a new project-local file")
            stop_requested.parent.mkdir(parents=True, exist_ok=True)
        run = data / "logs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}")
        run.mkdir(parents=True, exist_ok=False)
        environment = build_environment(ROOT, data, run, args.model_port)
        os.environ.update(environment)
        report = verify_python_runtime(ROOT)
        if not (ROOT / "frontend" / "dist" / "index.html").is_file():
            raise PortableError("The prebuilt frontend/dist is missing; use the complete portable package")
        model = args.model_path or Path("model") / MODEL_NAME
        model = (ROOT / model).resolve() if not model.is_absolute() else model.resolve()
        print("Verifying the model and local runtime...", flush=True)
        validate_file(model, MODEL_SIZE, MODEL_SHA256, "Qwen model")
        archive = ROOT / "runtime" / LLAMA_ZIP
        if not archive.is_file():
            archive = ROOT / ".cache" / "runtimes" / LLAMA_ZIP
        runtime_target = ROOT / ".cache" / "runtimes" / "llama-b11814"
        if not runtime_target.resolve().is_relative_to(ROOT):
            raise PortableError("The llama.cpp cache must stay inside this project")
        runtime = ensure_runtime(archive, runtime_target)
        runner = runtime / "llama-server.exe"
        if not runner.is_file():
            raise PortableError(f"The fixed llama.cpp package has no server: {runner}")
        report.update({"model": str(model), "model_sha256": MODEL_SHA256,
                       "llama_archive": str(archive), "llama_archive_sha256": LLAMA_SHA256})
        if args.check:
            report["numeric_api_check"] = numerical_check(ROOT, data)
            (run / "check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
            return 0

        assert_ports_available([args.port, args.model_port])
        report.update({"application_port": args.port, "model_port": args.model_port, "cpu": args.cpu,
                       "startup_warmup": not args.skip_warmup})
        (run / "launch.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Logs: {run}", flush=True)
        with ExitStack() as logs:
            def start(name, command, stop_file=None):
                output = logs.enter_context((run / f"{name}.log").open("wb"))
                kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=output, stderr=subprocess.STDOUT, **kwargs)
                process._portable_process_group = os.name == "nt"
                owned = OwnedProcess(name, process, stop_file)
                children.append(owned)
                return process

            device = ["--device", "none", "-ngl", "0"] if args.cpu else ["--device", "Vulkan0", "-ngl", "99"]
            llama = start("llama", [str(runner), "-m", str(model), "--alias", MODEL_ALIAS,
                "--host", "127.0.0.1", "--port", str(args.model_port), "-c", "2048", "-np", "1",
                "-t", "4", "-b", "256", "-ub", "128", "--reasoning", "off", *device])
            wait_for_health(llama, f"http://127.0.0.1:{args.model_port}/health", timeout=180,
                            ready_log=run / "llama.log", ready_text=f"listening on http://127.0.0.1:{args.model_port}")
            warmup_log = run / "startup-warmup.json"
            if args.skip_warmup:
                warmup_log.write_text(json.dumps({"source": "synthetic_startup_warmup", "is_user_guidance": False,
                    "status": "skipped", "reason": "explicit --skip-warmup diagnostic option"}, indent=2), encoding="utf-8")
                print("Synthetic startup warmup skipped (--skip-warmup).", flush=True)
            else:
                warmup_model(args.model_port, warmup_log)
            if llama.poll() is not None:
                raise PortableError(f"Model exited before application startup (code {llama.returncode}); see {run}")
            stop_file = run / "stop-backend"
            backend = start("backend", [str(private_python), "-B", "-X", "utf8", str(Path(__file__).resolve()),
                "--_serve-backend", "--port", str(args.port), "--_stop-file", str(stop_file)], stop_file)
            wait_for_health(backend, f"http://127.0.0.1:{args.port}/api/health", timeout=30,
                            ready_log=run / "backend.log", ready_text=f"Uvicorn running on http://127.0.0.1:{args.port}")
            (run / "ready.json").write_text(json.dumps({"application_pid": backend.pid, "model_pid": llama.pid,
                "url": f"http://127.0.0.1:{args.port}"}), encoding="utf-8")
            print(f"READY http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
            if not args.no_browser:
                webbrowser.open(f"http://127.0.0.1:{args.port}")
            while True:
                if stop_requested is not None and stop_requested.is_file():
                    print("Stopping this demo's services...", flush=True)
                    return 0
                for child in children:
                    if child.process.poll() is not None:
                        raise PortableError(f"{child.name} exited (code {child.process.returncode}); see {run}")
                time.sleep(0.4)
    except KeyboardInterrupt:
        print("Stopping this demo's services...", flush=True)
        return 0
    except (PortableError, OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError, zipfile.BadZipFile) as error:
        print(f"Demo could not start: {error}", file=sys.stderr, flush=True)
        if run is not None:
            print(f"Logs: {run}", file=sys.stderr, flush=True)
        return 1
    finally:
        stop_owned_processes(children)


if __name__ == "__main__":
    raise SystemExit(main())
