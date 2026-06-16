"""
Doctor 命令用于 hermes CLI。

诊断 Hermes 智能体设置的问题。
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

from hermes_cli.config import get_project_root, get_hermes_home, get_env_path
from hermes_cli.env_loader import load_hermes_dotenv
from hermes_constants import display_hermes_home

PROJECT_ROOT = get_project_root()
HERMES_HOME = get_hermes_home()
_DHH = display_hermes_home()  # 面向用户的显示路径（例如 ~/.hermes 或 ~/.hermes/profiles/coder）

# 从 ~/.hermes/.env 加载环境变量，以便 API 密钥检查正常工作
_env_path = get_env_path()
load_hermes_dotenv(hermes_home=_env_path.parent, project_env=PROJECT_ROOT / ".env")

from hermes_cli.colors import Colors, color
from hermes_cli.models import _HERMES_USER_AGENT
from hermes_constants import OPENROUTER_MODELS_URL
from utils import base_url_host_matches


_PROVIDER_ENV_HINTS = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_TOKEN",
    "OPENAI_BASE_URL",
    "NOUS_API_KEY",
    "GLM_API_KEY",
    "ZAI_API_KEY",
    "Z_AI_API_KEY",
    "KIMI_API_KEY",
    "KIMI_CN_API_KEY",
    "GMI_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "KILOCODE_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "HF_TOKEN",
    "OPENCODE_ZEN_API_KEY",
    "OPENCODE_GO_API_KEY",
    "XIAOMI_API_KEY",
    "TOKENHUB_API_KEY",
)


from hermes_constants import is_termux as _is_termux


def _python_install_cmd() -> str:
    return "python -m pip install" if _is_termux() else "uv pip install"


def _system_package_install_cmd(pkg: str) -> str:
    if _is_termux():
        return f"pkg install {pkg}"
    if sys.platform == "darwin":
        return f"brew install {pkg}"
    return f"sudo apt install {pkg}"


def _safe_which(cmd: str) -> str | None:
    """shutil.which 包装器，对测试中的平台 monkeypatching 具有弹性。"""
    try:
        return shutil.which(cmd)
    except Exception:
        return None


def _termux_browser_setup_steps(node_installed: bool) -> list[str]:
    steps: list[str] = []
    step = 1
    if not node_installed:
        steps.append(f"{step}) pkg install nodejs")
        step += 1
    steps.append(f"{step}) npm install -g agent-browser")
    steps.append(f"{step + 1}) agent-browser install")
    return steps


def _termux_install_all_fallback_notes() -> list[str]:
    return [
        "Termux 安装配置集：使用 .[termux-all] 以获得最大兼容性（Termux 上安装程序默认值）。",
        "Termux 上排除了 Matrix E2EE 附加组件（python-olm 当前无法构建）。",
        "Termux 上排除了本地 faster-whisper 附加组件（ctranslate2/av 构建路径不可用）。",
        "STT 回退：使用 Groq Whisper（设置 GROQ_API_KEY）或 OpenAI Whisper（设置 VOICE_TOOLS_OPENAI_KEY）。",
    ]


def _has_provider_env_config(content: str) -> bool:
    """当 ~/.hermes/.env 包含提供商认证/基础 URL 设置时返回 True。"""
    return any(key in content for key in _PROVIDER_ENV_HINTS)


def _honcho_is_configured_for_doctor() -> bool:
    """当 Honcho 已配置时返回 True，即使此进程没有活动会话。"""
    try:
        from plugins.memory.honcho.client import HonchoClientConfig

        cfg = HonchoClientConfig.from_global_config()
        return bool(cfg.enabled and (cfg.api_key or cfg.base_url))
    except Exception:
        return False


def _is_kanban_worker_env_gate(item: dict) -> bool:
    """当 Kanban 仅因为这不是工作进程而不可用时返回 True。"""
    if item.get("name") != "kanban":
        return False
    if os.environ.get("HERMES_KANBAN_TASK"):
        return False

    tools = item.get("tools") or []
    return bool(tools) and all(str(tool).startswith("kanban_") for tool in tools)


def _doctor_tool_availability_detail(toolset: str) -> str:
    """对于需要上下文的工具集的医生状态可选的解释性后缀。"""
    if toolset == "kanban" and not os.environ.get("HERMES_KANBAN_TASK"):
        return "（运行时门控；仅对调度程序生成的工作进程加载）"
    return ""


def _apply_doctor_tool_availability_overrides(available: list[str], unavailable: list[dict]) -> tuple[list[str], list[dict]]:
    """为医生诊断调整运行时门控的工具可用性。"""
    updated_available = list(available)
    updated_unavailable = []
    for item in unavailable:
        name = item.get("name")
        if _is_kanban_worker_env_gate(item):
            if "kanban" not in updated_available:
                updated_available.append("kanban")
            continue
        if name == "honcho" and _honcho_is_configured_for_doctor():
            if "honcho" not in updated_available:
                updated_available.append("honcho")
            continue
        updated_unavailable.append(item)
    return updated_available, updated_unavailable


def _has_healthy_oauth_fallback_for_apikey_provider(provider_label: str) -> bool:
    """当直接 API 密钥探测失败是非阻塞时返回 True。

    某些提供商系列同时支持直接的 API 密钥路径和单独的
    OAuth 运行时路径。当 OAuth 路径已健康时，医生应
    仍然显示失败的 API 密钥连接行，但不应将该
    直接密钥问题提升到最终的阻塞摘要中。
    """
    normalized = (provider_label or "").strip().lower()
    if normalized in {"google / gemini", "gemini"}:
        try:
            from hermes_cli.auth import get_gemini_oauth_auth_status
            return bool((get_gemini_oauth_auth_status() or {}).get("logged_in"))
        except Exception:
            return False
    if normalized == "minimax":
        try:
            from hermes_cli.auth import get_minimax_oauth_auth_status
            return bool((get_minimax_oauth_auth_status() or {}).get("logged_in"))
        except Exception:
            return False
    if normalized == "xai":
        try:
            from hermes_cli.auth import get_xai_oauth_auth_status
            return bool((get_xai_oauth_auth_status() or {}).get("logged_in"))
        except Exception:
            return False
    return False


def check_ok(text: str, detail: str = ""):
    print(f"  {color('', Colors.GREEN)} {text}" + (f" {color(detail, Colors.DIM)}" if detail else ""))

def check_warn(text: str, detail: str = ""):
    print(f"  {color('', Colors.YELLOW)} {text}" + (f" {color(detail, Colors.DIM)}" if detail else ""))

def check_fail(text: str, detail: str = ""):
    print(f"  {color('', Colors.RED)} {text}" + (f" {color(detail, Colors.DIM)}" if detail else ""))

def check_info(text: str):
    print(f"    {color('→', Colors.CYAN)} {text}")


def _section(title: str) -> None:
    """打印医生部分横幅：空行 + 粗体青色  标题。"""
    print()
    print(color(f" {title}", Colors.CYAN, Colors.BOLD))


def _fail_and_issue(text: str, detail: str, fix: str, issues: list[str]) -> None:
    """发出 check_fail 并追加相应的修复说明。"""
    check_fail(text, detail)
    issues.append(fix)


def _read_pyproject_version() -> str | None:
    """从项目根目录的 ``pyproject.toml`` 读取 ``version = \"...\"``。

    从已安装的 wheel 运行时返回 None（pyproject.toml 不会随包一起发布），
    或者文件无法解析时返回 None。仅读取 ``[project]`` 版本，
    忽略其他表中出现的任何版本字符串。
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    in_project = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("version") and "=" in line:
            value = line.split("=", 1)[1]
            value = value.split("#", 1)[0].strip().strip("\"'")
            return value or None
    return None


def _check_version_consistency(issues: list[str]) -> None:
    """验证 pyproject.toml 版本与 hermes_cli.__version__ 一致。

    git 冲突解决（reset/merge）可能会还原一个文件而不还原另一个，
    导致 ``hermes --version`` 报告过时的版本而 ``pyproject.toml`` 是最新的。
    检测此漂移以便用户可以重新同步。对于已安装的 wheel（没有 pyproject.toml）静默无操作。
    """
    try:
        from hermes_cli import __version__ as init_version
    except Exception:
        return
    pyproject_version = _read_pyproject_version()
    if pyproject_version is None:
        return
    if pyproject_version == init_version:
        check_ok("版本文件一致", f"({init_version})")
    else:
        _fail_and_issue(
            "源文件之间的版本不匹配",
            f"(pyproject.toml {pyproject_version} != hermes_cli/__init__.py {init_version})",
            "重新同步版本文件（例如运行 'hermes update'，或将 "
            "hermes_cli/__init__.py 的 __version__ 设置为与 pyproject.toml 匹配）",
            issues,
        )


def _check_s6_supervision(issues: list[str]) -> None:
    """在容器中运行于我们的 s6 /init 下时，显示 s6 看到的内容。

    作为 :func:`_check_gateway_service_linger` 的对应检查运行，
    针对的是宿主机上的 systemd 情况。在 s6 容器之外的任何地方都是空操作，
    以免主机运行时充斥着不相关的输出。

    报告：
      - main-hermes 和 dashboard 静态服务是否正常运行
      - 注册了多少个按配置集的网关槽（通过
        ``S6ServiceManager.list_profile_gateways()``）以及有多少正在被
        监督为 ``up``
    """
    try:
        from hermes_cli.service_manager import (
            S6ServiceManager,
            detect_service_manager,
        )
    except Exception:
        return

    if detect_service_manager() != "s6":
        return

    _section("s6 监督")

    mgr = S6ServiceManager()

    # 静态服务。它们通过 s6-rc 符号链接位于 /run/service/ 下，
    # 因此相同的 s6-svstat 探测方法有效。
    for static in ("main-hermes", "dashboard"):
        if mgr.is_running(static):
            check_ok(f"{static}: 运行中")
        else:
            check_info(f"{static}: 已停止（如果未通过环境变量启用则为预期状态）")

    profiles = mgr.list_profile_gateways()
    if not profiles:
        check_info("尚未注册任何按配置集的网关 — 使用 `hermes profile create <name>` 创建")
        return

    up_count = sum(1 for p in profiles if mgr.is_running(f"gateway-{p}"))
    check_ok(
        f"按配置集的网关: {up_count}/{len(profiles)} 个受监督运行中"
        + (f" ({', '.join(sorted(profiles))})" if len(profiles) <= 8 else "")
    )


