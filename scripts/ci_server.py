#!/usr/bin/env python3
"""受限 SSH 发布入口。服务器安装位置：/usr/local/sbin/fastapiadmin-ci。

只接受 baseline/receive/deploy/status + 完整 Git SHA，不提供任意远程 shell。
bootstrap 只供管理员首次本机执行；密码不经过 GitHub，不进入镜像或日志。
"""

import argparse
import base64
import datetime as dt
import fcntl
import gzip
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path("/opt/fastapiadmin")
SHARED = ROOT / "shared"
RELEASES = ROOT / "releases"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
IMAGE_PATTERN = re.compile(r"ghcr\.io/1783334779/fastapiadmin-backend@sha256:[0-9a-f]{64}\Z")


def manifest(release: Path, expected_sha: str | None = None) -> dict:
    data = json.loads((release / "release.json").read_text())
    sha = data.get("sha", "")
    if not SHA_PATTERN.fullmatch(sha) or sha != (expected_sha or release.name):
        raise ValueError("Invalid release commit")
    if "format" not in data:
        if data != {"sha": sha, "image": f"backend:sha-{sha}"}:
            raise ValueError("Invalid legacy release")
        return {**data, "format": 1, "frontend_sha": sha, "backend_sha": sha,
                "frontend_changed": True, "backend_changed": True}
    expected = {"format", "sha", "base_sha", "frontend_sha", "backend_sha", "image", "frontend_changed", "backend_changed"}
    if set(data) != expected or data["format"] != 2:
        raise ValueError("Invalid release manifest format")
    for key in ("frontend_sha", "backend_sha"):
        if not isinstance(data[key], str) or not SHA_PATTERN.fullmatch(data[key]):
            raise ValueError("Invalid component commit")
    if data["base_sha"] is not None and not SHA_PATTERN.fullmatch(data["base_sha"]):
        raise ValueError("Invalid baseline commit")
    if not isinstance(data["image"], str) or not IMAGE_PATTERN.fullmatch(data["image"]):
        raise ValueError("Only this repository's immutable GHCR image is allowed")
    for component in ("frontend", "backend"):
        if type(data[f"{component}_changed"]) is not bool:
            raise ValueError("Invalid component change flag")
        if data[f"{component}_changed"] and data[f"{component}_sha"] != sha:
            raise ValueError("Changed component does not match this commit")
    if not data["frontend_changed"] and not data["backend_changed"]:
        raise ValueError("Empty deployment")
    return data


def release_environment(sha: str) -> dict:
    data = manifest(RELEASES / sha)
    return {**os.environ, "BACKEND_IMAGE_TAG": f'sha-{data["backend_sha"]}', "BACKEND_IMAGE": data["image"]}


def running_image_matches(data: dict) -> None:
    actual = subprocess.check_output(["docker", "inspect", "fastapiadmin-backend", "--format", "{{.Image}}"], text=True).strip()
    expected = subprocess.check_output(["docker", "image", "inspect", data["image"], "--format", "{{.Id}}"], text=True).strip()
    if actual != expected:
        raise RuntimeError("Running backend differs from the successful release")


def baseline() -> dict:
    if not (ROOT / "current").is_symlink():
        if (SHARED / "last-success.json").exists():
            raise RuntimeError("Successful release exists but current link is missing")
        return {"sha": None, "format": 0}
    current = (ROOT / "current").resolve()
    if current.parent != RELEASES:
        raise RuntimeError("Current release is outside the release directory")
    data = manifest(current)
    success = json.loads((SHARED / "last-success.json").read_text())
    if success["sha"] != data["sha"]:
        raise RuntimeError("Current release is not the last successful deployment")
    running_image_matches(data)
    health(f'https://{settings()["host"]}/api/v1/monitor/health/check', settings()["host"])
    return data


def validate_baseline(data: dict) -> dict:
    current = baseline()
    if data["base_sha"] != current["sha"]:
        raise RuntimeError("Server baseline changed since planning; rerun the workflow")
    for component in ("frontend", "backend"):
        if not data[f"{component}_changed"]:
            if current["format"] != 2 or data[f"{component}_sha"] != current[f"{component}_sha"]:
                raise ValueError("Reused component differs from the server baseline")
    if not data["backend_changed"] and data["image"] != current["image"]:
        raise ValueError("Frontend-only deployment may not change the backend image")
    return current


