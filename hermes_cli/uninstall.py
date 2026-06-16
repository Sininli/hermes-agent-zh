"""
Hermes Agent 卸载程序。

提供以下选项：
- 完全卸载：删除所有内容，包括配置和数据
- 保留数据：删除代码但保留 ~/.hermes/（配置、会话、日志）
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from hermes_constants import get_hermes_home

from hermes_cli.colors import Colors, color

def log_info(msg: str):
    print(f"{color('→', Colors.CYAN)} {msg}")

def log_success(msg: str):
    print(f"{color('', Colors.GREEN)} {msg}")

def log_warn(msg: str):
    print(f"{color('', Colors.YELLOW)} {msg}")

def get_project_root() -> Path:
    """获取项目安装目录。"""
    return Path(__file__).parent.parent.resolve()


def find_shell_configs() -> list:
    """查找可能包含 PATH 条目的 shell 配置文件。"""
    home = Path.home()
    configs = []
    
    candidates = [
        home / ".bashrc",
        home / ".bash_profile",
        home / ".profile",
        home / ".zshrc",
        home / ".zprofile",
    ]
    
    for config in candidates:
        if config.exists():
            configs.append(config)
    
    return configs


def remove_path_from_shell_configs():
    """从 shell 配置文件中移除 Hermes PATH 条目。"""
    configs = find_shell_configs()
    removed_from = []
    
    for config_path in configs:
        try:
            content = config_path.read_text()
            original_content = content
            
            # 移除包含 hermes-agent 或 hermes PATH 条目的行
            new_lines = []
            skip_next = False
            
            for line in content.split('\n'):
                # 跳过 "# Hermes Agent" 注释及后续行
                if '# Hermes Agent' in line or '# hermes-agent' in line:
                    skip_next = True
                    continue
                if skip_next and ('hermes' in line.lower() and 'PATH' in line):
                    skip_next = False
                    continue
                skip_next = False
                
                # 移除任何包含 hermes 的 PATH 行
                if 'hermes' in line.lower() and ('PATH=' in line or 'path=' in line.lower()):
                    continue
                    
                new_lines.append(line)
            
            new_content = '\n'.join(new_lines)
            
            # 清理多个空行
            while '\n\n\n' in new_content:
                new_content = new_content.replace('\n\n\n', '\n\n')
            
            if new_content != original_content:
                config_path.write_text(new_content)
                removed_from.append(config_path)
                
        except Exception as e:
            log_warn(f"无法更新 {config_path}: {e}")
    
    return removed_from


def remove_wrapper_script():
    """移除 hermes 包装脚本（如果存在）。"""
    wrapper_paths = [
        Path.home() / ".local" / "bin" / "hermes",
        Path("/usr/local/bin/hermes"),
    ]
    
    removed = []
    for wrapper in wrapper_paths:
        if wrapper.exists():
            try:
                # 检查是否是我们的包装脚本（包含 hermes_cli 引用）
                content = wrapper.read_text()
                if 'hermes_cli' in content or 'hermes-agent' in content:
                    wrapper.unlink()
                    removed.append(wrapper)
            except Exception as e:
                log_warn(f"无法移除 {wrapper}: {e}")
    
    return removed


def _node_symlink_candidate_dirs() -> "list[Path]":
    """安装程序可能放置 node/npm/npx 符号链接的目录。"""
    dirs: list[Path] = [Path.home() / ".local" / "bin"]
    # 根 FHS 安装将链接放在 /usr/local/bin。
    if sys.platform == "linux":
        dirs.append(Path("/usr/local/bin"))
    # Termux 安装将链接放在 $PREFIX/bin。
    prefix = os.environ.get("PREFIX", "")
    if prefix and "com.termux" in prefix:
        dirs.append(Path(prefix) / "bin")
    return dirs


def remove_node_symlinks(hermes_home: Path) -> list:
    """移除安装程序放置在 PATH 上的 node/npm/npx 符号链接。

    POSIX 安装程序（``scripts/install.sh`` / ``scripts/lib/node-bootstrap.sh``）
    将 node/npm/npx 符号链接到 ``hermes`` 命令所在的同一目录：

    - ``/usr/local/bin/`` 用于根 FHS 安装（Linux, uid 0）
    - ``$PREFIX/bin/`` 用于 Termux
    - ``~/.local/bin/`` 用于其他情况（常见非 root 情况）

    我们检查所有候选目录，以便卸载无论安装方式如何都能工作
    （例如，将链接放在 ``/usr/local/bin`` 的根 FHS 安装，或
    在 FHS 修复之前使用 ``~/.local/bin`` 的旧安装）。仅移除解析到
    此 Hermes 主目录的 ``node`` 目录的符号链接 — 用户已重定向到其他
    位置（nvm, fnm 等）的链接保持不动。
    """
    node_dir = (hermes_home / "node").resolve()
    removed = []

    for name in ("node", "npm", "npx"):
        for bin_dir in _node_symlink_candidate_dirs():
            link = bin_dir / name
            try:
                # 仅操作符号链接 — 从不删除用户放在此处的真实二进制文件。
                if not link.is_symlink():
                    continue

                # 解析链接目标并确认它指向我们的 node 目录。
                # os.readlink + 手动连接处理损坏的（悬挂）链接；
                # 悬挂链接上的 Path.resolve() 仍返回目标路径。
                target = Path(os.readlink(link))
                if not target.is_absolute():
                    target = (link.parent / target)
                target = target.resolve()

                if target == node_dir or node_dir in target.parents:
                    link.unlink()
                    removed.append(link)
            except Exception as e:
                log_warn(f"无法移除 {link}: {e}")

    return removed


def uninstall_gateway_service():
    """停止并卸载网关服务（systemd, launchd, Windows
    计划任务/启动文件夹）并终止所有独立的网关进程。

    委托给网关模块处理：
    - Linux: 用户 + 系统 systemd 服务（使用适当的 DBUS 环境设置）
    - macOS: launchd plist
    - Windows: 计划任务 + 启动文件夹回退，通过 ``gateway_windows``
    - 所有平台: 独立的 ``hermes gateway run`` 进程
    - Termux/Android: 跳过 systemd（Android 上没有 systemd），仍终止独立进程
    """
    import platform
    stopped_something = False

    # 1. 终止所有独立的网关进程（所有平台，包括 Termux）
    try:
        from hermes_cli.gateway import kill_gateway_processes, find_gateway_pids
        pids = find_gateway_pids()
        if pids:
            killed = kill_gateway_processes()
            if killed:
                log_success(f"已终止 {killed} 个运行中的网关进程")
                stopped_something = True
    except Exception as e:
        log_warn(f"无法检查网关进程: {e}")

    system = platform.system()

    # Termux/Android 没有 systemd 也没有 launchd — 无需再操作。
    prefix = os.getenv("PREFIX", "")
    is_termux = bool(os.getenv("TERMUX_VERSION") or "com.termux/files/usr" in prefix)
    if is_termux:
        return stopped_something

    # 2. Linux: 卸载 systemd 服务（用户和系统作用域）
    if system == "Linux":
        try:
            from hermes_cli.gateway import (
                get_systemd_unit_path,
                get_service_name,
                _systemctl_cmd,
            )
            svc_name = get_service_name()

            for is_system in (False, True):
                unit_path = get_systemd_unit_path(system=is_system)
                if not unit_path.exists():
                    continue

                scope = "system" if is_system else "user"
                try:
                    if is_system and os.geteuid() != 0:
                        log_warn(f"系统网关服务存在于 {unit_path} "
                                 f"但需要 sudo 权限才能移除")
                        continue

                    cmd = _systemctl_cmd(is_system)
                    subprocess.run(cmd + ["stop", svc_name],
                                   capture_output=True, check=False)
                    subprocess.run(cmd + ["disable", svc_name],
                                   capture_output=True, check=False)
                    unit_path.unlink()
                    subprocess.run(cmd + ["daemon-reload"],
                                   capture_output=True, check=False)
                    log_success(f"已移除 {scope} 网关服务 ({unit_path})")
                    stopped_something = True
                except Exception as e:
                    log_warn(f"无法移除 {scope} 网关服务: {e}")
        except Exception as e:
            log_warn(f"无法检查 systemd 网关服务: {e}")

    # 3. macOS: 卸载 launchd plist
    elif system == "Darwin":
        try:
            from hermes_cli.gateway import get_launchd_plist_path
            plist_path = get_launchd_plist_path()
            if plist_path.exists():
                subprocess.run(["launchctl", "unload", str(plist_path)],
                               capture_output=True, check=False)
                plist_path.unlink()
                log_success(f"已移除 macOS 网关服务 ({plist_path})")
                stopped_something = True
        except Exception as e:
            log_warn(f"无法移除 launchd 网关服务: {e}")

    # 4. Windows: 卸载计划任务 + 启动文件夹条目。
    elif system == "Windows":
        try:
            from hermes_cli import gateway_windows
            if gateway_windows.is_installed() or gateway_windows.is_task_registered() \
                    or gateway_windows.is_startup_entry_installed():
                try:
                    gateway_windows.stop()
                except Exception as e:
                    log_warn(f"无法干净地停止 Windows 网关: {e}")
                try:
                    gateway_windows.uninstall()
                    log_success("已移除 Windows 网关（计划任务 + 启动条目）")
                    stopped_something = True
                except Exception as e:
                    log_warn(f"无法完全卸载 Windows 网关: {e}")
        except Exception as e:
            log_warn(f"无法检查 Windows 网关服务: {e}")

    return stopped_something


def _hermes_path_markers(hermes_home: Path) -> list[str]:
    """标识 Hermes 拥有的用户 PATH 条目的路径子串。"""
    root = str(hermes_home).rstrip("\\/")
    markers = [root + "\\hermes-agent", root + "\\git", root + "\\node", root + "\\venv"]
    return markers


def remove_path_from_windows_registry(hermes_home: Path) -> list[str]:
    """从注册表中的用户作用域 PATH 中去除 Hermes 拥有的条目。

    返回已移除的路径条目列表。操作 HKCU\\Environment 键，
    与安装程序通过 ``[Environment]::SetEnvironmentVariable`` 写入的键相同。
    """
    try:
        import winreg
    except ImportError:
        return []

    removed: list[str] = []
    key_path = "Environment"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                path_value, path_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                return []
            entries = [e for e in path_value.split(";") if e]
            markers = _hermes_path_markers(hermes_home)
            kept: list[str] = []
            for entry in entries:
                entry_norm = entry.rstrip("\\/")
                matched = any(entry_norm.lower().startswith(m.lower()) for m in markers)
                if matched:
                    removed.append(entry)
                else:
                    kept.append(entry)
            if removed:
                new_value = ";".join(kept)
                winreg.SetValueEx(key, "Path", 0, path_type, new_value)
    except OSError as e:
        log_warn(f"无法编辑注册表中的用户 PATH: {e}")
    return removed


def remove_hermes_env_vars_windows() -> list[str]:
    """从用户作用域环境变量中删除 HERMES_HOME 和 HERMES_GIT_BASH_PATH。"""
    try:
        import winreg
    except ImportError:
        return []

    removed: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            for name in ("HERMES_HOME", "HERMES_GIT_BASH_PATH"):
                try:
                    winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                try:
                    winreg.DeleteValue(key, name)
                    removed.append(name)
                except OSError as e:
                    log_warn(f"无法从用户环境中删除 {name}: {e}")
    except OSError as e:
        log_warn(f"无法打开用户环境键: {e}")
    return removed


def remove_portable_tooling_windows(hermes_home: Path) -> list[Path]:
    """删除 Windows 安装程序在 ``%LOCALAPPDATA%\\hermes\\`` 下创建的 PortableGit 和 Node 安装。
    仅在完全卸载时调用；它们与系统 Git/Node 隔离，因此不会破坏其他工具。
    """
    removed: list[Path] = []
    for sub in ("git", "node", "gateway-service"):
        target = hermes_home / sub
        if target.exists():
            try:
                shutil.rmtree(target, ignore_errors=False)
                removed.append(target)
            except Exception as e:
                log_warn(f"无法移除 {target}: {e}")
    return removed


def _is_windows() -> bool:
    import sys
    return sys.platform == "win32"


def _is_default_hermes_home(hermes_home: Path) -> bool:
    """当 ``hermes_home`` 指向默认（非配置集）根目录时返回 True。"""
    try:
        from hermes_constants import get_default_hermes_root
        return hermes_home.resolve() == get_default_hermes_root().resolve()
    except Exception:
        return False


def _discover_named_profiles():
    """返回每个非默认配置集的 ``ProfileInfo`` 列表，如果配置集支持不可用
    或除默认根目录外未安装任何内容，则返回 ``[]``。"""
    try:
        from hermes_cli.profiles import list_profiles
    except Exception:
        return []
    try:
        return [p for p in list_profiles() if not getattr(p, "is_default", False)]
    except Exception as e:
        log_warn(f"无法枚举配置集: {e}")
        return []


def _uninstall_profile(profile) -> None:
    """完全卸载单个命名配置集：停止其网关服务，移除其别名包装脚本，
    并清空其 HERMES_HOME 目录。

    我们 shell 调用 ``hermes -p <name> gateway stop|uninstall``，因为
    服务名称、单元路径和 plist 路径都源自当前的 HERMES_HOME，
    无法在进程内轻松切换。
    """
    import sys as _sys
    name = profile.name
    profile_home = profile.path

    log_info(f"正在卸载配置集 '{name}'...")

    # 1. 停止并移除该配置集的网关服务。
    hermes_invocation = [_sys.executable, "-m", "hermes_cli.main", "--profile", name]
    for subcmd in ("stop", "uninstall"):
        try:
            subprocess.run(
                hermes_invocation + ["gateway", subcmd],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log_warn(f"  网关 {subcmd} 对 '{name}' 超时")
        except Exception as e:
            log_warn(f"  无法为 '{name}' 运行网关 {subcmd}: {e}")

    # 2. 移除 ~/.local/bin/<name> 处的别名包装脚本（如果有）。
    alias_path = getattr(profile, "alias_path", None)
    if alias_path and alias_path.exists():
        try:
            alias_path.unlink()
            log_success(f"  已移除别名 {alias_path}")
        except Exception as e:
            log_warn(f"  无法移除别名 {alias_path}: {e}")

    # 3. 清空配置集的 HERMES_HOME 目录。
    try:
        if profile_home.exists():
            shutil.rmtree(profile_home)
            log_success(f"  已移除 {profile_home}")
    except Exception as e:
        log_warn(f"  无法移除 {profile_home}: {e}")


def run_gui_uninstall(args):
    """仅 GUI 卸载：移除聊天 GUI，保留智能体和数据完整。

    镜像 ``hermes uninstall --gui``。移除桌面应用的构建产物，
    打包的应用包（尽力而为），以及 Electron userData 目录 —
    ``$HERMES_HOME`` 下的 config/sessions/.env 均不受影响，
    也绝不触及其他工具的 Python venv。
    """
    from hermes_cli.gui_uninstall import (
        agent_is_installed,
        gui_install_summary,
        uninstall_gui,
    )

    hermes_home = get_hermes_home()
    summary = gui_install_summary(hermes_home)
    skip_confirm = bool(getattr(args, "yes", False))

    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.MAGENTA, Colors.BOLD))
    print(color("│          Hermes 聊天 GUI 卸载程序                       │", Colors.MAGENTA, Colors.BOLD))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.MAGENTA, Colors.BOLD))
    print()

    if not summary["gui_installed"]:
        print("未找到 Hermes 聊天 GUI 安装。")
        print(f"  检查位置: {hermes_home}，以及此操作系统的标准应用位置。")
        return

    print(color("这将仅移除聊天 GUI。Hermes 智能体将保持安装状态。", Colors.CYAN))
    print()
    print(color("将移除:", Colors.YELLOW, Colors.BOLD))
    for p in summary["source_built_artifacts"]:
        print(f"   {p}")
    for p in summary["packaged_app_paths"]:
        print(f"   {p}")
    if summary["userdata_exists"]:
        print(f"   {summary['userdata_dir']}  (桌面应用数据)")
    print()
    if agent_is_installed(hermes_home):
        print(color("保留不变:", Colors.GREEN, Colors.BOLD))
        print(f"   {hermes_home / 'hermes-agent'} 中的 Hermes 智能体")
        print(f"   {hermes_home} 下的配置、会话和密钥")
        print()

    if not skip_confirm:
        try:
            confirm = input(f"输入 '{color('yes', Colors.YELLOW)}' 以移除聊天 GUI: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            print("已取消。")
            return
        if confirm != "yes":
            print()
            print("卸载已取消。")
            return

    print()
    print(color("正在卸载聊天 GUI...", Colors.CYAN, Colors.BOLD))
    print()
    uninstall_gui(hermes_home)

    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.GREEN, Colors.BOLD))
    print(color("│             聊天 GUI 已卸载！                           │", Colors.GREEN, Colors.BOLD))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.GREEN, Colors.BOLD))
    print()
    print("Hermes 智能体仍处于安装状态。运行 'hermes' 使用 CLI，")
    print("或运行 'hermes uninstall' 同时移除智能体。")
    print()


def run_uninstall(args):
    """
    运行卸载过程。
    
    选项：
    - 完全卸载：移除代码 + ~/.hermes/（配置、数据、日志）
    - 保留数据：移除代码但保留 ~/.hermes/ 以便将来重新安装
    """
    project_root = get_project_root()
    hermes_home = get_hermes_home()

    # 从默认根目录卸载时检测命名配置集 —
    # 主动提供清理它们，而不是留下僵尸 HERMES_HOME
    # 和 systemd 单元。
    is_default_profile = _is_default_hermes_home(hermes_home)
    named_profiles = _discover_named_profiles() if is_default_profile else []

    # 非交互式快速路径（``--yes``）：无提示。``--full`` 选择
    # 完全清除（代码 + ~/.hermes 数据）；否则保留数据。命名配置集
    # 不会自动移除 — 这对无人值守运行来说是破坏性且令人惊讶的默认行为，
    # 因此它保持为交互式流程的选择加入。这是
    # 桌面应用的独立清理脚本用于其精简/完整模式的路径。
    skip_confirm = bool(getattr(args, "yes", False))
    if skip_confirm:
        full_uninstall = bool(getattr(args, "full", False))
        _perform_uninstall(
            project_root=project_root,
            hermes_home=hermes_home,
            full_uninstall=full_uninstall,
            remove_profiles=False,
            named_profiles=named_profiles,
        )
        return

    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.MAGENTA, Colors.BOLD))
    print(color("│            Hermes 智能体卸载程序                       │", Colors.MAGENTA, Colors.BOLD))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.MAGENTA, Colors.BOLD))
    print()
    
    # 显示将会受影响的內容
    print(color("当前安装:", Colors.CYAN, Colors.BOLD))
    print(f"  代码:    {project_root}")
    print(f"  配置:  {hermes_home / 'config.yaml'}")
    print(f"  密钥: {hermes_home / '.env'}")
    print(f"  数据:    {hermes_home / 'cron/'}, {hermes_home / 'sessions/'}, {hermes_home / 'logs/'}")
    print()

    if named_profiles:
        print(color("检测到其他配置集:", Colors.CYAN, Colors.BOLD))
        for p in named_profiles:
            running = " (网关运行中)" if getattr(p, "gateway_running", False) else ""
            print(f"   {p.name}{running}: {p.path}")
        print()
    
    # 请求确认
    print(color("卸载选项:", Colors.YELLOW, Colors.BOLD))
    print()
    print("  1) " + color("保留数据", Colors.GREEN) + " - 仅移除代码，保留配置/会话/日志")
    print("     （推荐 - 以后可以重新安装，设置保持不变）")
    print()
    print("  2) " + color("完全卸载", Colors.RED) + " - 删除所有内容，包括所有数据")
    print("     （警告：这将永久删除所有配置、会话和日志）")
    print()
    print("  3) " + color("取消", Colors.CYAN) + " - 不卸载")
    print()
    
    try:
        choice = input(color("选择选项 [1/2/3]: ", Colors.BOLD)).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        print("已取消。")
        return
    
    if choice == "3" or choice.lower() in {"c", "cancel", "q", "quit", "n", "no"}:
        print()
        print("卸载已取消。")
        return
    
    full_uninstall = (choice == "2")

    # 从默认配置集执行完全卸载时，同时提供移除
    # 任何命名配置集的选项 — 停止其网关服务，取消链接
    # 其别名包装脚本，并清空其 HERMES_HOME 目录。否则
    # 这些会留下僵尸服务和数据。
    remove_profiles = False
    if full_uninstall and named_profiles:
        print()
        print(color("默认情况下不会移除其他配置集。", Colors.YELLOW))
        print(f"找到 {len(named_profiles)} 个命名配置集: " +
              ", ".join(p.name for p in named_profiles))
        print()
        try:
            resp = input(color(
                f"同时停止并移除这 {len(named_profiles)} 个配置集？[y/N]: ",
                Colors.BOLD
            )).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            print("已取消。")
            return
        remove_profiles = resp in {"y", "yes"}

    # 最终确认
    print()
    if full_uninstall:
        print(color("️  警告：这将永久删除所有 Hermes 数据！", Colors.RED, Colors.BOLD))
        print(color("   包括：配置、API 密钥、会话、计划任务、日志", Colors.RED))
        if remove_profiles:
            print(color(
                f"   加上 {len(named_profiles)} 个配置集: " +
                ", ".join(p.name for p in named_profiles),
                Colors.RED
            ))
    else:
        print("这将移除 Hermes 代码但保留您的配置和数据。")
    
    print()
    try:
        confirm = input(f"输入 '{color('yes', Colors.YELLOW)}' 以确认: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        print("已取消。")
        return
    
    if confirm != "yes":
        print()
        print("卸载已取消。")
        return

    _perform_uninstall(
        project_root=project_root,
        hermes_home=hermes_home,
        full_uninstall=full_uninstall,
        remove_profiles=remove_profiles,
        named_profiles=named_profiles,
    )


def _perform_uninstall(
    *,
    project_root: Path,
    hermes_home: Path,
    full_uninstall: bool,
    remove_profiles: bool,
    named_profiles: list,
) -> None:
    """执行卸载步骤。交互式和 ``--yes`` 路径共享此方法，
    因此破坏性序列仅存在于一个地方。

    步骤：停止网关 → 清除 PATH（rc 文件 + Windows 注册表）→ 移除
    ``hermes`` 包装脚本 + node 符号链接 → 移除桌面聊天 GUI 产物 →
    删除代码检出 → (Windows) 移除 PortableGit/Node →
    可选地在完全卸载时清空 ``$HERMES_HOME`` 数据和命名配置集。
    """
    print()
    print(color("正在卸载...", Colors.CYAN, Colors.BOLD))
    print()
    
    # 1. 停止并卸载网关服务 + 终止独立进程
    log_info("正在检查运行中的网关...")
    if not uninstall_gateway_service():
        log_info("未找到网关服务或进程")
    
    # 2. 从 shell 配置（POSIX）以及 Windows 用户作用域注册表中移除 PATH 条目。
    #    两个辅助函数在不适用平台上是空操作，因此我们可以安全地无条件调用它们。
    log_info("正在从 shell 配置中移除 PATH 条目...")
    removed_configs = remove_path_from_shell_configs()
    if removed_configs:
        for config in removed_configs:
            log_success(f"已更新 {config}")
    else:
        log_info("在 shell rc 文件中未找到要移除的 PATH 条目")

    if _is_windows():
        log_info("正在从 Windows 用户环境中移除 PATH 条目...")
        removed_path_entries = remove_path_from_windows_registry(Path(os.path.expandvars(str(hermes_home))))
        if removed_path_entries:
            for entry in removed_path_entries:
                log_success(f"已从用户 PATH 中移除: {entry}")
        else:
            log_info("用户环境中没有 Hermes 拥有的 PATH 条目")

        log_info("正在移除 HERMES_HOME / HERMES_GIT_BASH_PATH 用户环境变量...")
        removed_env = remove_hermes_env_vars_windows()
        if removed_env:
            for name in removed_env:
                log_success(f"已移除用户环境变量: {name}")
        else:
            log_info("没有要移除的 Hermes 设置的用户环境变量")
    
    # 3. 移除包装脚本
    log_info("正在移除 hermes 命令...")
    removed_wrappers = remove_wrapper_script()
    if removed_wrappers:
        for wrapper in removed_wrappers:
            log_success(f"已移除 {wrapper}")
    else:
        log_info("未找到包装脚本")

    # 3b. 移除安装程序留在 ~/.local/bin 的 node/npm/npx 符号链接
    log_info("正在移除 Hermes 管理的 node/npm/npx 符号链接...")
    removed_node_links = remove_node_symlinks(hermes_home)
    if removed_node_links:
        for link in removed_node_links:
            log_success(f"已移除 {link}")
    else:
        log_info("未找到 Hermes 管理的 node/npm/npx 符号链接")

    # 3c. 同时移除桌面聊天 GUI 的产物
    log_info("正在移除桌面聊天 GUI 产物...")
    try:
        from hermes_cli.gui_uninstall import uninstall_gui
        gui_removed = uninstall_gui(hermes_home)
        if not gui_removed:
            log_info("未找到桌面 GUI 产物")
    except Exception as e:
        log_warn(f"无法移除桌面 GUI 产物: {e}")

    # 4. 移除安装目录（代码）
    log_info("正在移除安装目录...")
    
    try:
        if project_root.exists():
            if hermes_home in project_root.parents or project_root.parent == hermes_home:
                shutil.rmtree(project_root)
                log_success(f"已移除 {project_root}")
            else:
                shutil.rmtree(project_root)
                log_success(f"已移除 {project_root}")
    except Exception as e:
        log_warn(f"无法完全移除 {project_root}: {e}")
        log_info("您可能需要手动删除它")

    # 4b. 仅 Windows：移除安装程序产物（非用户数据）
    if _is_windows():
        log_info("正在移除 Windows 安装程序产物（PortableGit, Node, gateway-service）...")
        removed_artifacts = remove_portable_tooling_windows(hermes_home)
        if removed_artifacts:
            for path in removed_artifacts:
                log_success(f"已移除 {path}")
        else:
            log_info("没有要移除的 Windows 安装程序产物")
    
    # 5. 可选地移除 ~/.hermes/ 数据目录（以及命名配置集）
    if full_uninstall:
        if remove_profiles and named_profiles:
            for prof in named_profiles:
                _uninstall_profile(prof)

        log_info("正在移除配置和数据...")
        try:
            if hermes_home.exists():
                shutil.rmtree(hermes_home)
                log_success(f"已移除 {hermes_home}")
        except Exception as e:
            log_warn(f"无法完全移除 {hermes_home}: {e}")
            log_info("您可能需要手动删除它")
    else:
        log_info(f"保留 {hermes_home} 中的配置和数据")
    
    # 完成
    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.GREEN, Colors.BOLD))
    print(color("│              卸载完成！                                 │", Colors.GREEN, Colors.BOLD))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.GREEN, Colors.BOLD))
    print()
    
    if not full_uninstall:
        print(color("您的配置和数据已保留:", Colors.CYAN))
        print(f"  {hermes_home}/")
        print()
        print("稍后使用现有设置重新安装:")
        if _is_windows():
            print(color("  iex (irm https://hermes-agent.nousresearch.com/install.ps1)", Colors.DIM))
        else:
            print(color("  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash", Colors.DIM))
        print()

    if _is_windows():
        print(color("打开新终端（PowerShell / Windows Terminal）以获取", Colors.YELLOW))
        print(color("更新的用户 PATH 和环境变量。", Colors.YELLOW))
    else:
        print(color("重新加载 shell 以完成流程:", Colors.YELLOW))
        print("  source ~/.bashrc  # 或 ~/.zshrc")
    print()
    print("感谢使用 Hermes 智能体！")
    print()


class _UninstallArgs:
    """用于下面模块入口点的轻量级 args 命名空间。"""

    def __init__(self, *, mode: str):
        self.gui = mode == "gui"
        self.gui_summary = False
        self.full = mode == "full"
        self.yes = True  # 模块入口点始终是非交互式的


def main(argv=None) -> int:
    """模块入口点：``python -m hermes_cli.uninstall --mode <gui|lite|full>``。

    存在以便桌面应用可以在被删除的 venv *外部* 的 Python 解释器下
    运行卸载。在 Windows 上，``lite``/``full`` 使用 rmtree 删除包含
    运行中 ``python.exe`` 的 venv — 而运行中的 .exe 是强制锁定的，
    因此从 venv 自己的解释器中执行会部分失败。桌面应用使用系统
    Python + ``PYTHONPATH=<agentRoot>`` 启动此程序，以便在拆除
    venv 时 ``import hermes_cli`` 从源代码解析。

    此模块仅导入 stdlib + ``hermes_constants`` + ``hermes_cli.colors``
    （以及延迟加载的 ``hermes_cli.gui_uninstall``），因此它在没有
    venv site-packages 的裸系统 Python 下也能正常运行。
    """
    import argparse

    parser = argparse.ArgumentParser(prog="python -m hermes_cli.uninstall")
    parser.add_argument(
        "--mode",
        choices=["gui", "lite", "full"],
        required=True,
        help="gui = 仅聊天 GUI; lite = GUI + 智能体，保留数据; full = 全部",
    )
    ns = parser.parse_args(argv)
    args = _UninstallArgs(mode=ns.mode)

    if args.gui:
        run_gui_uninstall(args)
    else:
        run_uninstall(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