def check_certificates() -> None:
    """验证 certifi CA 包是否可加载。

    在用户遇到 SSLConfigurationError 的 traceback 墙之前，
    以用户友好的方式显示该错误。
    """
    try:
        from agent.ssl_guard import verify_ca_bundle_with_fallback
        from agent.errors import SSLConfigurationError
        verify_ca_bundle_with_fallback()
        check_ok("SSL CA 证书包有效")
    except SSLConfigurationError as e:
        check_fail("SSL CA 证书包已损坏", str(e))
    except Exception as e:
        check_warn("SSL 证书检查已跳过", str(e))


def _check_gateway_service_linger(issues: list[str]) -> None:
    """当 systemd 用户网关服务在注销后将停止时发出警告。

    在 s6 下运行的容器中跳过 — 驻留概念
    （用户 systemd 在 SSH 注销后继续运行）在此不适用，
    s6 监管状态由 ``_check_s6_supervision`` 单独显示。
    """
    try:
        from hermes_cli.gateway import (
            get_systemd_linger_status,
            get_systemd_unit_path,
            is_linux,
        )
        from hermes_cli.service_manager import detect_service_manager
    except Exception as e:
        check_warn("网关服务驻留", f"(无法导入网关辅助函数: {e})")
        return

    if not is_linux():
        return

    if detect_service_manager() == "s6":
        return

    unit_path = get_systemd_unit_path()
    if not unit_path.exists():
        return

    _section("网关服务")
    linger_enabled, linger_detail = get_systemd_linger_status()
    if linger_enabled is True:
        check_ok("Systemd 驻留已启用", "（网关服务在注销后继续运行）")
    elif linger_enabled is False:
        check_warn("Systemd 驻留已禁用", "（网关可能在注销后停止）")
        check_info("运行: sudo loginctl enable-linger $USER")
        issues.append("为用户网关服务启用驻留: sudo loginctl enable-linger $USER")
    else:
        check_warn("无法验证 systemd 驻留", f"({linger_detail})")


_APIKEY_PROVIDERS_CACHE: list | None = None