def write_atomic(path: Path, content: str, mode: int = 0o600) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w") as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"$pbkdf2-sha256$600000${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def prepare_certificate(certificate_dir: Path) -> None:
    # 沿用已签发的 IP 证书；只修正仍指向已卸载宝塔目录的 HTTP-01 校验路径。
    Path("/var/www/letsencrypt/.well-known/acme-challenge").mkdir(parents=True, exist_ok=True)
    renewal = Path("/etc/letsencrypt/renewal") / f"{certificate_dir.name}.conf"
    if renewal.exists():
        original = renewal.read_text()
        if "/www/server/nginx/html" in original:
            backup = ROOT / "backups" / "certificate-renewal.before-ci.conf"
            if not backup.exists():
                write_atomic(backup, original)
            write_atomic(renewal, original.replace("/www/server/nginx/html", "/var/www/letsencrypt"))
    hook = Path("/etc/letsencrypt/renewal-hooks/deploy/fastapiadmin-nginx")
    hook.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(hook, "#!/bin/sh\n/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx\n", 0o755)


def bootstrap(host: str, certificate: str, seed: str) -> None:
    ipaddress.IPv4Address(host)
    certificate_dir = Path(certificate)
    if certificate_dir.parent != Path("/etc/letsencrypt/live"):
        raise ValueError("Certificate must be a lineage directory under /etc/letsencrypt/live")
    for name in ("fullchain.pem", "privkey.pem"):
        if not (certificate_dir / name).is_file():
            raise ValueError(f"Certificate file missing: {name}")
    ROOT.mkdir(mode=0o755, exist_ok=True)
    SHARED.mkdir(mode=0o700, exist_ok=True)
    SHARED.chmod(0o700)
    for name in ("incoming", "releases", "backups"):
        (ROOT / name).mkdir(mode=0o755 if name == "releases" else 0o700, exist_ok=True)
    required = ("server.env", "deployment.json", "sys_user.initial.json", "credentials.txt")
    existing = [(SHARED / name).exists() for name in required]
    if any(existing):
        if not all(existing):
            raise RuntimeError("Partial initialization found; refusing to replace existing secrets")
        settings = json.loads((SHARED / "deployment.json").read_text())
        if settings != {"host": host, "certificate_dir": str(certificate_dir)}:
            raise RuntimeError("Existing deployment settings differ; explicit administrator review required")
        prepare_certificate(certificate_dir)
        print("Existing credentials retained; no passwords rotated.")
        return
    if (SHARED / "mysql").exists() and any((SHARED / "mysql").iterdir()):
        raise RuntimeError("Database data already exists; refusing fresh initialization")
    for name in ("mysql", "redis", "uploads", "files"):
        directory = SHARED / name
        directory.mkdir(exist_ok=True)
        if name in ("uploads", "files"):
            os.chown(directory, 1000, 1000)
    values = {
        "APP_ROOT": str(ROOT), "PUBLIC_HOST": host,
        "MYSQL_DATABASE": "fastapiadmin", "MYSQL_USER": "fastapiadmin",
        "MYSQL_ROOT_PASSWORD": secrets.token_urlsafe(32), "MYSQL_PASSWORD": secrets.token_urlsafe(32),
        "REDIS_PASSWORD": secrets.token_urlsafe(32), "SECRET_KEY": secrets.token_hex(32),
        "DATA_ENCRYPTION_KEY": secrets.token_hex(32), "DEPLOY_ENV": "prod",
        "DEMO_ENABLE": "false", "ALLOW_LOCALHOST_HOSTS": "false", "LOGGER_LEVEL": "INFO",
        "ALLOWED_HOSTS": json.dumps([host]), "OAUTH_ALLOWED_HOSTS": json.dumps([host]),
        "PROD_CORS_ORIGINS": f"https://{host}", "SCHEDULER_ALLOW_CODE_EXEC": "false",
    }
    # dotenv 的 JSON 数组需要保留内部双引号；绝不能用 shell source 读取本文件。
    env_content = "".join(f"{key}='{value}'\n" for key, value in values.items())
    users = json.loads(Path(seed).read_text())
    administrator_password = secrets.token_urlsafe(24)
    for user in users:
        enabled = user["username"] == "super"
        user["password"] = password_hash(administrator_password if enabled else secrets.token_urlsafe(32))
        user["status"] = 0 if enabled else 1
        user["avatar"] = "/api/v1/static/image/avatar.png"
    write_atomic(SHARED / "server.env", env_content)
    write_atomic(SHARED / "sys_user.initial.json", json.dumps(users, ensure_ascii=False))
    os.chown(SHARED / "sys_user.initial.json", 1000, 1000)
    write_atomic(SHARED / "credentials.txt", f"URL: https://{host}/web/\nUsername: super\nInitial password: {administrator_password}\n")
    write_atomic(SHARED / "deployment.json", json.dumps({"host": host, "certificate_dir": str(certificate_dir)}))
    prepare_certificate(certificate_dir)
    print("Initialized independent server secrets. Initial login is in /opt/fastapiadmin/shared/credentials.txt (root only).")


def settings() -> dict:
    return json.loads((SHARED / "deployment.json").read_text())


def receive(sha: str) -> None:
    incoming = ROOT / "incoming"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{sha}-", dir=incoming)
    count = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            while block := sys.stdin.buffer.read(1024 * 1024):
                count += len(block)
                if count > 1024**3:
                    raise ValueError("Release bundle exceeds 1 GiB")
                output.write(block)
        if count < 1024:
            raise ValueError("Empty or incomplete bundle")
        os.replace(temporary, incoming / f"{sha}.tar.gz")
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f"Received release {sha}: {count} bytes")


