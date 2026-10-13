"""Manage the dedicated Lima VM and official Piston service (never host-execute code)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse, urlunparse

import requests
import yaml

PROJECT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("ALGOMENTOR_EXECUTION_ROOT", Path.home() / ".local/share/algomentor-execution")).expanduser().resolve()
STATE = ROOT / "state"
LIMACTL = Path(os.environ.get("ALGOMENTOR_LIMACTL", ROOT / "lima/bin/limactl")).expanduser().resolve()
VM = "algomentor-exec"
CONTAINER = "algomentor-piston"
LABEL = "org.algomentor.execution=isolated-piston"
CONFIG = PROJECT / "deployment/lima-piston.yaml"
CACHE = Path.home() / ".cache/algomentor-execution"
API = "http://127.0.0.1:2000/api/v2"
IMAGE = "ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a"
CONTAINER_LIMITS = {
    "PISTON_REPO_URL": "http://192.168.5.2:2099/index",
    "PISTON_DISABLE_NETWORKING": "true",
    "PISTON_RUN_TIMEOUT": "3000",
    "PISTON_RUN_CPU_TIME": "3000",
    "PISTON_COMPILE_TIMEOUT": "3000",
    "PISTON_COMPILE_CPU_TIME": "3000",
    "PISTON_RUN_MEMORY_LIMIT": "268435456",
    "PISTON_COMPILE_MEMORY_LIMIT": "268435456",
    "PISTON_OUTPUT_MAX_SIZE": "8192",
    "PISTON_MAX_PROCESS_COUNT": "16",
    "PISTON_MAX_CONCURRENT_JOBS": "4",
    "PISTON_MAX_FILE_SIZE": "10485760",
}


def environment() -> dict[str, str]:
    # No Django, encryption, DeepSeek or arbitrary shell environment is propagated.
    permitted = {"HOME", "PATH", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE"}
    result = {key: value for key, value in os.environ.items() if key in permitted}
    result["LIMA_HOME"] = str(STATE)
    return result


def run(arguments: list[str], *, capture: bool = False, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess:
    if not LIMACTL.is_file():
        raise RuntimeError("Lima 未安装；先运行 .venv/bin/python scripts/install_lima_runtime.py。")
    return subprocess.run(
        [str(LIMACTL), *arguments], cwd=PROJECT, env=environment(),
        text=True, capture_output=capture, check=check, timeout=timeout,
    )


def docker(*arguments: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    return run(["shell", "--workdir=/", VM, "sudo", "docker", *arguments], capture=capture, check=check)


def check_config(path: Path) -> None:
    configuration = yaml.safe_load(path.read_text())
    if configuration.get("mounts") or configuration.get("env"):
        raise RuntimeError("拒绝使用共享主机目录或额外环境变量的执行 VM。")
    ssh = configuration.get("ssh", {})
    if any(ssh.get(key) for key in ("forwardAgent", "forwardX11", "loadDotSSHPubKeys")):
        raise RuntimeError("拒绝向执行 VM 共享 SSH 凭据或代理。")
    rules = configuration.get("portForwards", [])
    if not any(rule.get("ignore") and rule.get("guestIP") == "0.0.0.0" for rule in rules):
        raise RuntimeError("执行 VM 必须关闭自动转发其他端口。")
    for rule in rules:
        if not rule.get("ignore") and (
            rule.get("guestPort") != 2000 or rule.get("hostPort") != 2000
            or rule.get("hostIP") != "127.0.0.1" or rule.get("guestIP") != "127.0.0.1"
        ):
            raise RuntimeError("执行 VM 只能向本机回环地址转发 Piston 2000 端口。")


def check_state() -> None:
    for name in ("default.yaml", "override.yaml", "base.yaml"):
        if (STATE / "_config" / name).exists():
            raise RuntimeError("独立 Lima 状态目录出现全局配置，请先核查其挂载与转发设置：" + name)
    check_config(CONFIG)
    actual = STATE / VM / "lima.yaml"
    if actual.exists():
        check_config(actual)


def ensure_cached_image() -> Path:
    """Use native Python DNS/downloads; Lima's Go DNS may fail on macOS networks."""
    configuration = yaml.safe_load(CONFIG.read_text())
    image = configuration["images"][0]
    url = image["location"]
    expected = image["digest"].removeprefix("sha256:")
    if not url.startswith("https://cloud-images.ubuntu.com/") or len(expected) != 64:
        raise RuntimeError("执行 VM 镜像必须使用已核对的 Ubuntu 官方 HTTPS 地址与 SHA-256。")
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    cached = CACHE / "ubuntu-24.04-server-cloudimg-arm64.img"

    def verified(path: Path) -> bool:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest() == expected

    if cached.exists():
        if not verified(cached):
            raise RuntimeError("缓存的 Ubuntu 镜像摘要不匹配；请核查缓存后重试，不会使用未验证文件。")
    else:
        temporary = cached.with_suffix(cached.suffix + ".part")
        print("下载固定 Ubuntu 官方镜像（约 592 MiB）", flush=True)
        with requests.Session() as session:
            session.trust_env = False
            with session.get(url, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                downloaded = 0
                reported = 0
                with temporary.open("wb") as stream:
                    for block in response.iter_content(1024 * 1024):
                        stream.write(block)
                        downloaded += len(block)
                        if downloaded - reported >= 16 * 1024 * 1024:
                            print(f"Ubuntu 镜像：{downloaded // (1024 * 1024)} MiB", flush=True)
                            reported = downloaded
        if not verified(temporary):
            raise RuntimeError("Ubuntu 镜像下载后摘要验证失败；不会启动该镜像。")
        temporary.replace(cached)
    # This is a boot-image import, not a host filesystem mount into the VM.
    configuration["images"][0]["location"] = str(cached)
    proxy = download_proxy()
    if proxy:
        # Only anonymous download routing is added; no host environment is shared.
        for provision in configuration.get("provision", []):
            script = provision.get("script", "")
            provision["script"] = script.replace(
                "set -eu -o pipefail\n",
                "set -eu -o pipefail\nexport http_proxy=" + shlex.quote(proxy)
                + "\nexport https_proxy=" + shlex.quote(proxy) + "\nexport no_proxy=127.0.0.1,localhost\n",
                1,
            )
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime_config = STATE / "runtimeconfig.yaml"
    runtime_config.write_text(yaml.safe_dump(configuration, allow_unicode=True, sort_keys=False))
    runtime_config.chmod(0o600)
    check_config(runtime_config)
    print("Ubuntu 镜像 SHA-256 已验证", flush=True)
    return runtime_config


def inspect_container() -> dict | None:
    response = docker("inspect", CONTAINER, capture=True, check=False)
    if response.returncode:
        if "no such" in response.stderr.lower() or "not found" in response.stderr.lower():
            return None
        raise RuntimeError("无法查询隔离容器；请检查 VM 是否启动。")
    result = json.loads(response.stdout)
    container = result[0]
    if container.get("Config", {}).get("Labels", {}).get("org.algomentor.execution") != "isolated-piston":
        raise RuntimeError("同名容器不属于 AlgoMentor，停止操作。")
    if container.get("Config", {}).get("Image") != IMAGE:
        raise RuntimeError("执行容器使用的镜像与固定官方摘要不一致，停止操作。")
    mounts = container.get("Mounts", [])
    allowed_mounts = {("volume", "/piston/packages"), ("tmpfs", "/tmp")}
    if any((mount.get("Type"), mount.get("Destination")) not in allowed_mounts for mount in mounts):
        raise RuntimeError("执行容器存在非预期文件挂载，停止操作。")
    host_config = container.get("HostConfig", {})
    if not host_config.get("Privileged") or host_config.get("Memory") != 1536 * 1024 * 1024 or host_config.get("PidsLimit") != 128:
        raise RuntimeError("执行容器与官方 Isolate 权限及外层资源限制不一致，停止操作。")
    if set(host_config.get("Tmpfs") or {}) != {"/tmp"}:
        raise RuntimeError("执行容器临时目录必须使用独立 tmpfs，停止操作。")
    ports = host_config.get("PortBindings", {})
    if ports != {"2000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "2000"}]}:
        raise RuntimeError("执行容器端口必须仅绑定 VM 回环地址，停止操作。")
    config_env = dict(value.split("=", 1) for value in container.get("Config", {}).get("Env", []) if "=" in value)
    if any(config_env.get(key) != value for key, value in CONTAINER_LIMITS.items()):
        raise RuntimeError("执行容器缺少固定的网络或资源限制，停止操作。")
    allowed_env = set(CONTAINER_LIMITS) | {"PATH", "NODE_VERSION", "YARN_VERSION", "DEBIAN_FRONTEND"}
    if set(config_env) - allowed_env:
        raise RuntimeError("执行容器存在非预期环境变量，停止操作。")
    return container


def request(method: str, path: str, *, payload=None, timeout: int = 15):
    # Fixed loopback endpoint, no redirects or ambient proxy/credentials.
    with requests.Session() as session:
        session.trust_env = False
        response = session.request(method, API + path, json=payload, timeout=(3, timeout), allow_redirects=False)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"本地 Piston 返回 HTTP {response.status_code}。")
    if len(response.content) > 524288:
        raise RuntimeError("本地 Piston 响应超过管理命令读取上限。")
    return response.json()


def wait_api() -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            request("GET", "/runtimes")
            return
        except (requests.RequestException, RuntimeError):
            time.sleep(1)
    raise RuntimeError("本地 Piston 启动后仍不可达；检查 VM 或容器日志。")


def prepare_package_cache() -> None:
    from piston_package_mirror import INDEX

    def ready() -> bool:
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get("http://127.0.0.1:2099/index", timeout=(1, 2), allow_redirects=False)
            if response.status_code != 200 or response.content != INDEX:
                raise RuntimeError("2099 端口已有非预期服务；不会用它安装运行时。")
            return True
        except requests.ConnectionError:
            return False

    if ready():
        return
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / "package-mirror.log").open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", str(PROJECT / "scripts/piston_package_mirror.py")],
            cwd=PROJECT, env=environment(), stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True,
        )
    (ROOT / "package-mirror.pid").write_text(str(process.pid))
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if ready():
            return
        if process.poll() is not None:
            raise RuntimeError("官方包缓存启动失败；查看本机 package-mirror.log。")
        time.sleep(1)
    raise RuntimeError("官方包缓存未能及时启动；不会安装未验证运行时。")