def _build_apikey_providers_list() -> list:
    """构建 API 密钥提供者健康检查列表并缓存一次。

    元组格式: (name, env_vars, default_url, base_env, supports_models_endpoint)
    基础列表通过任何尚未存在的 auth_type=\"api_key\" 的 ProviderProfile 进行增强 —
    添加 plugins/model-providers/<name>/ 就足以进入医生检查。
    """
    _static = [
        ("Z.AI / GLM",      ("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"), "https://api.z.ai/api/paas/v4/models", "GLM_BASE_URL", True),
        ("Kimi / Moonshot",  ("KIMI_API_KEY",),                              "https://api.moonshot.ai/v1/models",   "KIMI_BASE_URL", True),
        ("StepFun Step Plan", ("STEPFUN_API_KEY",),                          "https://api.stepfun.ai/step_plan/v1/models", "STEPFUN_BASE_URL", True),
        ("Kimi / Moonshot (中国)", ("KIMI_CN_API_KEY",),                    "https://api.moonshot.cn/v1/models",   None, True),
        ("Arcee AI",         ("ARCEEAI_API_KEY",),                           "https://api.arcee.ai/api/v1/models",  "ARCEE_BASE_URL", True),
        ("GMI Cloud",        ("GMI_API_KEY",),                               "https://api.gmi-serving.com/v1/models", "GMI_BASE_URL", True),
        ("DeepSeek",         ("DEEPSEEK_API_KEY",),                          "https://api.deepseek.com/v1/models",  "DEEPSEEK_BASE_URL", True),
        ("Hugging Face",     ("HF_TOKEN",),                                  "https://router.huggingface.co/v1/models", "HF_BASE_URL", True),
        ("NVIDIA NIM",       ("NVIDIA_API_KEY",),                            "https://integrate.api.nvidia.com/v1/models", "NVIDIA_BASE_URL", True),
        ("Alibaba/DashScope", ("DASHSCOPE_API_KEY",),                        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models", "DASHSCOPE_BASE_URL", True),
        ("MiniMax",          ("MINIMAX_API_KEY",),                           "https://api.minimax.io/v1/models",    "MINIMAX_BASE_URL", True),
        ("MiniMax (中国)",  ("MINIMAX_CN_API_KEY",),                        "https://api.minimaxi.com/v1/models",  "MINIMAX_CN_BASE_URL", False),
        ("Kilo Code",        ("KILOCODE_API_KEY",),                          "https://api.kilo.ai/api/gateway/models", "KILOCODE_BASE_URL", True),
        ("OpenCode Zen",     ("OPENCODE_ZEN_API_KEY",),                      "https://opencode.ai/zen/v1/models",  "OPENCODE_ZEN_BASE_URL", True),
        ("OpenCode Go",      ("OPENCODE_GO_API_KEY",),                       None,                                  "OPENCODE_GO_BASE_URL", False),
    ]
    _known_names = {t[0] for t in _static}
    _known_canonical: set[str] = set()
    _name_to_canonical = {
        "Z.AI / GLM": "zai", "Kimi / Moonshot": "kimi-coding",
        "StepFun Step Plan": "stepfun", "Kimi / Moonshot (中国)": "kimi-coding-cn",
        "Arcee AI": "arcee", "GMI Cloud": "gmi", "DeepSeek": "deepseek",
        "Hugging Face": "huggingface", "NVIDIA NIM": "nvidia",
        "Alibaba/DashScope": "alibaba", "MiniMax": "minimax",
        "MiniMax (中国)": "minimax-cn",
        "Kilo Code": "kilocode", "OpenCode Zen": "opencode-zen",
        "OpenCode Go": "opencode-go",
    }
    for _label, _canonical in _name_to_canonical.items():
        _known_canonical.add(_canonical)
    _dedicated_canonical = {"anthropic", "openrouter", "bedrock"}
    _known_canonical.update(_dedicated_canonical)
    try:
        from providers import list_providers
        from providers.base import ProviderProfile as _PP
        try:
            from hermes_cli.providers import normalize_provider as _normalize_provider
        except Exception:
            def _normalize_provider(_name: str) -> str:
                return (_name or "").strip().lower()
        for _pp in list_providers():
            if not isinstance(_pp, _PP) or _pp.auth_type != "api_key" or not _pp.env_vars:
                continue
            _label = _pp.display_name or _pp.name
            if _label in _known_names or _pp.name in _known_canonical:
                continue
            _candidates = {_normalize_provider(_pp.name)}
            for _alias in (_pp.aliases or ()):
                _candidates.add(_normalize_provider(_alias))
            if _candidates & _dedicated_canonical:
                continue
            _key_vars = tuple(
                v for v in _pp.env_vars
                if not v.endswith("_BASE_URL") and not v.endswith("_URL")
            )
            _base_var = next(
                (v for v in _pp.env_vars if v.endswith("_BASE_URL") or v.endswith("_URL")),
                None,
            )
            if not _key_vars:
                continue
            _models_url = (
                (_pp.models_url or (_pp.base_url.rstrip("/") + "/models"))
                if _pp.base_url else None
            )
            _hc = getattr(_pp, "supports_health_check", True)
            _static.append((_label, _key_vars, _models_url, _base_var, _hc))
    except Exception:
        pass
    return _static


def run_doctor(args):
    """运行诊断检查。"""
    should_fix = getattr(args, 'fix', False)
    ack_target = getattr(args, 'ack', None)

    os.environ.setdefault("HERMES_INTERACTIVE", "1")

    # 处理 `hermes doctor --ack <id>` 作为快速路径。
    if ack_target:
        from hermes_cli.security_advisories import (
            ADVISORIES,
            ack_advisory,
        )
        valid_ids = {a.id for a in ADVISORIES}
        if ack_target not in valid_ids:
            print(color(
                f"未知的咨询 ID: {ack_target!r}。已知 ID: "
                f"{', '.join(sorted(valid_ids)) or '(无)'}",
                Colors.RED,
            ))
            sys.exit(2)
        if ack_advisory(ack_target):
            print(color(
                f"   已确认咨询 {ack_target}。"
                f"它将不再触发启动横幅。",
                Colors.GREEN,
            ))
        else:
            print(color(
                f"   无法持久化 {ack_target} 的确认信息。"
                f"请检查 ~/.hermes/config.yaml 是否可写。",
                Colors.RED,
            ))
            sys.exit(1)
        return

    issues = []
    manual_issues = []  # 无法自动修复的问题
    fixed_count = 0

    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.CYAN))
    print(color("│                 🩺 Hermes 诊断工具                      │", Colors.CYAN))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.CYAN))

    _section("安全公告")
    try:
        from hermes_cli.security_advisories import (
            detect_compromised,
            filter_unacked,
            full_remediation_text,
            get_acked_ids,
        )
        all_hits = detect_compromised()
        fresh_hits = filter_unacked(all_hits)
        if fresh_hits:
            for hit in fresh_hits:
                check_fail(
                    f"{hit.advisory.title}",
                    f"({hit.package}=={hit.installed_version})",
                )
                for line in full_remediation_text(hit):
                    if line:
                        print(f"    {color(line, Colors.YELLOW)}")
                    else:
                        print()
                manual_issues.append(
                    f"解决安全公告 {hit.advisory.id}: "
                    f"卸载 {hit.package}=={hit.installed_version} 并 "
                    f"轮换凭据，然后运行 "
                    f"`hermes doctor --ack {hit.advisory.id}`。"
                )
            acked_ids = get_acked_ids()
            for h in all_hits:
                if h.advisory.id in acked_ids:
                    check_warn(
                        f"{h.package}=={h.installed_version} 仍然已安装 "
                        f"（咨询 {h.advisory.id} 已确认）",
                    )
        else:
            check_ok("没有活动的安全公告")
    except Exception as e:
        check_warn(f"安全检查失败: {e}")

    _section("MCP 服务器安全")
    try:
        from hermes_cli.config import load_config
        from hermes_cli.mcp_security import validate_mcp_server_entry

        servers = load_config().get("mcp_servers") or {}
        suspicious = 0
        if isinstance(servers, dict):
            for name, entry in sorted(servers.items()):
                if not isinstance(entry, dict):
                    continue
                issues_found = validate_mcp_server_entry(name, entry)
                if not issues_found:
                    continue
                suspicious += 1
                check_warn(f"MCP 服务器 '{name}' 有可疑的 stdio 命令", "; ".join(issues_found))
                manual_issues.append(
                    f"审查/移除 config.yaml 中的 mcp_servers.{name}；轮换任何可能已暴露的凭据。"
                )
        if suspicious == 0:
            check_ok("没有可疑的 MCP stdio 命令")
    except Exception as e:
        check_warn(f"MCP 安全检查失败: {e}")
    
    _section("Python 环境")
    py_version = sys.version_info
    if py_version >= (3, 11):
        check_ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    elif py_version >= (3, 10):
        check_ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
        check_warn("建议使用 Python 3.11+ 以获得 RL 训练工具（tinker 需要 >= 3.11）")
    elif py_version >= (3, 8):
        check_warn(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}", "（建议 3.10+）")
    else:
        _fail_and_issue(
            f"Python {py_version.major}.{py_version.minor}.{py_version.micro}",
            "（需要 3.10+）",
            "升级 Python 到 3.10+",
            issues,
        )
    
    # 检查是否在虚拟环境中
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        check_ok("虚拟环境已激活")
    else:
        check_warn("未在虚拟环境中", "（推荐）")

    _check_version_consistency(issues)

    _section("SSL / CA 证书")
    check_certificates()

    _section("必需的包")
    required_packages = [
        ("openai", "OpenAI SDK"),
        ("rich", "Rich (终端 UI)"),
        ("dotenv", "python-dotenv"),
        ("yaml", "PyYAML"),
        ("httpx", "HTTPX"),
    ]
    
    optional_packages = [
        ("croniter", "Croniter (cron 表达式)"),
        ("telegram", "python-telegram-bot"),
        ("discord", "discord.py"),
    ]
    
    for module, name in required_packages:
        try:
            __import__(module)
            check_ok(name)
        except ImportError:
            _fail_and_issue(name, "（缺失）", f"安装 {name}: {_python_install_cmd()} {module}", issues)
    
    for module, name in optional_packages:
        try:
            __import__(module)
            check_ok(name, "（可选）")
        except ImportError:
            check_warn(name, "（可选，未安装）")
    
    _section("配置文件")
    env_path = HERMES_HOME / '.env'
    if env_path.exists():
        check_ok(f"{_DHH}/.env 文件存在")
        
        content = env_path.read_text(encoding="utf-8")
        if _has_provider_env_config(content):
            check_ok("已配置 API 密钥或自定义端点")
        else:
            check_warn(f"在 {_DHH}/.env 中未找到 API 密钥")
            issues.append("运行 'hermes setup' 以配置 API 密钥")
    else:
        fallback_env = PROJECT_ROOT / '.env'
        if fallback_env.exists():
            check_ok(".env 文件存在（在项目目录中）")
        else:
            check_fail(f"{_DHH}/.env 文件缺失")
            if should_fix:
                env_path.parent.mkdir(parents=True, exist_ok=True)
                env_path.touch()
                try:
                    os.chmod(str(env_path), 0o600)
                except OSError:
                    pass
                check_ok(f"已创建空的 {_DHH}/.env")
                check_info("运行 'hermes setup' 以配置 API 密钥")
                fixed_count += 1
            else:
                check_info("运行 'hermes setup' 来创建一个")
                issues.append("运行 'hermes setup' 创建 .env")
    
    config_path = HERMES_HOME / 'config.yaml'
    if config_path.exists():
        check_ok(f"{_DHH}/config.yaml 存在")

        try:
            import yaml as _yaml
            cfg = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            model_section = cfg.get("model") or {}
            provider_raw = (model_section.get("provider") or "").strip()
            provider = provider_raw.lower()
            default_model = (model_section.get("default") or model_section.get("model") or "").strip()

            known_providers: set = set()
            try:
                from hermes_cli.auth import (
                    PROVIDER_REGISTRY,
                    resolve_provider as _resolve_auth_provider,
                )
                known_providers = set(PROVIDER_REGISTRY.keys()) | {"openrouter", "custom", "auto"}
            except Exception:
                _resolve_auth_provider = None
                pass
            try:
                from hermes_cli.config import get_compatible_custom_providers as _compatible_custom_providers
                from hermes_cli.providers import (
                    normalize_provider as _normalize_catalog_provider,
                    resolve_provider_full as _resolve_provider_full,
                )
            except Exception:
                _compatible_custom_providers = None
                _normalize_catalog_provider = None
                _resolve_provider_full = None

            custom_providers = []
            if _compatible_custom_providers is not None:
                try:
                    custom_providers = _compatible_custom_providers(cfg)
                except Exception:
                    custom_providers = []

            user_providers = cfg.get("providers")
            if isinstance(user_providers, dict):
                known_providers.update(str(name).strip().lower() for name in user_providers if str(name).strip())
            for entry in custom_providers:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "").strip()
                if name:
                    known_providers.add("custom:" + name.lower().replace(" ", "-"))

            valid_provider_ids = set(known_providers)
            provider_ids_to_accept = {provider} if provider else set()
            if _normalize_catalog_provider is not None:
                for known_provider in known_providers:
                    try:
                        valid_provider_ids.add(_normalize_catalog_provider(known_provider))
                    except Exception:
                        continue

            runtime_provider = provider
            if (
                provider
                and _resolve_auth_provider is not None
                and provider not in {"auto", "custom"}
            ):
                try:
                    runtime_provider = _resolve_auth_provider(provider)
                    provider_ids_to_accept.add(runtime_provider)
                except Exception:
                    runtime_provider = provider

            catalog_provider = provider
            if (
                provider
                and _resolve_provider_full is not None
                and provider not in {"auto", "custom"}
            ):
                provider_def = _resolve_provider_full(provider, user_providers, custom_providers)
                catalog_provider = provider_def.id if provider_def is not None else None
                if catalog_provider is not None:
                    provider_ids_to_accept.add(catalog_provider)

            if provider and provider != "auto":
                if catalog_provider is None or (
                    known_providers
                    and not (provider_ids_to_accept & valid_provider_ids)
                ):
                    known_list = ", ".join(sorted(known_providers)) if known_providers else "（不可用）"
                    _fail_and_issue(
                        f"model.provider '{provider_raw}' 不是一个可识别的提供商",
                        f"（已知: {known_list}）",
                        (
                            f"model.provider '{provider_raw}' 未知。"
                            f"有效的提供商: {known_list}。"
                            f"修复: 运行 'hermes config set model.provider <有效提供商>'"
                        ),
                        issues,
                    )

            provider_for_policy = runtime_provider or catalog_provider
            provider_policy_id = str(provider_for_policy or "").strip().lower()
            providers_accepting_vendor_slugs = {
                "openrouter",
                "auto",
                "kilocode",
                "opencode-zen",
                "huggingface",
                "lmstudio",
                "nous",
            }
            provider_accepts_vendor_slug = (
                provider_policy_id in providers_accepting_vendor_slugs
                or provider_policy_id == "custom"
                or provider_policy_id.startswith("custom:")
            )
            if (
                default_model
                and "/" in default_model
                and provider_policy_id
                and not provider_accepts_vendor_slug
            ):
                check_warn(
                    f"model.default '{default_model}' 使用了提供商/模型标签但提供商是 '{provider_raw}'",
                    "（供应商前缀标签属于像 openrouter 这样的聚合器）",
                )
                issues.append(
                    f"model.default '{default_model}' 是供应商前缀的但 model.provider 是 '{provider_raw}'。"
                    "要么将 model.provider 设置为 'openrouter'，要么删除供应商前缀。"
                )

            if runtime_provider and runtime_provider not in ("auto", "custom"):
                try:
                    if runtime_provider == "openrouter":
                        from hermes_cli.config import get_env_value

                        configured = bool(
                            str(get_env_value("OPENROUTER_API_KEY") or "").strip()
                            or str(get_env_value("OPENAI_API_KEY") or "").strip()
                        )
                    else:
                        from hermes_cli.auth import PROVIDER_REGISTRY, get_auth_status

                        pconfig = PROVIDER_REGISTRY.get(runtime_provider)
                        configured = True
                        if pconfig and getattr(pconfig, "auth_type", "") == "api_key":
                            status = get_auth_status(runtime_provider) or {}
                            configured = bool(
                                status.get("configured")
                                or status.get("logged_in")
                                or status.get("api_key")
                            )
                    if not configured:
                        _fail_and_issue(
                            f"model.provider '{runtime_provider}' 已设置但未配置 API 密钥",
                            "（检查 ~/.hermes/.env 或运行 'hermes setup'）",
                            (
                                f"未找到提供商 '{runtime_provider}' 的凭据。"
                                f"运行 'hermes setup' 或在 {_DHH}/.env 中设置提供商的 API 密钥，"
                                f"或使用 'hermes config set model.provider <名称>' 切换提供商"
                            ),
                            issues,
                        )
                except Exception:
                    pass

        except Exception as e:
            check_warn("无法验证模型/提供商配置", f"({e})")
    else:
        fallback_config = PROJECT_ROOT / 'cli-config.yaml'
        if fallback_config.exists():
            check_ok("cli-config.yaml 存在（在项目目录中）")
        else:
            if should_fix:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                example_config = PROJECT_ROOT / 'cli-config.yaml.example'
                if example_config.exists():
                    shutil.copy2(str(example_config), str(config_path))
                    check_ok(f"从 cli-config.yaml.example 创建了 {_DHH}/config.yaml")
                else:
                    from hermes_cli.config import DEFAULT_CONFIG, save_config
                    save_config(DEFAULT_CONFIG)
                    check_ok(f"从默认值创建了 {_DHH}/config.yaml")
                fixed_count += 1
            else:
                check_warn("未找到 config.yaml", "（使用默认值）")

    config_path = HERMES_HOME / 'config.yaml'
    if config_path.exists():
        try:
            from hermes_cli.config import check_config_version, migrate_config
            current_ver, latest_ver = check_config_version()
            if current_ver < latest_ver:
                check_warn(
                    f"配置版本过时 (v{current_ver} → v{latest_ver})",
                    "（有新的设置可用）"
                )
                if should_fix:
                    try:
                        migrate_config(interactive=False, quiet=False)
                        check_ok("配置已迁移到最新版本")
                        fixed_count += 1
                    except Exception as mig_err:
                        check_warn(f"自动迁移失败: {mig_err}")
                        issues.append("运行 'hermes setup' 以迁移配置")
                else:
                    issues.append("运行 'hermes doctor --fix' 或 'hermes setup' 以迁移配置")
            else:
                check_ok(f"配置版本是最新的 (v{current_ver})")
        except Exception:
            pass

        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}
            stale_root_keys = [k for k in ("provider", "base_url") if k in raw_config and isinstance(raw_config[k], str)]
            if stale_root_keys:
                check_warn(
                    f"过时的根级别配置键: {', '.join(stale_root_keys)}",
                    "（应在 'model:' 部分下）"
                )
                if should_fix:
                    raw_model = raw_config.get("model")
                    if isinstance(raw_model, dict):
                        model_section = raw_model
                    elif isinstance(raw_model, str) and raw_model.strip():
                        model_section = {"default": raw_model.strip()}
                        raw_config["model"] = model_section
                    else:
                        model_section = {}
                        raw_config["model"] = model_section
                    for k in stale_root_keys:
                        if not model_section.get(k):
                            model_section[k] = raw_config.pop(k)
                        else:
                            raw_config.pop(k)
                    from utils import atomic_yaml_write
                    atomic_yaml_write(config_path, raw_config)
                    check_ok("已将过时的根级别键迁移到模型部分")
                    fixed_count += 1
                else:
                    issues.append("config.yaml 中有过时的根级别 provider/base_url — 运行 'hermes doctor --fix'")
        except Exception:
            pass

        try:
            import yaml
            from hermes_cli.config import load_env, remove_env_value
            with open(config_path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}
            agent_cfg = raw_config.get("agent")
            cfg_max_turns = (
                agent_cfg.get("max_turns")
                if isinstance(agent_cfg, dict)
                else None
            )
            if cfg_max_turns is None:
                cfg_max_turns = raw_config.get("max_turns")
            env_ghost = load_env().get("HERMES_MAX_ITERATIONS")
            drift = (
                cfg_max_turns is not None
                and env_ghost is not None
                and str(cfg_max_turns).strip() != str(env_ghost).strip()
            )
            if drift:
                check_warn(
                    f".env 中的 HERMES_MAX_ITERATIONS={env_ghost} 掩盖了 "
                    f"config.yaml 中的 agent.max_turns={cfg_max_turns}",
                    "（来自早期 `hermes setup` 运行的过时残留）",
                )
                if should_fix:
                    if remove_env_value("HERMES_MAX_ITERATIONS"):
                        check_ok(
                            "已从 .env 中移除过时的 HERMES_MAX_ITERATIONS "
                            f"（config.yaml agent.max_turns={cfg_max_turns} 现在是权威的）"
                        )
                        fixed_count += 1
                    else:
                        check_warn("无法从 .env 中移除 HERMES_MAX_ITERATIONS")
                        manual_issues.append(
                            "手动从 "
                            f"{_DHH}/.env 中删除 HERMES_MAX_ITERATIONS 行 — config.yaml agent.max_turns 是权威的。"
                        )
                else:
                    issues.append(
                        ".env 中的过时 HERMES_MAX_ITERATIONS 掩盖了 config.yaml — "
                        "运行 'hermes doctor --fix'"
                    )
        except Exception:
            pass

        try:
            from hermes_cli.config import validate_config_structure
            config_issues = validate_config_structure()
            if config_issues:
                _section("配置结构")
                for ci in config_issues:
                    if ci.severity == "error":
                        check_fail(ci.message)
                    else:
                        check_warn(ci.message)
                    for hint_line in ci.hint.splitlines():
                        check_info(hint_line)
                    issues.append(ci.message)
        except Exception:
            pass

    _section("xAI 模型退役（2026 年 5 月 15 日）")

    try:
        from hermes_cli.config import load_config
        from hermes_cli.xai_retirement import (
            MIGRATION_GUIDE_URL,
            find_retired_xai_refs,
            format_issue,
        )

        _xai_cfg = load_config()
        retired_refs = find_retired_xai_refs(_xai_cfg)
        if not retired_refs:
            check_ok("配置中没有已退役的 xAI 模型")
        else:
            for ref in retired_refs:
                check_warn(format_issue(ref))
            check_info(f"迁移指南: {MIGRATION_GUIDE_URL}")
            manual_issues.append(
                f"更新 config.yaml 中的 {len(retired_refs)} 个已退役的 xAI 模型引用 "
                f"— 参见 {MIGRATION_GUIDE_URL}"
            )
    except Exception as _xai_check_err:
        check_warn("xAI 退役检查已跳过", f"({_xai_check_err})")

    _section("认证提供商")

    try:
        from hermes_cli.auth import (
            get_nous_auth_status,
            get_codex_auth_status,
            get_gemini_oauth_auth_status,
            get_minimax_oauth_auth_status,
        )

        nous_status = get_nous_auth_status()
        if nous_status.get("logged_in"):
            check_ok("Nous Portal 认证", "（已登录）")
        else:
            check_warn("Nous Portal 认证", "（未登录）")

        codex_status = get_codex_auth_status()
        if codex_status.get("logged_in"):
            check_ok("OpenAI Codex 认证", "（已登录）")
        else:
            check_warn("OpenAI Codex 认证", "（未登录）")
            if codex_status.get("error"):
                check_info(codex_status["error"])
            if not _safe_which("codex"):
                check_info(
                    "未安装 codex CLI "
                    "（可选 — 仅用于从现有的 Codex CLI 登录导入令牌时必需）"
                )

        gemini_status = get_gemini_oauth_auth_status()
        if gemini_status.get("logged_in"):
            email = gemini_status.get("email") or ""
            project = gemini_status.get("project_id") or ""
            pieces = []
            if email:
                pieces.append(email)
            if project:
                pieces.append(f"project={project}")
            suffix = f" ({', '.join(pieces)})" if pieces else ""
            check_ok("Google Gemini OAuth", f"（已登录{suffix}）")
        else:
            check_warn("Google Gemini OAuth", "（未登录）")

        minimax_status = get_minimax_oauth_auth_status()
        if minimax_status.get("logged_in"):
            region = minimax_status.get("region", "global")
            check_ok("MiniMax OAuth", f"（已登录，区域={region}）")
        else:
            check_warn("MiniMax OAuth", "（未登录）")
    except Exception as e:
        check_warn("认证提供商状态", f"(无法检查: {e})")

    try:
        from hermes_cli.auth import get_xai_oauth_auth_status
        xai_oauth_status = get_xai_oauth_auth_status() or {}
        if xai_oauth_status.get("logged_in"):
            check_ok("xAI OAuth", "（已登录）")
        else:
            check_warn("xAI OAuth", "（未登录）")
            if xai_oauth_status.get("error"):
                check_info(xai_oauth_status["error"])
    except Exception:
        pass

    _section("目录结构")
    hermes_home = HERMES_HOME
    if hermes_home.exists():
        check_ok(f"{_DHH} 目录存在")
    elif should_fix:
        hermes_home.mkdir(parents=True, exist_ok=True)
        check_ok(f"已创建 {_DHH} 目录")
        fixed_count += 1
    else:
        check_warn(f"{_DHH} 未找到", "（将在首次使用时创建）")
    
    expected_subdirs = ["cron", "sessions", "logs", "skills", "memories"]
    for subdir_name in expected_subdirs:
        subdir_path = hermes_home / subdir_name
        if subdir_path.exists():
            check_ok(f"{_DHH}/{subdir_name}/ 存在")
        elif should_fix:
            subdir_path.mkdir(parents=True, exist_ok=True)
            check_ok(f"已创建 {_DHH}/{subdir_name}/")
            fixed_count += 1
        else:
            check_warn(f"{_DHH}/{subdir_name}/ 未找到", "（将在首次使用时创建）")
    
    soul_path = hermes_home / "SOUL.md"
    if soul_path.exists():
        content = soul_path.read_text(encoding="utf-8").strip()
        lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith(("<!--", "-->", "#"))]
        if lines:
            check_ok(f"{_DHH}/SOUL.md 存在（个性已配置）")
        else:
            check_info(f"{_DHH}/SOUL.md 存在但为空 — 编辑它以自定义个性")
    else:
        check_warn(f"{_DHH}/SOUL.md 未找到", "（创建它以赋予 Hermes 自定义个性）")
        if should_fix:
            soul_path.parent.mkdir(parents=True, exist_ok=True)
            soul_path.write_text(
                "# Hermes Agent Persona\n\n"
                "<!-- 编辑此文件以自定义 Hermes 的沟通方式。 -->\n\n"
                "你是 Hermes，一个乐于助人的 AI 助手。\n",
                encoding="utf-8",
            )
            check_ok(f"已使用基本模板创建 {_DHH}/SOUL.md")
            fixed_count += 1
    
    memories_dir = hermes_home / "memories"
    if memories_dir.exists():
        check_ok(f"{_DHH}/memories/ 目录存在")
        memory_file = memories_dir / "MEMORY.md"
        user_file = memories_dir / "USER.md"
        if memory_file.exists():
            size = len(memory_file.read_text(encoding="utf-8").strip())
            check_ok(f"MEMORY.md 存在（{size} 字符）")
        else:
            check_info("MEMORY.md 尚未创建（将在智能体首次写入记忆时创建）")
        if user_file.exists():
            size = len(user_file.read_text(encoding="utf-8").strip())
            check_ok(f"USER.md 存在（{size} 字符）")
        else:
            check_info("USER.md 尚未创建（将在智能体首次写入记忆时创建）")
    else:
        check_warn(f"{_DHH}/memories/ 未找到", "（将在首次使用时创建）")
        if should_fix:
            memories_dir.mkdir(parents=True, exist_ok=True)
            check_ok(f"已创建 {_DHH}/memories/")
            fixed_count += 1
    
    state_db_path = hermes_home / "state.db"
    if state_db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(state_db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            count = cursor.fetchone()[0]
            conn.close()
            check_ok(f"{_DHH}/state.db 存在（{count} 个会话）")
        except Exception as e:
            from hermes_state import is_malformed_db_error, repair_state_db_schema

            if is_malformed_db_error(e):
                check_warn(
                    f"{_DHH}/state.db 模式已损坏（会话被隐藏，直到修复）",
                    f"({e})",
                )
                if should_fix:
                    report = repair_state_db_schema(state_db_path)
                    if report.get("repaired"):
                        try:
                            conn = sqlite3.connect(str(state_db_path))
                            count = conn.execute(
                                "SELECT COUNT(*) FROM sessions"
                            ).fetchone()[0]
                            conn.close()
                        except Exception:
                            count = "?"
                        backup_name = (
                            Path(report["backup_path"]).name
                            if report.get("backup_path") else "n/a"
                        )
                        check_ok(
                            f"已修复 state.db 模式（{count} 个会话已恢复）",
                            f"（策略: {report.get('strategy')}; 备份: {backup_name}）",
                        )
                        fixed_count += 1
                    else:
                        check_warn(
                            "state.db 模式修复未能自动恢复",
                            f"({report.get('error')}; 备份: {report.get('backup_path')})",
                        )
                        issues.append(
                            "state.db 模式损坏且自动修复失败 — "
                            "从 state.db 旁边的备份副本恢复"
                        )
                else:
                    issues.append(
                        "state.db 模式损坏 — 运行 'hermes doctor --fix' "
                        "（或 'hermes sessions repair'）以恢复隐藏的会话"
                    )
            else:
                check_warn(f"{_DHH}/state.db 存在但存在问题: {e}")
    else:
        check_info(f"{_DHH}/state.db 尚未创建（将在首次会话时创建）")

    wal_path = hermes_home / "state.db-wal"
    if wal_path.exists():
        try:
            wal_size = wal_path.stat().st_size
            if wal_size > 50 * 1024 * 1024:  # 50 MB
                check_warn(
                    f"WAL 文件很大（{wal_size // (1024*1024)} MB）",
                    "（可能表示错过了检查点）"
                )
                if should_fix:
                    import sqlite3
                    conn = sqlite3.connect(str(state_db_path))
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    conn.close()
                    new_size = wal_path.stat().st_size if wal_path.exists() else 0
                    check_ok(f"WAL 检查点已执行（{wal_size // 1024}K → {new_size // 1024}K）")
                    fixed_count += 1
                else:
                    issues.append("WAL 文件大 — 运行 'hermes doctor --fix' 以执行检查点")
            elif wal_size > 10 * 1024 * 1024:  # 10 MB
                check_info(f"WAL 文件为 {wal_size // (1024*1024)} MB（活动会话的正常大小）")
        except Exception:
            pass

    _check_gateway_service_linger(issues)
    _check_s6_supervision(issues)

    if sys.platform != "win32":
        _section("命令安装")
        _venv_bin = None
        for _venv_name in ("venv", ".venv"):
            _candidate = PROJECT_ROOT / _venv_name / "bin" / "hermes"
            if _candidate.exists():
                _venv_bin = _candidate
                break

        _prefix = os.environ.get("PREFIX", "")
        _is_termux_env = bool(os.environ.get("TERMUX_VERSION")) or "com.termux/files/usr" in _prefix
        if _is_termux_env and _prefix:
            _cmd_link_dir = Path(_prefix) / "bin"
            _cmd_link_display = "$PREFIX/bin"
        else:
            _cmd_link_dir = Path.home() / ".local" / "bin"
            _cmd_link_display = "~/.local/bin"
        _cmd_link = _cmd_link_dir / "hermes"

        if _venv_bin is None:
            check_warn(
                "未找到 Venv 入口点",
                "（hermes 不在 venv/bin/ 或 .venv/bin/ 中 — 使用 pip install -e '.[all]' 重新安装）"
            )
            manual_issues.append(
                f"重新安装入口点: cd {PROJECT_ROOT} && source venv/bin/activate && pip install -e '.[all]'"
            )
        else:
            check_ok(f"Venv 入口点存在（{_venv_bin.relative_to(PROJECT_ROOT)}）")

            if _cmd_link.is_symlink():
                _target = _cmd_link.resolve()
                _expected = _venv_bin.resolve()
                if _target == _expected:
                    check_ok(f"{_cmd_link_display}/hermes → 目标正确")
                else:
                    check_warn(
                        f"{_cmd_link_display}/hermes 指向错误的目标",
                        f"(→ {_target}, 期望 → {_expected})"
                    )
                    if should_fix:
                        _cmd_link.unlink()
                        _cmd_link.symlink_to(_venv_bin)
                        check_ok(f"已修复符号链接: {_cmd_link_display}/hermes → {_venv_bin}")
                        fixed_count += 1
                    else:
                        issues.append(f"{_cmd_link_display}/hermes 的符号链接已损坏 — 运行 'hermes doctor --fix'")
            elif _cmd_link.exists():
                check_ok(f"{_cmd_link_display}/hermes 存在（非符号链接）")
            else:
                check_fail(
                    f"{_cmd_link_display}/hermes 未找到",
                    "（hermes 命令在 venv 外部可能无法工作）"
                )
                if should_fix:
                    _cmd_link_dir.mkdir(parents=True, exist_ok=True)
                    _cmd_link.symlink_to(_venv_bin)
                    check_ok(f"已创建符号链接: {_cmd_link_display}/hermes → {_venv_bin}")
                    fixed_count += 1

                    _path_dirs = os.environ.get("PATH", "").split(os.pathsep)
                    if str(_cmd_link_dir) not in _path_dirs:
                        check_warn(
                            f"{_cmd_link_display} 不在您的 PATH 中",
                            "（将其添加到您的 shell 配置中: export PATH=\"$HOME/.local/bin:$PATH\"）"
                        )
                        manual_issues.append(f"将 {_cmd_link_display} 添加到您的 PATH")
                else:
                    issues.append(f"缺少 {_cmd_link_display}/hermes 符号链接 — 运行 'hermes doctor --fix'")

    _section("外部工具")
    if _safe_which("git"):
        check_ok("git")
    else:
        check_warn("未找到 git", "（可选）")
    
    if _safe_which("rg"):
        check_ok("ripgrep (rg)", "（更快的文件搜索）")
    else:
        check_warn("未找到 ripgrep (rg)", "（文件搜索将使用 grep 回退）")
        check_info(f"安装以获得更快的搜索: {_system_package_install_cmd('ripgrep')}")
    
    terminal_env = os.getenv("TERMINAL_ENV", "local")
    try:
        from hermes_constants import is_container as _is_container
        running_in_container = _is_container()
    except Exception:
        running_in_container = False

    if running_in_container:
        if terminal_env != "docker":
            check_info(
                "在容器内运行 — 使用本地终端后端 "
                "（Docker-in-Docker 默认未配置）"
            )
            terminal_env = "local"
    if terminal_env == "docker":
        if _safe_which("docker"):
            try:
                result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
            except subprocess.TimeoutExpired:
                result = None
            if result is not None and result.returncode == 0:
                check_ok("docker", "（守护进程运行中）")
            else:
                _fail_and_issue("docker 守护进程未运行", "", "启动 Docker 守护进程", issues)
        else:
            _fail_and_issue(
                "未找到 docker",
                "（TERMINAL_ENV=docker 需要）",
                "安装 Docker 或更改 TERMINAL_ENV",
                issues,
            )
    elif _safe_which("docker"):
        check_ok("docker", "（可选）")
    elif _is_termux():
        check_info("Docker 后端在 Termux 内部不可用（Android 上预期如此）")
    elif running_in_container:
        pass
    else:
        check_warn("未找到 docker", "（可选）")
    
    if terminal_env == "ssh":
        ssh_host = os.getenv("TERMINAL_SSH_HOST")
        if ssh_host:
            ssh_user = os.getenv("TERMINAL_SSH_USER")
            ssh_port = os.getenv("TERMINAL_SSH_PORT")
            ssh_key = os.getenv("TERMINAL_SSH_KEY")
            target = f"{ssh_user}@{ssh_host}" if ssh_user else ssh_host
            cmd = ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]
            if ssh_port:
                cmd += ["-p", ssh_port]
            if ssh_key:
                cmd += ["-i", os.path.expanduser(ssh_key)]
            cmd += [target, "echo ok"]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
            except subprocess.TimeoutExpired:
                result = None
            if result is not None and result.returncode == 0:
                check_ok(f"SSH 连接到 {ssh_host}")
            else:
                _fail_and_issue(f"SSH 连接到 {ssh_host}", "", f"检查 {ssh_host} 的 SSH 配置", issues)
        else:
            _fail_and_issue(
                "未设置 TERMINAL_SSH_HOST",
                "（TERMINAL_ENV=ssh 需要）",
                "在 .env 中设置 TERMINAL_SSH_HOST",
                issues,
            )
    
    if terminal_env == "daytona":
        daytona_key = os.getenv("DAYTONA_API_KEY")
        if daytona_key:
            check_ok("Daytona API 密钥", "（已配置）")
        else:
            _fail_and_issue(
                "未设置 DAYTONA_API_KEY",
                "（TERMINAL_ENV=daytona 需要）",
                "设置 DAYTONA_API_KEY 环境变量",
                issues,
            )
        try:
            from daytona import Daytona
            check_ok("daytona SDK", "（已安装）")
        except ImportError:
            _fail_and_issue(
                "未安装 daytona SDK",
                "（pip install daytona）",
                "安装 daytona SDK: pip install daytona",
                issues,
            )

    if _safe_which("node"):
        check_ok("Node.js")
        agent_browser_path = PROJECT_ROOT / "node_modules" / "agent-browser"
        agent_browser_ok = False
        if agent_browser_path.exists():
            check_ok("agent-browser (Node.js)", "（浏览器自动化）")
            agent_browser_ok = True
        elif shutil.which("agent-browser"):
            check_ok("agent-browser", "（浏览器自动化）")
            agent_browser_ok = True
        elif _is_termux():
            check_info("agent-browser 未安装（在测试的 Termux 路径中预期）")
            check_info("稍后手动安装: npm install -g agent-browser && agent-browser install")
            check_info("Termux 浏览器设置:")
            for step in _termux_browser_setup_steps(node_installed=True):
                check_info(step)
        else:
            check_warn("agent-browser 未安装", "（运行: npm install）")

        if agent_browser_ok and not _is_termux():
            try:
                from tools.browser_tool import (
                    _chromium_installed,
                    _is_camofox_mode,
                    _get_cloud_provider,
                    _get_cdp_override,
                    _using_lightpanda_engine,
                )
            except Exception:
                pass
            else:
                skip_chromium_check = (
                    _is_camofox_mode()
                    or bool(_get_cdp_override())
                    or _get_cloud_provider() is not None
                    or _using_lightpanda_engine()
                )
                if not skip_chromium_check:
                    if _chromium_installed():
                        check_ok("Playwright Chromium", "（浏览器引擎）")
                    else:
                        check_warn(
                            "Playwright Chromium 未安装",
                            "（browser_* 工具将对智能体隐藏）",
                        )
                        if sys.platform == "win32":
                            check_info(
                                f"使用以下命令安装: cd {PROJECT_ROOT} && "
                                "npx playwright install chromium"
                            )
                        else:
                            check_info(
                                f"使用以下命令安装: cd {PROJECT_ROOT} && "
                                "npx playwright install --with-deps chromium"
                            )
    elif _is_termux():
        check_info("未找到 Node.js（浏览器工具在测试的 Termux 路径中是可选的）")
        check_info("在 Termux 上使用以下命令安装 Node.js: pkg install nodejs")
        check_info("Termux 浏览器设置:")
        for step in _termux_browser_setup_steps(node_installed=False):
            check_info(step)
    else:
        check_warn("未找到 Node.js", "（可选，浏览器工具需要）")
    
    _npm_bin = _safe_which("npm")
    if _npm_bin:
        npm_audit_targets = [
            (PROJECT_ROOT, "浏览器工具 (agent-browser)", ["--workspaces=false"]),
            (PROJECT_ROOT, "web 工作区", ["--workspace", "web"]),
            (PROJECT_ROOT, "ui-tui 工作区", ["--workspace", "ui-tui"]),
            (PROJECT_ROOT / "scripts" / "whatsapp-bridge", "WhatsApp 桥接", []),
        ]
        for npm_dir, label, audit_extra in npm_audit_targets:
            check_dir = PROJECT_ROOT if audit_extra else npm_dir
            if not (check_dir / "node_modules").exists():
                continue
            try:
                audit_result = subprocess.run(
                    [_npm_bin, "audit", "--json", *audit_extra],
                    cwd=str(npm_dir),
                    capture_output=True, text=True, timeout=30,
                )
                import json as _json
                audit_data = _json.loads(audit_result.stdout) if audit_result.stdout.strip() else {}
                vuln_count = audit_data.get("metadata", {}).get("vulnerabilities", {})
                critical = vuln_count.get("critical", 0)
                high = vuln_count.get("high", 0)
                moderate = vuln_count.get("moderate", 0)
                total = critical + high + moderate
                if audit_extra and audit_extra[0] == "--workspace":
                    fix_cmd = None
                elif audit_extra == ["--workspaces=false"]:
                    fix_cmd = f"cd {npm_dir} && npm audit fix --workspaces=false"
                else:
                    fix_cmd = f"cd {npm_dir} && npm audit fix"
                if total == 0:
                    check_ok(f"{label} 依赖", "（没有已知漏洞）")
                elif critical > 0 or high > 0:
                    if fix_cmd:
                        vuln_detail = (
                            f"{critical} 严重, {high} 高, {moderate} 中 — 运行: {fix_cmd}"
                        )
                    else:
                        vuln_detail = (
                            f"{critical} 严重, {high} 高, {moderate} 中 — "
                            "构建工具公告；通过锁定文件升级清除"
                        )
                    check_warn(
                        f"{label} 依赖",
                        f"({vuln_detail})"
                    )
                    if audit_extra and audit_extra[0] == "--workspace":
                        check_info(
                            "  ^ 构建时工具（非运行时）；如果手动 npm 修复 "
                            "出现 arborist 错误，这是已知的 npm 错误 — "
                            "通过锁定文件升级清除"
                        )
                    issues.append(
                        f"{label} 有 {total} 个 npm "
                        f"{'漏洞' if total == 1 else '漏洞'}"
                    )
                else:
                    check_ok(
                        f"{label} 依赖",
                        f"({moderate} 个中度 "
                        f"{'漏洞' if moderate == 1 else '漏洞'})",
                    )
            except Exception:
                pass

    if _is_termux():
        check_info("Termux 兼容性回退:")
        for note in _termux_install_all_fallback_notes():
            check_info(note)

    _section("API 连通性")
    import concurrent.futures as _futures
    from collections import namedtuple as _namedtuple

    _ConnectivityResult = _namedtuple(
        "_ConnectivityResult", ["label", "lines", "issues"]
    )
    _probes: list = []

    def _probe_openrouter() -> _ConnectivityResult:
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            return _ConnectivityResult(
                "OpenRouter API",
                [(color("", Colors.YELLOW), "OpenRouter API",
                  color("（未配置）", Colors.DIM))],
                [],
            )
        try:
            import httpx
            r = httpx.get(
                OPENROUTER_MODELS_URL,
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if r.status_code == 200:
                return _ConnectivityResult(
                    "OpenRouter API",
                    [(color("", Colors.GREEN), "OpenRouter API", "")],
                    [],
                )
            if r.status_code == 401:
                return _ConnectivityResult(
                    "OpenRouter API",
                    [(color("", Colors.RED), "OpenRouter API",
                      color("（无效的 API 密钥）", Colors.DIM))],
                    ["检查 .env 中的 OPENROUTER_API_KEY"],
                )
            if r.status_code == 402:
                return _ConnectivityResult(
                    "OpenRouter API",
                    [(color("", Colors.RED), "OpenRouter API",
                      color("（余额不足 — 需要付款）", Colors.DIM))],
                    ["OpenRouter 账户余额不足。"
                     "修复: 运行 'hermes config set model.provider <提供商>' "
                     "以切换提供商，或在 "
                     "https://openrouter.ai/settings/credits 为您的 OpenRouter 账户充值"],
                )
            if r.status_code == 429:
                return _ConnectivityResult(
                    "OpenRouter API",
                    [(color("", Colors.RED), "OpenRouter API",
                      color("（频率限制）", Colors.DIM))],
                    ["OpenRouter 频率限制已触发 — 考虑切换到"
                     "其他提供商或等待"],
                )
            return _ConnectivityResult(
                "OpenRouter API",
                [(color("", Colors.RED), "OpenRouter API",
                  color(f"(HTTP {r.status_code})", Colors.DIM))],
                [],
            )
        except Exception as e:
            return _ConnectivityResult(
                "OpenRouter API",
                [(color("", Colors.RED), "OpenRouter API",
                  color(f"({e})", Colors.DIM))],
                ["检查网络连接"],
            )

    def _probe_anthropic() -> _ConnectivityResult:
        from hermes_cli.auth import get_anthropic_key
        key = get_anthropic_key()
        if not key:
            return _ConnectivityResult("Anthropic API", [], [])
        try:
            import httpx
            from agent.anthropic_adapter import (
                _is_oauth_token,
                _COMMON_BETAS,
                _OAUTH_ONLY_BETAS,
                _CONTEXT_1M_BETA,
            )
            headers = {"anthropic-version": "2023-06-01"}
            is_oauth = _is_oauth_token(key)
            if is_oauth:
                headers["Authorization"] = f"Bearer {key}"
                headers["anthropic-beta"] = ",".join(_COMMON_BETAS + _OAUTH_ONLY_BETAS)
            else:
                headers["x-api-key"] = key
            r = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers=headers, timeout=10,
            )
            if (
                is_oauth
                and r.status_code == 400
                and "long context beta" in r.text.lower()
                and "not yet available" in r.text.lower()
            ):
                headers["anthropic-beta"] = ",".join(
                    [b for b in _COMMON_BETAS if b != _CONTEXT_1M_BETA]
                    + list(_OAUTH_ONLY_BETAS)
                )
                r = httpx.get(
                    "https://api.anthropic.com/v1/models",
                    headers=headers, timeout=10,
                )
            if r.status_code == 200:
                return _ConnectivityResult(
                    "Anthropic API",
                    [(color("", Colors.GREEN), "Anthropic API", "")],
                    [],
                )
            if r.status_code == 401:
                return _ConnectivityResult(
                    "Anthropic API",
                    [(color("", Colors.RED), "Anthropic API",
                      color("（无效的 API 密钥）", Colors.DIM))],
                    [],
                )
            return _ConnectivityResult(
                "Anthropic API",
                [(color("", Colors.YELLOW), "Anthropic API",
                  color("（无法验证）", Colors.DIM))],
                [],
            )
        except Exception as e:
            return _ConnectivityResult(
                "Anthropic API",
                [(color("", Colors.YELLOW), "Anthropic API",
                  color(f"({e})", Colors.DIM))],
                [],
            )

    def _probe_apikey_provider(pname, env_vars, default_url, base_env,
                               supports_health_check) -> _ConnectivityResult:
        key = ""
        for ev in env_vars:
            key = os.getenv(ev, "")
            if key:
                break
        if not key:
            return _ConnectivityResult(pname, [], [])
        label = pname.ljust(20)
        if not supports_health_check:
            return _ConnectivityResult(
                pname,
                [(color("", Colors.GREEN), label,
                  color("（密钥已配置）", Colors.DIM))],
                [],
            )
        try:
            import httpx
            base = os.getenv(base_env, "") if base_env else ""
            if not base and key.startswith("sk-kimi-"):
                base = "https://api.kimi.com/coding/v1"
            if base and base.rstrip("/").endswith("/anthropic"):
                from agent.auxiliary_client import _to_openai_base_url
                base = _to_openai_base_url(base)
            if base_url_host_matches(base, "api.kimi.com") and base.rstrip("/").endswith("/coding"):
                base = base.rstrip("/") + "/v1"
            url = (base.rstrip("/") + "/models") if base else default_url
            headers = {
                "Authorization": f"Bearer {key}",
                "User-Agent": _HERMES_USER_AGENT,
            }
            if base_url_host_matches(base, "api.kimi.com"):
                headers["User-Agent"] = "claude-code/0.1.0"
            if url and base_url_host_matches(url, "generativelanguage.googleapis.com"):
                headers.pop("Authorization", None)
                headers["x-goog-api-key"] = key
            r = httpx.get(url, headers=headers, timeout=10)
            if (
                pname == "Alibaba/DashScope"
                and not base
                and r.status_code == 401
            ):
                r = httpx.get(
                    "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
                    headers=headers, timeout=10,
                )
            if r.status_code == 200:
                return _ConnectivityResult(
                    pname,
                    [(color("", Colors.GREEN), label, "")],
                    [],
                )
            if r.status_code == 401:
                return _ConnectivityResult(
                    pname,
                    [(color("", Colors.RED), label,
                      color("（无效的 API 密钥）", Colors.DIM))],
                    [f"检查 .env 中的 {env_vars[0]}"],
                )
            return _ConnectivityResult(
                pname,
                [(color("", Colors.YELLOW), label,
                  color(f"(HTTP {r.status_code})", Colors.DIM))],
                [],
            )
        except Exception as e:
            return _ConnectivityResult(
                pname,
                [(color("", Colors.YELLOW), label,
                  color(f"({e})", Colors.DIM))],
                [],
            )

    def _probe_bedrock() -> _ConnectivityResult:
        try:
            from agent.bedrock_adapter import (
                has_aws_credentials,
                resolve_aws_auth_env_var,
                resolve_bedrock_region,
            )
        except ImportError:
            return _ConnectivityResult("AWS Bedrock", [], [])
        if not has_aws_credentials():
            return _ConnectivityResult("AWS Bedrock", [], [])
        auth_var = resolve_aws_auth_env_var()
        region = resolve_bedrock_region()
        label = "AWS Bedrock".ljust(20)
        try:
            import boto3
            from botocore.config import Config as _BotoConfig
            cfg = _BotoConfig(
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 1},
            )
            client = boto3.client("bedrock", region_name=region, config=cfg)
            resp = client.list_foundation_models()
            n = len(resp.get("modelSummaries", []))
            return _ConnectivityResult(
                "AWS Bedrock",
                [(color("", Colors.GREEN), label,
                  color(f"({auth_var}, {region}, {n} 模型)", Colors.DIM))],
                [],
            )
        except ImportError:
            return _ConnectivityResult(
                "AWS Bedrock",
                [(color("", Colors.YELLOW), label,
                  color(f"（未安装 boto3 — {sys.executable} -m pip install boto3）",
                        Colors.DIM))],
                [f"为 Bedrock 安装 boto3: {sys.executable} -m pip install boto3"],
            )
        except Exception as e:
            err_name = type(e).__name__
            return _ConnectivityResult(
                "AWS Bedrock",
                [(color("", Colors.YELLOW), label,
                  color(f"({err_name}: {e})", Colors.DIM))],
                [f"AWS Bedrock: {err_name} — 检查 bedrock:ListFoundationModels 的 IAM 权限"],
            )

    def _probe_azure_entra() -> _ConnectivityResult:
        label = "Azure Foundry (Entra ID)".ljust(28)
        try:
            from hermes_cli.config import load_config
            cfg = load_config()
            model_cfg = cfg.get("model") if isinstance(cfg, dict) else {}
            if not isinstance(model_cfg, dict):
                return _ConnectivityResult("Azure Foundry (Entra ID)", [], [])
            cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
            auth_mode = str(model_cfg.get("auth_mode") or "").strip().lower()
            if cfg_provider != "azure-foundry" or auth_mode != "entra_id":
                return _ConnectivityResult("Azure Foundry (Entra ID)", [], [])
        except Exception:
            return _ConnectivityResult("Azure Foundry (Entra ID)", [], [])

        try:
            from agent.azure_identity_adapter import (
                EntraIdentityConfig,
                SCOPE_AI_AZURE_DEFAULT,
                describe_active_credential,
                has_azure_identity_installed,
            )
        except Exception as exc:
            return _ConnectivityResult(
                "Azure Foundry (Entra ID)",
                [(color("", Colors.YELLOW), label,
                  color(f"（适配器导入失败: {exc}）", Colors.DIM))],
                [f"Azure Foundry 适配器导入失败: {exc}"],
            )

        if not has_azure_identity_installed():
            return _ConnectivityResult(
                "Azure Foundry (Entra ID)",
                [(color("", Colors.YELLOW), label,
                  color("（未安装 azure-identity）", Colors.DIM))],
                [f"安装 azure-identity: {sys.executable} -m pip install azure-identity"],
            )

        base_url = str(model_cfg.get("base_url") or "").strip()
        entra_cfg = model_cfg.get("entra") or {}
        if not isinstance(entra_cfg, dict):
            entra_cfg = {}
        scope = (
            str(entra_cfg.get("scope") or "").strip()
            or SCOPE_AI_AZURE_DEFAULT
        )
        config = EntraIdentityConfig(
            scope=scope,
        )
        info = describe_active_credential(config=config, timeout_seconds=10.0)
        if info.get("ok"):
            env_sources = info.get("env_sources") or []
            tag = ", ".join(env_sources) if env_sources else "默认凭据链"
            return _ConnectivityResult(
                "Azure Foundry (Entra ID)",
                [(color("", Colors.GREEN), label,
                  color(f"({tag}, scope={scope})", Colors.DIM))],
                [],
            )
        err = info.get("error") or "凭据链已耗尽"
        hint = info.get("hint") or (
            "运行 `az login`，设置 AZURE_TENANT_ID/AZURE_CLIENT_ID/"
            "AZURE_CLIENT_SECRET，或为此 VM 附加托管标识。"
        )
        return _ConnectivityResult(
            "Azure Foundry (Entra ID)",
            [(color("", Colors.YELLOW), label,
              color(f"({err})", Colors.DIM))],
            [f"Azure Foundry Entra: {err}. {hint}"],
        )

    _probes.append(("OpenRouter API", _probe_openrouter))
    _probes.append(("Anthropic API", _probe_anthropic))

    global _APIKEY_PROVIDERS_CACHE
    if _APIKEY_PROVIDERS_CACHE is None:
        _APIKEY_PROVIDERS_CACHE = _build_apikey_providers_list()
    for _entry in _APIKEY_PROVIDERS_CACHE:
        _pname, _env_vars, _default_url, _base_env, _supports = _entry
        _probes.append((_pname, lambda p=_pname, e=_env_vars, u=_default_url,
                                       b=_base_env, s=_supports:
                                _probe_apikey_provider(p, e, u, b, s)))

    _probes.append(("AWS Bedrock", _probe_bedrock))
    _probes.append(("Azure Foundry (Entra ID)", _probe_azure_entra))

    print(f"  {color(f'正在并行运行 {len(_probes)} 项连通性检查…', Colors.DIM)}",
          end="", flush=True)

    _imds_prev = os.environ.get("AWS_EC2_METADATA_DISABLED")
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    try:
        with _futures.ThreadPoolExecutor(max_workers=8,
                                         thread_name_prefix="doctor-probe") as _ex:
            _futures_in_order = [_ex.submit(_fn) for _, _fn in _probes]
            _results = [_f.result() for _f in _futures_in_order]
    finally:
        if _imds_prev is None:
            os.environ.pop("AWS_EC2_METADATA_DISABLED", None)
        else:
            os.environ["AWS_EC2_METADATA_DISABLED"] = _imds_prev

    print("\r" + " " * 70 + "\r", end="")
    for _r in _results:
        for _glyph, _label, _detail in _r.lines:
            if _detail:
                print(f"  {_glyph} {_label} {_detail}")
            else:
                print(f"  {_glyph} {_label}")
        _issues_to_add = list(_r.issues)
        if _issues_to_add and _has_healthy_oauth_fallback_for_apikey_provider(_r.label):
            _issues_to_add = []
        for _issue in _issues_to_add:
            issues.append(_issue)

    _section("工具可用性")
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from model_tools import check_tool_availability, TOOLSET_REQUIREMENTS
        
        available, unavailable = check_tool_availability()
        available, unavailable = _apply_doctor_tool_availability_overrides(available, unavailable)
        
        for tid in available:
            info = TOOLSET_REQUIREMENTS.get(tid, {})
            check_ok(info.get("name", tid), _doctor_tool_availability_detail(tid))
        
        for item in unavailable:
            env_vars = item.get("missing_vars") or item.get("env_vars") or []
            if env_vars:
                vars_str = ", ".join(env_vars)
                check_warn(item["name"], f"（缺少 {vars_str}）")
            else:
                check_warn(item["name"], "（系统依赖未满足）")

        api_disabled = [u for u in unavailable if (u.get("missing_vars") or u.get("env_vars"))]
        if api_disabled:
            issues.append("运行 'hermes setup' 以配置缺失的 API 密钥以获得完整工具访问权限")
    except Exception as e:
        check_warn("无法检查工具可用性", f"({e})")
    
    _section("技能中心")
    hub_dir = HERMES_HOME / "skills" / ".hub"
    if hub_dir.exists():
        check_ok("技能中心目录存在")
        lock_file = hub_dir / "lock.json"
        if lock_file.exists():
            try:
                import json
                lock_data = json.loads(lock_file.read_text())
                count = len(lock_data.get("installed", {}))
                check_ok(f"锁定文件正常（{count} 个中心安装的技能）")
            except Exception:
                check_warn("锁定文件", "（已损坏或无法读取）")
        quarantine = hub_dir / "quarantine"
        q_count = sum(1 for d in quarantine.iterdir() if d.is_dir()) if quarantine.exists() else 0
        if q_count > 0:
            check_warn(f"{q_count} 个技能在隔离区", "（待审查）")
    else:
        check_warn("技能中心目录未初始化", "（运行: hermes skills list）")

    from hermes_cli.config import get_env_value

    def _gh_authenticated() -> bool:
        try:
            result = subprocess.run(
                ["gh", "auth", "status", "--json", "authenticated"],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    github_token = get_env_value("GITHUB_TOKEN") or get_env_value("GH_TOKEN")
    if github_token:
        check_ok("GitHub 令牌已配置（已认证的 API 访问）")
    elif _gh_authenticated():
        check_ok("通过 gh CLI 已认证 GitHub", "（完整的 API 访问 — 无需 GITHUB_TOKEN）")
    else:
        check_warn("没有 GITHUB_TOKEN", f"（60 请求/小时 频率限制 — 在 {_DHH}/.env 中设置以获得更好的速率）")

    _section("记忆提供者")
    _active_memory_provider = ""
    try:
        import yaml as _yaml
        _mem_cfg_path = HERMES_HOME / "config.yaml"
        if _mem_cfg_path.exists():
            with open(_mem_cfg_path, encoding="utf-8") as _f:
                _raw_cfg = _yaml.safe_load(_f) or {}
            _active_memory_provider = (_raw_cfg.get("memory") or {}).get("provider", "")
    except Exception:
        pass

    if not _active_memory_provider:
        check_ok("内置记忆已激活", "（未配置外部提供者 — 这样没问题）")
    elif _active_memory_provider == "honcho":
        try:
            from plugins.memory.honcho.client import HonchoClientConfig, resolve_config_path
            hcfg = HonchoClientConfig.from_global_config()
            _honcho_cfg_path = resolve_config_path()

            if not _honcho_cfg_path.exists():
                if hcfg.api_key or hcfg.base_url:
                    check_ok(
                        "Honcho 通过环境变量配置",
                        f"配置文件 {_honcho_cfg_path} 未找到，使用 HONCHO_API_KEY 环境变量",
                    )
                else:
                    check_warn("Honcho 配置未找到", "运行: hermes memory setup")
            elif not hcfg.enabled:
                check_info(f"Honcho 已禁用（在 {_honcho_cfg_path} 中设置 enabled: true 以激活）")
            elif not (hcfg.api_key or hcfg.base_url):
                _fail_and_issue(
                    "Honcho API 密钥或基础 URL 未设置",
                    "运行: hermes memory setup",
                    "没有 Honcho API 密钥 — 运行 'hermes memory setup'",
                    issues,
                )
            else:
                from plugins.memory.honcho.client import get_honcho_client, reset_honcho_client
                reset_honcho_client()
                try:
                    get_honcho_client(hcfg)
                    check_ok(
                        "Honcho 已连接",
                        f"workspace={hcfg.workspace_id} mode={hcfg.recall_mode} freq={hcfg.write_frequency}",
                    )
                except Exception as _e:
                    _fail_and_issue("Honcho 连接失败", str(_e), f"Honcho 不可达: {_e}", issues)
        except ImportError:
            _fail_and_issue(
                "未安装 honcho-ai",
                "pip install honcho-ai",
                "Honcho 被设置为记忆提供者但未安装 honcho-ai",
                issues,
            )
        except Exception as _e:
            check_warn("Honcho 检查失败", str(_e))
    elif _active_memory_provider == "mem0":
        try:
            from plugins.memory.mem0 import _load_config as _load_mem0_config
            mem0_cfg = _load_mem0_config()
            mem0_key = mem0_cfg.get("api_key", "")
            if mem0_key:
                check_ok("Mem0 API 密钥已配置")
                check_info(f"user_id={mem0_cfg.get('user_id', '?')}  agent_id={mem0_cfg.get('agent_id', '?')}")
            else:
                _fail_and_issue(
                    "Mem0 API 密钥未设置",
                    "（在 .env 中设置 MEM0_API_KEY 或运行 hermes memory setup）",
                    "Mem0 被设置为记忆提供者但缺少 API 密钥",
                    issues,
                )
        except ImportError:
            _fail_and_issue(
                "Mem0 插件无法加载",
                "pip install mem0ai",
                "Mem0 被设置为记忆提供者但未安装 mem0ai",
                issues,
            )
        except Exception as _e:
            check_warn("Mem0 检查失败", str(_e))
    else:
        try:
            from plugins.memory import load_memory_provider
            _provider = load_memory_provider(_active_memory_provider)
            if _provider and _provider.is_available():
                check_ok(f"{_active_memory_provider} 提供者已激活")
            elif _provider:
                check_warn(f"{_active_memory_provider} 已配置但不可用", "运行: hermes memory status")
            else:
                check_warn(f"{_active_memory_provider} 插件未找到", "运行: hermes memory setup")
        except Exception as _e:
            check_warn(f"{_active_memory_provider} 检查失败", str(_e))

    try:
        from hermes_cli.profiles import list_profiles, _get_wrapper_dir, profile_exists
        import re as _re

        named_profiles = [p for p in list_profiles() if not p.is_default]
        if named_profiles:
            _section("配置集")
            check_ok(f"找到 {len(named_profiles)} 个配置集")
            wrapper_dir = _get_wrapper_dir()
            for p in named_profiles:
                parts = []
                if p.gateway_running:
                    parts.append("网关运行中")
                if p.model:
                    parts.append(p.model[:30])
                if not (p.path / "config.yaml").exists():
                    parts.append(" 缺少配置")
                if not (p.path / ".env").exists():
                    parts.append("没有 .env")
                wrapper = wrapper_dir / p.name
                if not wrapper.exists():
                    parts.append("没有别名")
                status = ", ".join(parts) if parts else "已配置"
                check_ok(f"  {p.name}: {status}")

            if wrapper_dir.is_dir():
                for wrapper in wrapper_dir.iterdir():
                    if not wrapper.is_file():
                        continue
                    try:
                        content = wrapper.read_text()
                        if "hermes -p" in content:
                            _m = _re.search(r"hermes -p (\S+)", content)
                            if _m and not profile_exists(_m.group(1)):
                                check_warn(f"孤立别名: {wrapper.name} → 配置集 '{_m.group(1)}' 不再存在")
                    except Exception:
                        pass
    except ImportError:
        pass
    except Exception:
        pass

    print()
    remaining_issues = issues + manual_issues
    if should_fix and fixed_count > 0:
        print(color("─" * 60, Colors.GREEN))
        print(color(f"  已修复 {fixed_count} 个问题。", Colors.GREEN, Colors.BOLD), end="")
        if remaining_issues:
            print(color(f" {len(remaining_issues)} 个问题需要手动干预。", Colors.YELLOW, Colors.BOLD))
        else:
            print()
        print()
        if remaining_issues:
            for i, issue in enumerate(remaining_issues, 1):
                print(f"  {i}. {issue}")
            print()
    elif remaining_issues:
        print(color("─" * 60, Colors.YELLOW))
        print(color(f"  发现 {len(remaining_issues)} 个需要处理的问题:", Colors.YELLOW, Colors.BOLD))
        print()
        for i, issue in enumerate(remaining_issues, 1):
            print(f"  {i}. {issue}")
        print()
        if not should_fix:
            print(color("  提示: 运行 'hermes doctor --fix' 以自动修复可能的问题。", Colors.DIM))
    else:
        print(color("─" * 60, Colors.GREEN))
        print(color("  所有检查通过！", Colors.GREEN, Colors.BOLD))
    
    print()
