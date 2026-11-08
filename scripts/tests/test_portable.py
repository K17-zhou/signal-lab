"""Behavior checks for the offline launcher; run with Python's unittest."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile


PROJECT = Path(__file__).resolve().parents[2]


def load_launcher(test):
    path = PROJECT / "scripts" / "portable.py"
    test.assertTrue(path.is_file(), "The portable launcher has not been implemented")
    spec = importlib.util.spec_from_file_location("portable_launcher_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.launcher = load_launcher(self)
        cache = PROJECT / ".cache" / "qa" / "defect-fixes" / "portable" / "unittest"
        cache.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, entries):
        archive = self.root / "runner.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, content in entries:
                zipped.writestr(name, content)
        return archive, archive.stat().st_size, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_changed_archive_is_rejected_before_any_extraction(self):
        archive, size, digest = self.archive([("llama-server.exe", b"runner")])
        archive.write_bytes(archive.read_bytes() + b"changed")
        target = self.root / "runner"
        with self.assertRaises(self.launcher.PortableError):
            self.launcher.ensure_runtime(archive, target, size, digest)
        self.assertFalse(target.exists())

    def test_archive_cannot_escape_with_windows_or_posix_paths(self):
        for name in ("../escaped.dll", "..\\escaped.dll", "/escaped.dll", "C:/escaped.dll", "good.dll:stream"):
            with self.subTest(name=name):
                archive, size, digest = self.archive([(name, b"untrusted")])
                with self.assertRaises(self.launcher.PortableError):
                    self.launcher.ensure_runtime(archive, self.root / "runner", size, digest)
                self.assertFalse((self.root / "escaped.dll").exists())

    def test_archive_symlink_and_windows_case_collision_are_rejected(self):
        link = zipfile.ZipInfo("linked.dll")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        for entries in ([(link, b"outside")], [("FILE.dll", b"first"), ("file.dll", b"second")]):
            with self.subTest(entries=entries):
                archive, size, digest = self.archive(entries)
                with self.assertRaises(self.launcher.PortableError):
                    self.launcher.ensure_runtime(archive, self.root / "runner", size, digest)

    def test_all_runtime_dlls_are_preserved_and_modified_cache_is_rejected(self):
        archive, size, digest = self.archive([
            ("llama-server.exe", b"runner"), ("nested/driver.dll", b"driver"),
            ("LICENSE", b"license"),
        ])
        target = self.root / "runner"
        self.launcher.ensure_runtime(archive, target, size, digest)
        self.assertEqual((target / "nested" / "driver.dll").read_bytes(), b"driver")
        self.assertEqual((target / "LICENSE").read_bytes(), b"license")
        (target / "nested" / "driver.dll").write_bytes(b"changed")
        with self.assertRaises(self.launcher.PortableError):
            self.launcher.ensure_runtime(archive, target, size, digest)

    def test_occupied_port_is_refused_and_listener_remains_open(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(self.launcher.PortableError, str(port)):
                self.launcher.assert_ports_available([port])
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def test_data_and_temp_paths_are_local_and_study_settings_are_cleared(self):
        inherited = {"PATH": "isolated", "SIGNAL_LAB_DB_PATH": "existing.sqlite3",
                     "SIGNAL_LAB_STUDY_ASSIGNMENTS": "study.json", "PYTHONPATH": "external"}
        data = self.root / "demo data"
        run = data / "logs" / "one"
        environment = self.launcher.build_environment(self.root, data, run, 18091, inherited)
        self.assertEqual(environment["SIGNAL_LAB_DB_PATH"], str(data / "portable.sqlite3"))
        self.assertEqual(environment["SIGNAL_LAB_STUDY_ASSIGNMENTS"], "")
        self.assertEqual(environment["SIGNAL_LAB_TUTOR_PORT"], "18091")
        self.assertNotIn("PYTHONPATH", environment)
        self.assertEqual(environment["PATH"], "isolated")
        for key in ("TEMP", "TMP", "TMPDIR"):
            self.assertTrue(Path(environment[key]).is_relative_to(run))

    def test_startup_fails_when_own_child_exits_even_if_a_health_url_is_good(self):
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(23)"])
        child.wait(timeout=5)
        with self.assertRaisesRegex(self.launcher.PortableError, "23"):
            self.launcher.wait_for_health(child, "http://127.0.0.1:1/health", timeout=0.1)

    def test_health_from_an_unrelated_service_cannot_confirm_own_startup(self):
        class HealthyHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        log = self.root / "own.log"
        log.write_text("own child has not bound the port", encoding="utf-8")
        try:
            with self.assertRaises(self.launcher.PortableError):
                self.launcher.wait_for_health(child, f"http://127.0.0.1:{server.server_port}/health",
                                              timeout=0.2, ready_log=log, ready_text="listening on")
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=5)
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_cleanup_stops_owned_child_and_leaves_unrelated_child_alive(self):
        owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            self.launcher.stop_owned_processes([self.launcher.OwnedProcess("test", owned)], timeout=1)
            self.assertIsNotNone(owned.poll())
            self.assertIsNone(unrelated.poll())
        finally:
            for child in (owned, unrelated):
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)

    @unittest.skipUnless(os.name == "nt", "Windows console fallback")
    def test_cleanup_works_when_a_child_has_no_console_for_ctrl_break(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        child._portable_process_group = True
        try:
            self.launcher.stop_owned_processes([self.launcher.OwnedProcess("no-console", child)], timeout=1)
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)

    def test_private_runtime_check_runs_s1_through_the_real_api(self):
        sys.path.insert(0, str(PROJECT / "backend"))
        self.addCleanup(sys.path.remove, str(PROJECT / "backend"))
        with patch.dict(os.environ, {"SIGNAL_LAB_STUDY_ASSIGNMENTS": ""}):
            result = self.launcher.numerical_check(PROJECT, self.root)
        self.assertEqual(result["health"]["status"], "ok")
        self.assertEqual(result["S1"]["alias_frequency_hz"], 50)
        self.assertEqual(result["S1"]["peak_frequency_hz"], 50)
        self.assertEqual(result["frontend_status"], 200)

    def test_backend_cleanup_uses_its_own_stop_marker_and_shuts_down_cleanly(self):
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        stop = self.root / "stop-backend"
        log = self.root / "backend.log"
        environment = self.launcher.build_environment(PROJECT, self.root, self.root / "run", 18091)
        with log.open("wb") as output:
            child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(PROJECT / "scripts" / "portable.py"),
                                      "--_serve-backend", "--port", str(port), "--_stop-file", str(stop)],
                                     cwd=PROJECT, env=environment, stdout=output, stderr=subprocess.STDOUT)
            try:
                self.launcher.wait_for_health(child, f"http://127.0.0.1:{port}/api/health", timeout=30,
                                              ready_log=log, ready_text="Uvicorn running on")
                self.launcher.stop_owned_processes([self.launcher.OwnedProcess("backend", child, stop)], timeout=10)
                self.assertEqual(child.returncode, 0)
                self.assertTrue(stop.is_file())
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)
        self.assertIn("Application shutdown complete", log.read_text(encoding="utf-8"))

    def launch_with_synthetic_model(self, *, status=200, response=None, options=()):
        """Exercise main with a real HTTP peer and owned, lightweight subprocesses."""
        root = Path(tempfile.mkdtemp(prefix="synthetic-launch-", dir=self.root))
        for relative in ("runtime/python/python.exe", "frontend/dist/index.html", "model/model.gguf",
                         "runtime/runner/llama-server.exe", "runtime/" + self.launcher.LLAMA_ZIP):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic test fixture")
        events, requests, children, browser_observations = [], [], [], []
        reply = response if response is not None else {
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 841, "completion_tokens": 1},
        }

        class ModelHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append({"path": self.path, "payload": json.loads(body),
                                 "ready_exists": bool(list((root / "data").glob("logs/*/ready.json")))})
                events.append("warmup request")
                encoded = reply if isinstance(reply, bytes) else json.dumps(reply).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        real_popen, private_python = subprocess.Popen, sys.executable
        stop = root / "stop-main"

        def start_lightweight_child(command, **kwargs):
            backend = "--_serve-backend" in command
            name = "backend" if backend else "model"
            events.append(name + " start")
            if backend:
                marker = command[command.index("--_stop-file") + 1]
                program = "from pathlib import Path\nimport sys,time\np=Path(sys.argv[1])\nwhile not p.exists(): time.sleep(0.05)"
                child = real_popen([private_python, "-B", "-X", "utf8", "-c", program, marker], **kwargs)
            else:
                child = real_popen([private_python, "-B", "-X", "utf8", "-c", "import time; time.sleep(60)"], **kwargs)
            children.append(child)
            return child

        def healthy(child, url, **kwargs):
            events.append(("backend" if "/api/" in url else "model") + " health")
            return {"status": "ok"}

        def open_browser(url):
            events.append("browser")
            browser_observations.append({"request_count": len(requests),
                                         "ready_exists": bool(list((root / "data").glob("logs/*/ready.json")))})
            stop.touch()
            return True

        output, errors = StringIO(), StringIO()
        arguments = ["portable.py", "--cpu", "--model-port", str(server.server_port),
                     "--data-dir", str(root / "data"), "--stop-file", str(stop), *options]
        try:
            with ExitStack() as patches:
                patches.enter_context(patch.dict(os.environ))
                patches.enter_context(patch.object(self.launcher, "ROOT", root))
                patches.enter_context(patch.object(sys, "executable", str(root / "runtime/python/python.exe")))
                patches.enter_context(patch.object(sys, "argv", arguments))
                patches.enter_context(patch.object(self.launcher, "verify_python_runtime", return_value={"source": "synthetic test fixture"}))
                patches.enter_context(patch.object(self.launcher, "validate_file"))
                patches.enter_context(patch.object(self.launcher, "ensure_runtime", return_value=root / "runtime/runner"))
                patches.enter_context(patch.object(self.launcher, "assert_ports_available"))
                patches.enter_context(patch.object(self.launcher, "numerical_check", return_value={"S1": "checked"}))
                patches.enter_context(patch.object(self.launcher, "wait_for_health", side_effect=healthy))
                patches.enter_context(patch.object(subprocess, "Popen", side_effect=start_lightweight_child))
                patches.enter_context(patch.object(self.launcher.webbrowser, "open", side_effect=open_browser))
                patches.enter_context(redirect_stdout(output))
                patches.enter_context(redirect_stderr(errors))
                try:
                    code = self.launcher.main()
                except SystemExit as error:
                    code = error.code
            return {"code": code, "events": events, "requests": requests, "children": children,
                    "child_exit_codes_before_fixture_cleanup": [child.poll() for child in children],
                    "browser": browser_observations, "stdout": output.getvalue(), "stderr": errors.getvalue(),
                    "ready": list((root / "data").glob("logs/*/ready.json")),
                    "warmup_logs": list((root / "data").glob("logs/*/startup-warmup.json"))}
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_default_startup_warms_synthetic_prefill_before_backend_ready_and_browser(self):
        result = self.launch_with_synthetic_model()
        self.assertEqual(result["code"], 0, result["stderr"])
        self.assertEqual(result["events"], ["model start", "model health", "warmup request",
                                             "backend start", "backend health", "browser"])
        self.assertEqual(result["browser"], [{"request_count": 1, "ready_exists": True}])
        self.assertEqual(len(result["ready"]), 1)
        request = result["requests"][0]
        self.assertEqual(request["path"], "/v1/chat/completions")
        self.assertIs(request["ready_exists"], False)
        payload = request["payload"]
        self.assertEqual(payload["model"], self.launcher.MODEL_ALIAS)
        self.assertIn(payload["max_tokens"], range(1, 5))
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertIs(payload["stream"], False)
        content = " ".join(message["content"] for message in payload["messages"])
        self.assertIn("synthetic startup warmup", content.lower())
        self.assertEqual(content.split().count("a"), 800)
        for forbidden in ("session_id", "run_id", "transfer", "prediction", "study", "学习", "迁移"):
            self.assertNotIn(forbidden, json.dumps(payload, ensure_ascii=False).lower())
        self.assertEqual(len(result["warmup_logs"]), 1)
        report = json.loads(result["warmup_logs"][0].read_text(encoding="utf-8"))
        self.assertEqual(report["source"], "synthetic_startup_warmup")
        self.assertIs(report["is_user_guidance"], False)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["prompt_tokens"], 841)

    def test_failed_warmup_cannot_report_ready_open_browser_or_leave_owned_services(self):
        for status, response in ((503, {"error": "synthetic failure"}), (200, b"not json"),
                                 (200, {"choices": []}), (200, {"choices": [{"message": {"content": ""}}]})):
            with self.subTest(status=status, response=response):
                result = self.launch_with_synthetic_model(status=status, response=response)
                self.assertEqual(result["code"], 1, result["stdout"])
                self.assertIn("synthetic startup warmup", result["stderr"].lower())
                self.assertEqual(result["events"], ["model start", "model health", "warmup request"])
                self.assertEqual(result["browser"], [])
                self.assertEqual(result["ready"], [])
                self.assertNotIn("READY http", result["stdout"])
                self.assertEqual(len(result["children"]), 1)
                self.assertTrue(all(code is not None for code in result["child_exit_codes_before_fixture_cleanup"]))
                report = json.loads(result["warmup_logs"][0].read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "failed")

    def test_check_does_not_start_a_model_or_send_a_warmup_request(self):
        result = self.launch_with_synthetic_model(options=("--check",))
        self.assertEqual(result["code"], 0, result["stderr"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["requests"], [])
        self.assertEqual(result["children"], [])
        self.assertEqual(result["browser"], [])
        self.assertEqual(result["ready"], [])
        self.assertEqual(result["warmup_logs"], [])

    def test_explicit_skip_warmup_keeps_the_performance_diagnostic_path(self):
        result = self.launch_with_synthetic_model(options=("--skip-warmup",))
        self.assertEqual(result["code"], 0, result["stderr"])
        self.assertEqual(result["requests"], [])
        self.assertEqual(result["events"], ["model start", "model health", "backend start", "backend health", "browser"])
        self.assertEqual(len(result["ready"]), 1)
        report = json.loads(result["warmup_logs"][0].read_text(encoding="utf-8"))
        self.assertEqual(report["source"], "synthetic_startup_warmup")
        self.assertEqual(report["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
