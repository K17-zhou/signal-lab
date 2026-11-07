"""Maintainer-only builder; the delivered demo never downloads or installs packages."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from urllib.request import urlopen
import zipfile

from portable import (PYTHON_VERSION, PYTHON_ZIP_SHA256, PortableError, ROOT,
                      archive_members, read_lock, sha256, validate_file)


PYTHON_ARCHIVE = f"python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{PYTHON_ARCHIVE}"
PYTHON_SIZE = 10950201
QA = ROOT / ".cache" / "qa" / "defect-fixes" / "portable"


def download(url: str, destination: Path) -> None:
    if not url.startswith("https://www.python.org/ftp/python/"):
        raise PortableError("Runtime downloads must use official python.org HTTPS")
    if destination.exists():
        return
    partial = destination.with_name(destination.name + ".part")
    with urlopen(url, timeout=90) as response, partial.open("wb") as output:
        if not response.geturl().startswith("https://www.python.org/"):
            raise PortableError("Runtime download redirected away from official python.org HTTPS")
        shutil.copyfileobj(response, output, length=1024 * 1024)
    partial.replace(destination)


def vendor_locked_packages(site: Path, destination: Path, locked: dict[str, str]) -> None:
    distributions = {str(distribution.metadata["Name"]).lower().replace("_", "-"): distribution
                     for distribution in importlib.metadata.distributions(path=[str(site)])}
    copied = set()
    for name, version in locked.items():
        distribution = distributions.get(name)
        if distribution is None or distribution.version != version:
            raise PortableError(f"The source venv does not contain locked {name}=={version}")
        if distribution.files is None:
            raise PortableError(f"The source distribution has no RECORD: {name}")
        for entry in distribution.files:
            relative = Path(str(entry))
            if ".." in relative.parts or "__pycache__" in relative.parts or relative.suffix in (".pyc", ".pyo"):
                continue
            source = site / relative
            if not source.resolve().is_relative_to(site.resolve()) or source.is_symlink():
                raise PortableError(f"Dependency path leaves the source site-packages: {source}")
            if not source.is_file():
                raise PortableError(f"A recorded dependency file is missing: {source}")
            if str(relative).casefold() in copied:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.add(str(relative).casefold())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-site-packages", type=Path, default=ROOT / ".venv" / "Lib" / "site-packages")
    parser.add_argument("--replace", action="store_true", help="Keep the previous private runtime in the QA cache and replace it")
    args = parser.parse_args()
    try:
        if os.name != "nt" or struct.calcsize("P") != 8 or sys.version.split()[0] != PYTHON_VERSION:
            raise PortableError(f"Build with the locked Windows x64 Python {PYTHON_VERSION} development environment")
        site = args.source_site_packages.resolve()
        if not site.is_relative_to(ROOT) or not site.is_dir():
            raise PortableError("The source site-packages must exist inside this project")
        QA.mkdir(parents=True, exist_ok=True)
        downloads = QA / "downloads"
        downloads.mkdir(exist_ok=True)
        archive = downloads / PYTHON_ARCHIVE
        spdx = downloads / (PYTHON_ARCHIVE + ".spdx.json")
        download(PYTHON_URL + ".spdx.json", spdx)
        metadata = json.loads(spdx.read_text(encoding="utf-8"))
        published = next(package for package in metadata["packages"]
                         if package.get("packageFileName") == PYTHON_ARCHIVE)
        upstream_hash = next(checksum["checksumValue"] for checksum in published["checksums"]
                             if checksum["algorithm"] == "SHA256")
        if upstream_hash != PYTHON_ZIP_SHA256:
            raise PortableError("The official SPDX checksum differs from the pinned CPython release")
        download(PYTHON_URL, archive)
        validate_file(archive, PYTHON_SIZE, upstream_hash, "Official CPython archive")
        locked = read_lock(ROOT / "backend" / "requirements.lock.txt")
        staging = Path(tempfile.mkdtemp(prefix="python-stage-", dir=QA))
        with zipfile.ZipFile(archive) as zipped:
            members = archive_members(zipped)
            for item, relative in members:
                target = staging / relative
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zipped.read(item))
        vendor_locked_packages(site, staging / "site-packages", locked)
        (staging / "python313._pth").write_text(
            "python313.zip\n.\nsite-packages\n../../backend\n../../scripts\n"
            "# Deliberately do not import site: no global or user packages are loaded.\n", encoding="utf-8")
        shutil.copy2(spdx, staging / "python-source.spdx.json")
        manifest = {"schema_version": 1, "python_version": PYTHON_VERSION,
                    "python_archive_url": PYTHON_URL, "python_archive_size": PYTHON_SIZE,
                    "python_archive_sha256": upstream_hash, "checksum_source_url": PYTHON_URL + ".spdx.json",
                    "dependency_source": "project locked development venv RECORD files, including dist-info and licenses",
                    "lock_sha256": sha256(ROOT / "backend" / "requirements.lock.txt"),
                    "packages": locked, "files": {}}
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                manifest["files"][path.relative_to(staging).as_posix()] = {
                    "size": path.stat().st_size, "sha256": sha256(path)}
        (staging / "portable-runtime.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        target = ROOT / "runtime" / "python"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not args.replace:
                raise PortableError(f"Private runtime already exists: {target}; use --replace to preserve and rebuild it")
            previous = QA / ("previous-python-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
            target.rename(previous)
        staging.rename(target)
        print(json.dumps({"runtime": str(target), "python_archive_size": PYTHON_SIZE,
                          "python_archive_sha256": upstream_hash, "locked_packages": len(locked),
                          "files": len(manifest["files"]),
                          "runtime_bytes": sum(value["size"] for value in manifest["files"].values())}, indent=2))
        return 0
    except (PortableError, OSError, ValueError, KeyError, StopIteration, zipfile.BadZipFile) as error:
        print(f"Portable build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