def extract_release(sha: str) -> Path:
    release = RELEASES / sha
    if release.exists():
        if release.is_symlink() or manifest(release)["sha"] != sha:
            raise ValueError("Existing release is not valid")
        return release
    stage = Path(tempfile.mkdtemp(prefix=f".{sha}-", dir=RELEASES))
    try:
        with tarfile.open(ROOT / "incoming" / f"{sha}.tar.gz", "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > 20_000 or sum(member.size for member in members) > 3 * 1024**3:
                raise ValueError("Archive limits exceeded")
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError("Unsafe archive member")
                if path.parts and path.parts[0] not in {"web", "docker", "release.json", "backend-image.tar"}:
                    raise ValueError("Unexpected archive root")
            for member in members:
                archive.extract(member, stage)
        # Validate before staging the release under its final name. No files are activated here.
        metadata = manifest(stage, sha)
        if metadata.get("format") == 2:
            if (stage / "backend-image.tar").exists():
                raise ValueError("Registry releases must not contain a backend image archive")
            if not metadata.get("frontend_changed"):
                if (stage / "web").exists():
                    raise ValueError("Backend-only bundle must not replace the frontend")
                previous = baseline()
                if metadata.get("base_sha") != previous["sha"] or metadata.get("frontend_sha") != previous.get("frontend_sha"):
                    raise ValueError("Cannot reuse a different frontend baseline")
                shutil.copytree(RELEASES / previous["sha"] / "web", stage / "web")
            version = {"sha": sha, "frontend_sha": metadata.get("frontend_sha"), "backend_sha": metadata.get("backend_sha")}
            if metadata.get("frontend_changed") and json.loads((stage / "web/version.json").read_text()) != version:
                raise ValueError("Checked frontend version mismatch")
            (stage / "web/version.json").write_text(json.dumps(version))
        elif json.loads((stage / "web/version.json").read_text())["sha"] != sha:
            raise ValueError("Frontend commit differs from backend commit")
        for required in ("web/index.html", "docker/docker-compose.yaml", "docker/docker-compose.ci.yaml", "docker/nginx/host-ci.conf.template", "docker/redis/conf/redis.conf"):
            if not (stage / required).is_file():
                raise ValueError(f"Release file missing: {required}")
        # tar 不携带服务器文件权限策略；前端目录必须能被 www-data 遍历。
        for directory, _, files in os.walk(stage):
            Path(directory).chmod(0o755)
            for name in files:
                (Path(directory) / name).chmod(0o644)
        stage.rename(release)
        try:
            manifest(release)
        except Exception:
            release.rename(stage)
            raise
        return release
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def compose(release: Path, *arguments: str) -> list[str]:
    return ["docker", "compose", "--env-file", str(SHARED / "server.env"),
            "-f", str(release / "docker/docker-compose.yaml"),
            "-f", str(release / "docker/docker-compose.ci.yaml"), "-p", "fastapiadmin", *arguments]


def run(command: list[str], log, sha: str, timeout: int = 600) -> None:
    environment = release_environment(sha)
    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, env=environment, timeout=timeout)