def download_proxy() -> str | None:
    proxy = requests.utils.get_environ_proxies("https://ghcr.io").get("https")
    if not proxy:
        return None
    parsed = urlparse(proxy)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise RuntimeError("自动配置仅支持无凭据 HTTP 下载代理。")
    if parsed.hostname in ("127.0.0.1", "localhost", "::1"):
        parsed = parsed._replace(netloc="192.168.5.2:" + str(parsed.port or 80))
    return urlunparse(parsed)


def prepare_download_proxy() -> None:
    proxy = download_proxy()
    if not proxy:
        return
    existing = run(["shell", "--workdir=/", VM, "sudo", "cat", "/etc/docker/daemon.json"], capture=True, check=False)
    configuration = json.loads(existing.stdout) if existing.returncode == 0 else {}
    proxies = {"http-proxy": proxy, "https-proxy": proxy, "no-proxy": "127.0.0.1,localhost"}
    if configuration.get("proxies") == proxies:
        return
    configuration["proxies"] = proxies
    subprocess.run(
        [str(LIMACTL), "shell", "--workdir=/", VM, "sudo", "tee", "/etc/docker/daemon.json"],
        cwd=PROJECT, env=environment(), input=json.dumps(configuration), text=True,
        stdout=subprocess.DEVNULL, check=True, timeout=30,
    )
    run(["shell", "--workdir=/", VM, "sudo", "systemctl", "restart", "docker"])


