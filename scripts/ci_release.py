#!/usr/bin/env python3
"""Plan against the actual successful server release; package only changed components."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

IMAGE_NAME = "ghcr.io/1783334779/fastapiadmin-backend"
SHA = re.compile(r"[0-9a-f]{40}\Z")


def plan(baseline: dict, head: str) -> dict:
    if not SHA.fullmatch(head):
        raise ValueError("Invalid target commit")
    base = baseline.get("sha")
    if base is not None and not SHA.fullmatch(base):
        raise ValueError("Invalid server baseline")
    full = baseline.get("format") != 2
    paths = []
    if not full:
        available = subprocess.run(["git", "merge-base", "--is-ancestor", base, head], check=False).returncode == 0
        if available:
            paths = subprocess.check_output(["git", "diff", "--name-only", "--no-renames", "-z", base, head]).decode().split("\0")
            paths = [path for path in paths if path]
        else:
            full = True
    frontend = backend = app = full
    for path in paths:
        if path.startswith("frontend/web/"):
            frontend = True
        elif path.startswith("frontend/app/"):
            app = True
        elif path.startswith("backend/"):
            backend = True
        elif path.startswith("docs/") or path in {"README.md", "README.en.md", "LICENSE", "AGENTS.md"}:
            continue
        else:
            # Shared tooling / Docker / workflows / unknown inputs: fail safe to a full release.
            frontend = backend = app = True
    return {"sha": head, "base_sha": base, "frontend": frontend, "backend": backend,
            "app": app, "deploy": frontend or backend, "baseline": baseline,
            "reason": "full-bootstrap-or-unavailable-baseline" if full else "diff-from-successful-server-release"}


def package(release_plan: dict, release: Path, digest: str) -> dict:
    if not release_plan["deploy"]:
        raise ValueError("No deployment required")
    baseline = release_plan["baseline"]
    sha = release_plan["sha"]
    if release_plan["backend"] and not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Missing immutable backend image digest")
    manifest = {
        "format": 2, "sha": sha, "base_sha": release_plan["base_sha"],
        "frontend_changed": release_plan["frontend"], "backend_changed": release_plan["backend"],
        "frontend_sha": sha if release_plan["frontend"] else baseline["frontend_sha"],
        "backend_sha": sha if release_plan["backend"] else baseline["backend_sha"],
        "image": f"{IMAGE_NAME}@{digest}" if release_plan["backend"] else baseline["image"],
    }
    release.mkdir(parents=True, exist_ok=True)
    if manifest["frontend_changed"]:
        if not (release / "web/index.html").is_file():
            raise ValueError("Checked frontend artifact missing")
        (release / "web/version.json").write_text(json.dumps({
            "sha": sha, "frontend_sha": manifest["frontend_sha"], "backend_sha": manifest["backend_sha"],
        }))
    (release / "release.json").write_text(json.dumps(manifest))
    for name in ("docker-compose.yaml", "docker-compose.ci.yaml", "redis/conf/redis.conf", "nginx/host-ci.conf.template"):
        destination = release / "docker" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path("docker") / name, destination)
    shutil.copytree("docker/mysql/init", release / "docker/mysql/init", dirs_exist_ok=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("plan")
    prepare.add_argument("--baseline", type=Path, required=True)
    prepare.add_argument("--sha", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    bundle = sub.add_parser("package")
    bundle.add_argument("--plan", type=Path, required=True)
    bundle.add_argument("--release", type=Path, required=True)
    bundle.add_argument("--digest", default="")
    arguments = parser.parse_args()
    if arguments.action == "plan":
        result = plan(json.loads(arguments.baseline.read_text()), arguments.sha)
        arguments.output.write_text(json.dumps(result))
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a") as stream:
                for key in ("frontend", "backend", "app", "deploy"):
                    stream.write(f"{key}={str(result[key]).lower()}\n")
        print(json.dumps({key: value for key, value in result.items() if key != "baseline"}))
    else:
        print(json.dumps(package(json.loads(arguments.plan.read_text()), arguments.release, arguments.digest)))


if __name__ == "__main__":
    main()