def health(url: str, host: str) -> dict:
    request = urllib.request.Request(url, headers={"Host": host, "X-Forwarded-Proto": "https"})
    # 公网 HTTPS 必须正常验证证书；不使用 -k / 不关闭证书校验。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=15) as response:
        result = json.load(response)
    if not result.get("success") or result["data"]["db_status"] != 1 or result["data"]["redis_status"] != 1:
        raise RuntimeError("Database / Redis health check failed")
    return result


def snapshot(release: Path, sha: str, destination: Path, log) -> None:
    dump = compose(release, "exec", "-T", "mysql", "sh", "-c",
                   'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --single-transaction --routines --triggers --events --hex-blob --no-tablespaces --set-gtid-purged=OFF --databases "$MYSQL_DATABASE"')
    with subprocess.Popen(dump, stdout=subprocess.PIPE, stderr=log,
                          env=release_environment(sha)) as process:
        with gzip.open(destination / "mysql.sql.gz", "wb") as output:
            shutil.copyfileobj(process.stdout, output)
        if process.wait(timeout=180) != 0:
            raise RuntimeError("Database backup failed; deployment stopped before migration")
    with gzip.open(destination / "mysql.sql.gz", "rb") as check:
        while check.read(1024 * 1024):
            pass
    with tarfile.open(destination / "files.tar.gz", "w:gz") as archive:
        archive.add(SHARED / "uploads", arcname="uploads")
        archive.add(SHARED / "files", arcname="files")
    shutil.copy2(SHARED / "server.env", destination / "server.env")
    if (ROOT / "current").is_symlink():
        write_atomic(destination / "previous-release.txt", str((ROOT / "current").resolve()) + "\n")


def switch_link(name: str, release: Path) -> None:
    temporary = ROOT / f".{name}-{secrets.token_hex(6)}"
    temporary.symlink_to(release)
    os.replace(temporary, ROOT / name)


def pull_image(data: dict, log) -> None:
    """Use this Actions job's ephemeral read token, never a stored PAT or shell argument."""
    raw = sys.stdin.buffer.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("Registry credential envelope too large")
    credentials = json.loads(raw)
    username, token = credentials.get("username", ""), credentials.get("token", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\[\]-]{0,99}", username) or not isinstance(token, str) or not token or "\n" in token:
        raise ValueError("Invalid short-lived registry credentials")
    with tempfile.TemporaryDirectory(prefix=".registry-", dir=SHARED) as temporary:
        # TemporaryDirectory is 0700; credentials are removed on both success and failure.
        config = Path(temporary)
        subprocess.run(["docker", "--config", str(config), "login", "ghcr.io", "-u", username, "--password-stdin"],
                       input=token.encode(), stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        (config / "config.json").chmod(0o600)
        print(f'Pulling immutable backend image {data["image"]} (existing layers are reused)...', flush=True)
        run(["docker", "--config", str(config), "pull", data["image"]], log, data["sha"], timeout=900)


def activate(release: Path, destination: Path, log, sha: str) -> None:
    config = Path("/etc/nginx/sites-available/fastapiadmin-ci")
    enabled = Path("/etc/nginx/sites-enabled/fastapiadmin-ci")
    previous = (ROOT / "current").resolve() if (ROOT / "current").is_symlink() else None
    original_config = config.read_text() if config.exists() else None
    previously_enabled = enabled.is_symlink()
    metadata = settings()
    content = (release / "docker/nginx/host-ci.conf.template").read_text()
    content = content.replace("__PUBLIC_HOST__", metadata["host"]).replace("__CERTIFICATE_DIR__", metadata["certificate_dir"])
    config_changed = original_config != content or not previously_enabled
    if original_config is not None:
        write_atomic(destination / "nginx.before.conf", original_config)
    try:
        switch_link("current", release)
        if config_changed:
            write_atomic(config, content, 0o644)
            if not enabled.exists():
                enabled.symlink_to(config)
            run(["nginx", "-t"], log, sha)
            run(["systemctl", "reload", "nginx"], log, sha)
        health(f'https://{metadata["host"]}/api/v1/monitor/health/check', metadata["host"])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'https://{metadata["host"]}/web/version.json', timeout=15) as response:
            if json.load(response)["sha"] != sha:
                raise RuntimeError("Public frontend version mismatch")
        running_image_matches(manifest(release))
        if previous and previous != release:
            switch_link("previous", previous)
    except Exception:
        if previous:
            switch_link("current", previous)
        else:
            (ROOT / "current").unlink(missing_ok=True)
        if config_changed:
            if original_config is None:
                config.unlink(missing_ok=True)
            else:
                write_atomic(config, original_config, 0o644)
            if not previously_enabled:
                enabled.unlink(missing_ok=True)
            run(["nginx", "-t"], log, sha)
            run(["systemctl", "reload", "nginx"], log, sha)
        raise