def start() -> None:
    check_state()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (STATE / VM / "lima.yaml").exists():
        run(["start", "--tty=false", VM])
    else:
        runtime_config = ensure_cached_image()
        run(["validate", str(runtime_config)])
        run(["start", "--name=" + VM, "--tty=false", str(runtime_config)])
    check_state()
    prepare_download_proxy()
    prepare_package_cache()
    info = docker("info", capture=True).stdout
    if "Cgroup Version: 2" not in info:
        raise RuntimeError("Piston 需要 cgroup v2，当前 Docker 配置不符合要求。")
    container = inspect_container()
    if container is None:
        arguments = [
            "run", "-d", "--name", CONTAINER, "--label", LABEL,
            "--platform", "linux/amd64", "--privileged", "--restart", "unless-stopped",
            "--memory", "1536m", "--pids-limit", "128",
            "--publish", "127.0.0.1:2000:2000",
            "--mount", "type=volume,source=algomentor-piston-packages,target=/piston/packages",
            "--tmpfs", "/tmp:exec,size=268435456",
            "--log-opt", "max-size=10m", "--log-opt", "max-file=2",
        ]
        for key, value in CONTAINER_LIMITS.items():
            arguments.extend(["--env", key + "=" + value])
        arguments.append(IMAGE)
        docker(*arguments)
    elif not container.get("State", {}).get("Running"):
        docker("start", CONTAINER)
    wait_api()
    print("隔离执行服务已启动：http://127.0.0.1:2000/api/v2")


def install_python() -> None:
    check_state()
    prepare_package_cache()
    if inspect_container() is None:
        raise RuntimeError("隔离容器尚未创建；先运行 start。")
    runtimes = request("GET", "/runtimes")
    python = [item for item in runtimes if item.get("language") == "python" and item.get("version", "").startswith("3.")]
    if not python:
        packages = request("GET", "/packages")
        candidates = [item for item in packages if item.get("language") == "python" and item.get("language_version", "").startswith("3.")]
        if not candidates:
            raise RuntimeError("官方 Piston 包仓库未提供 Python 3。")
        version = max((item["language_version"] for item in candidates), key=lambda value: tuple(int(part) for part in value.split(".")))
        print("通过官方 Piston packages API 安装 Python " + version, flush=True)
        request("POST", "/packages", payload={"language": "python", "version": version}, timeout=600)
        runtimes = request("GET", "/runtimes")
        python = [item for item in runtimes if item.get("language") == "python" and item.get("version", "").startswith("3.")]
    if not python:
        raise RuntimeError("Python 包安装后未出现在 runtimes，安装未验证。")
    print(json.dumps({"python_runtimes": [item["version"] for item in python]}, ensure_ascii=False))


def smoke() -> None:
    check_state()
    if inspect_container() is None:
        raise RuntimeError("隔离容器尚未创建。")
    response = request("POST", "/execute", payload={
        "language": "python", "version": "3.x", "files": [{"name": "main.py", "content": 'print("ALGOMENTOR_SANDBOX_OK")'}],
        "run_timeout": 2000, "run_cpu_time": 2000, "run_memory_limit": 134217728,
    })
    result = response.get("run", {})
    if result.get("code") != 0 or result.get("stdout", "").strip() != "ALGOMENTOR_SANDBOX_OK" or result.get("signal"):
        raise RuntimeError("隔离服务真实运行检查失败：" + json.dumps(result, ensure_ascii=False))
    print(json.dumps({"status": "verified", "provider": "piston", "version": response.get("version"), "run": result}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "install-python", "smoke", "logs"))
    arguments = parser.parse_args()
    try:
        if arguments.action == "start":
            start()
        elif arguments.action == "stop":
            check_state()
            run(["stop", VM])
        elif arguments.action == "status":
            check_state()
            run(["list", VM])
            print(json.dumps(request("GET", "/runtimes"), ensure_ascii=False))
        elif arguments.action == "install-python":
            install_python()
        elif arguments.action == "smoke":
            smoke()
        elif arguments.action == "logs":
            check_state()
            inspect_container()
            docker("logs", "--tail", "80", CONTAINER)
        return 0
    except (RuntimeError, requests.RequestException, subprocess.SubprocessError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