def prune_releases(current: Path) -> None:
    # 仅清理本项目完整 SHA 命名的旧发布；不调用全局 docker prune，不删任何数据卷。
    releases = sorted((path for path in RELEASES.iterdir() if SHA_PATTERN.fullmatch(path.name) and path.is_dir() and not path.is_symlink()),
                      key=lambda path: path.stat().st_mtime, reverse=True)
    protected = {current, *(path.resolve() for path in (ROOT / "current", ROOT / "previous") if path.is_symlink())}
    removable = [release for release in releases[3:] if release not in protected]
    # Several frontend releases may reuse one image. Never remove a retained release's image.
    retained_images = {manifest(release)["image"] for release in releases if release not in removable}
    for release in removable:
        image = manifest(release)["image"]
        used = subprocess.check_output(["docker", "ps", "-aq", "--filter", f"ancestor={image}"], text=True).strip()
        if not used and image not in retained_images:
            subprocess.run(["docker", "image", "rm", image], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(release)
    backups = sorted((path for path in (ROOT / "backups").iterdir()
                      if re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{12}-[0-9a-f]{6}", path.name) and path.is_dir() and not path.is_symlink()),
                     key=lambda path: path.name, reverse=True)
    # A run of frontend-only publishes must not evict the last database backups.
    for database_backup in (True, False):
        group = [path for path in backups if (path / "mysql.sql.gz").exists() == database_backup]
        for backup in group[5:]:
            shutil.rmtree(backup)


def deploy(sha: str) -> None:
    if (ROOT / "current").is_symlink() and (ROOT / "current").resolve().name == sha:
        if baseline()["sha"] == sha:
            (ROOT / "incoming" / f"{sha}.tar.gz").unlink(missing_ok=True)
            print(f"Already active and healthy: {sha}", flush=True)
            return
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise RuntimeError("Less than 2 GiB free disk space; refusing deployment")
    release = extract_release(sha)
    data = manifest(release)
    if data["format"] == 2:
        validate_baseline(data)
    backend_changed = data["backend_changed"]
    if not backend_changed:
        previous_release = RELEASES / data["base_sha"]
        # Frontend-only mode cannot silently change DB / backend runtime settings.
        for relative in ("docker/docker-compose.yaml", "docker/docker-compose.ci.yaml", "docker/redis/conf/redis.conf"):
            if (release / relative).read_bytes() != (previous_release / relative).read_bytes():
                raise ValueError("Runtime configuration changed; a backend deployment is required")
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / "backups" / f"{timestamp}-{sha[:12]}-{secrets.token_hex(3)}"
    destination.mkdir(mode=0o700)
    old_release = (ROOT / "current").resolve() if (ROOT / "current").is_symlink() else None
    migration_started = False
    backend_stopped = False
    with (destination / "deploy.log").open("w") as log:
        try:
            image_file = release / "backend-image.tar"
            if data["format"] == 2 and backend_changed:
                pull_image(data, log)
            elif image_file.exists():
                print("Loading backend image...", flush=True)
                run(["docker", "load", "-i", str(image_file)], log, sha)
                image_file.unlink()
            run(["docker", "image", "inspect", data["image"]], log, sha)
            run(compose(release, "config", "--quiet"), log, sha)
            if backend_changed and old_release:
                print("Stopping only this application's backend for a consistent backup...", flush=True)
                run(compose(old_release, "stop", "backend"), log, old_release.name)
                backend_stopped = True
            if backend_changed:
                print("Starting database dependencies and saving a pre-migration backup...", flush=True)
                run(compose(release, "up", "-d", "--no-build", "--wait", "--wait-timeout", "240", "mysql", "redis"), log, sha)
                snapshot(release, sha, destination, log)
                migration_started = True
                print("Applying the application's existing database initialization/migration logic...", flush=True)
                code = "import asyncio; from app.scripts.initialize import InitializeData; asyncio.run(InitializeData().init_db())"
                run(compose(release, "run", "--rm", "--no-deps", "backend", "python", "-c", code), log, sha)
                print("Starting the checked backend image...", flush=True)
                run(compose(release, "up", "-d", "--no-build", "--no-deps", "--pull", "never", "--wait", "--wait-timeout", "240", "backend"), log, sha)
            else:
                print("Frontend-only release: keeping backend, MySQL and Redis running; no migration or database snapshot.", flush=True)
            health("http://127.0.0.1:8001/api/v1/monitor/health/check", settings()["host"])
            print("Switching frontend release and checking public HTTPS...", flush=True)
            activate(release, destination, log, sha)
        except Exception:
            if backend_stopped and not migration_started and old_release:
                run(compose(old_release, "up", "-d", "--no-build", "--no-deps", "backend"), log, old_release.name)
            print(f"Deployment FAILED. Private diagnostic log / backups: {destination}", flush=True)
            if migration_started:
                print("Database migration may have run. No automatic database restore or unverified old-image rollback was attempted.", flush=True)
            raise
    (ROOT / "incoming" / f"{sha}.tar.gz").unlink(missing_ok=True)
    try:
        prune_releases(release)
    except Exception as error:
        print(f"Release is healthy; old-artifact cleanup needs administrator review ({type(error).__name__}).")
    write_atomic(SHARED / "last-success.json", json.dumps({"sha": sha, "frontend_sha": data["frontend_sha"],
                 "backend_sha": data["backend_sha"], "image": data["image"], "time": timestamp, "backup": str(destination)}))
    print(f'Deployed {sha}: https://{settings()["host"]}/web/', flush=True)


def main() -> None:
    if os.geteuid() != 0:
        raise PermissionError("This restricted deployment entry must run as root")
    original = os.environ.get("SSH_ORIGINAL_COMMAND")
    if original is None and len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        parser = argparse.ArgumentParser()
        parser.add_argument("action")
        parser.add_argument("--host", required=True)
        parser.add_argument("--certificate", required=True)
        parser.add_argument("--seed", required=True)
        arguments = parser.parse_args()
        bootstrap(arguments.host, arguments.certificate, arguments.seed)
        return
    arguments = shlex.split(original) if original is not None else sys.argv[1:]
    if len(arguments) != 2 or arguments[0] not in {"baseline", "receive", "deploy", "status"} or not SHA_PATTERN.fullmatch(arguments[1]):
        raise ValueError("Only baseline/receive/deploy/status followed by a full lowercase Git SHA are allowed")
    action, sha = arguments
    with (SHARED / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == "baseline":
            print(json.dumps(baseline()))
        elif action == "receive":
            receive(sha)
        elif action == "deploy":
            deploy(sha)
        else:
            if not (ROOT / "current").is_symlink() or (ROOT / "current").resolve().name != sha:
                raise RuntimeError("Active release does not match the requested commit")
            health(f'https://{settings()["host"]}/api/v1/monitor/health/check', settings()["host"])
            running_image_matches(manifest((ROOT / "current").resolve()))
            print(f"Active and healthy: {sha}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # 不向 GitHub 打印环境变量、数据库口令或应用日志；详细信息在 root-only 日志。
        print(f"Deployment command failed ({type(error).__name__}): {error}", file=sys.stderr)
        sys.exit(1)
