#!/usr/bin/env python3
"""
Hermes 技能文件全面中文翻译脚本
================================
用法:
  python translate_hermes_skills.py            # 翻译
  python translate_hermes_skills.py --restore  # 从备份还原
  python translate_hermes_skills.py --backup-only  # 仅备份，不翻译

功能:
  - 翻译前自动备份原文件
  - 翻译 skills 目录下所有 SKILL.md 的:
    - YAML 前置元数据 (description, name, triggers, tags 等)
    - Markdown 正文标题 (Headings)
    - 正文中的概览、描述性段落
    - 保留代码块、命令、技术术语、URL 不翻译
  - 翻译 Hermes 源代码文件（banner.py、tips.py 等）
  - 支持从备份还原所有文件
特点: 支持增量运行（跳过已翻译的）
前置: pip install pyyaml (可选，非必需)
"""

import os
import re
import json
import shutil
import sys
from datetime import datetime

HERMES_HOME = "C:/Users/Administrator/AppData/Local/hermes"
SKILLS_DIR = os.path.join(HERMES_HOME, "skills")
STATE_FILE = os.path.join(HERMES_HOME, ".translation_state.json")
BACKUP_DIR = os.path.join(HERMES_HOME, "translation_backups")
_BACKUP_TIMESTAMP = None  # 每次运行时设置一次

# ============================================================
# 0. 备份和还原工具函数
# ============================================================

def _get_backup_timestamp():
    global _BACKUP_TIMESTAMP
    if _BACKUP_TIMESTAMP is None:
        _BACKUP_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _BACKUP_TIMESTAMP

def _backup_file(file_path, subdir=""):
    """备份文件到 translation_backups/<timestamp>/<subdir>/ 下"""
    if not os.path.exists(file_path):
        return None
    ts = _get_backup_timestamp()
    rel = os.path.relpath(file_path, HERMES_HOME) if file_path.startswith(HERMES_HOME) else os.path.basename(file_path)
    backup_path = os.path.join(BACKUP_DIR, ts, subdir, rel.lstrip(os.sep))
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy2(file_path, backup_path)
    return backup_path

def _find_latest_backup():
    """找到最新的备份时间戳目录"""
    if not os.path.exists(BACKUP_DIR):
        return None
    timestamps = sorted([d for d in os.listdir(BACKUP_DIR)
                         if os.path.isdir(os.path.join(BACKUP_DIR, d))], reverse=True)
    return timestamps[0] if timestamps else None

def restore_all(timestamp=None):
    """从指定（或最新）的备份还原所有文件"""
    ts = timestamp or _find_latest_backup()
    if not ts:
        print("✗ 没有找到任何备份")
        return False
    backup_root = os.path.join(BACKUP_DIR, ts)
    if not os.path.exists(backup_root):
        print(f"✗ 备份目录不存在: {backup_root}")
        return False
    
    restored = 0
    errors = 0
    for root, dirs, files in os.walk(backup_root):
        for fname in files:
            backup_file = os.path.join(root, fname)
            # 计算相对于备份根目录的路径
            rel = os.path.relpath(backup_file, backup_root)
            target = os.path.join(HERMES_HOME, rel)
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(backup_file, target)
                print(f"  ✓ {rel}")
                restored += 1
            except Exception as e:
                print(f"  ✗ {rel} — {e}")
                errors += 1
    
    print(f"\n还原完成: {restored} 个文件还原, {errors} 个错误")
    # 清除翻译状态，以便下次运行重新翻译
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("（已清除翻译状态，下次运行脚本会重新翻译）")
    return True

# ============================================================
# 1. 章节标题翻译映射 (Heading Translation Map)
# ============================================================
HEADING_TRANS = {
    # 一等标题模式
    "Overview": "概述",
    "Overview and Usage Guidelines": "概述与使用指南",
    "Core behavior": "核心行为",
    "Core Behaviour": "核心行为",
    "Core principle": "核心原则",
    "Core Concept": "核心概念",
    "The Iron Law": "铁律",
    "When to Use": "使用时机",
    "When to use this skill": "使用时机",
    "When NOT to use": "不适用场景",
    "Prerequisites": "前置条件",
    "Quick Start": "快速开始",
    "Quick start": "快速开始",
    "Output requirements": "输出要求",
    "Save location": "保存位置",
    "Interaction style": "交互风格",
    "Your task": "你的任务",
    "The Task": "任务说明",
    "Definition / Purpose": "定义与目的",
    "Usage": "使用方法",
    "How to use it": "使用方法",
    "How to use": "使用方法",
    "How to use it in Hermes": "在 Hermes 中的使用方法",
    "Instructions": "操作说明",
    "Key concepts": "关键概念",
    "Key Features": "主要特性",
    "Key features": "主要特性",
    "Features": "功能特性",
    "Parameters": "参数说明",
    "Options": "选项说明",
    "Configuration": "配置说明",
    "Configuration Options": "配置选项",
    "Settings": "设置",
    "Examples": "示例",
    "Example": "示例",
    "Workflow": "工作流程",
    "Typical workflow": "典型工作流程",
    "Basic workflow": "基本工作流程",
    "Step-by-step": "分步指南",
    "Step-by-step guide": "分步指南",
    "How it works": "工作原理",
    "How This Works": "工作原理",
    "Technical details": "技术细节",
    "Technical Details": "技术细节",
    "Architecture": "架构说明",
    "Architecture Overview": "架构概述",
    "Notes": "注意事项",
    "Important notes": "重要说明",
    "Important": "重要",
    "Tips": "小贴士",
    "Troubleshooting": "故障排除",
    "Troubleshooting and FAQ": "故障排除与常见问题",
    "FAQ": "常见问题",
    "FAQ / Troubleshooting": "常见问题与故障排除",
    "Limitations": "局限性",
    "Known Issues": "已知问题",
    "Best practices": "最佳实践",
    "Best Practices": "最佳实践",
    "Security": "安全",
    "Security notes": "安全说明",
    "API Reference": "API 参考",
    "API": "API 说明",
    "Endpoints": "接口说明",
    "Data Format": "数据格式",
    "File Format": "文件格式",
    "Output format": "输出格式",
    "Return value": "返回值",
    "Returns": "返回值",
    "Errors": "错误处理",
    "Error handling": "错误处理",
    "Error Codes": "错误码",
    "Authentication": "身份验证",
    "Authentication and Authorization": "身份验证与授权",
    "Rate Limits": "频率限制",
    "Pagination": "分页",
    "Pagination and Filtering": "分页与筛选",
    "Filtering": "筛选",
    "Sorting": "排序",
    "Webhook": "Webhook",
    "Webhooks": "Webhook",
    "Webhook Events": "Webhook 事件",
    "Changelog": "更新日志",
    "Version History": "版本历史",
    "Installation": "安装方法",
    "Installation Guide": "安装指南",
    "Setup": "设置",
    "Setup Guide": "设置指南",
    "Initial Setup": "初始设置",
    "Getting Started": "入门指南",
    "Getting started": "入门指南",
    "Migration": "迁移指南",
    "Upgrading": "升级指南",
    "Uninstallation": "卸载",
    "Dependencies": "依赖项",
    "Requirements": "环境要求",
    "System Requirements": "系统要求",
    "Supported Platforms": "支持平台",
    "Compatibility": "兼容性",
    "Testing": "测试",
    "Test": "测试",
    "Running Tests": "运行测试",
    "Debugging": "调试",
    "Debugging Tips": "调试技巧",
    "Performance": "性能",
    "Performance Tuning": "性能调优",
    "Performance considerations": "性能考虑",
    "Background": "背景说明",
    "Background and Motivation": "背景与动机",
    "Motivation": "动机",
    "Design": "设计",
    "Design Principles": "设计原则",
    "Design Decisions": "设计决策",
    "Voice Calibration (optional)": "语音校准（可选）",
    "Voice Calibration": "语音校准",
    "PERSONALITY AND SOUL": "个性与灵魂",
    "What This Skill Does": "此技能的功能",
    "What this skill does": "此技能的功能",
    "Skills included": "包含的技能",
    "Included Tools": "包含的工具",
    "Tools": "工具说明",
    "Related Skills": "相关技能",
    "Related skills": "相关技能",
    "See also": "另请参阅",
    "Reference": "参考资料",
    "References": "参考资料",
    "Further Reading": "扩展阅读",
    "Next Steps": "后续步骤",
    "Summary": "总结",
    "Quick Reference": "快速参考",
    "Cheat Sheet": "速查表",
    "Command Reference": "命令参考",
    "CLI Reference": "CLI 参考",
    "Commands": "命令说明",
    "Subcommands": "子命令",
    "Arguments": "参数",
    "Flags": "标记选项",
    "Environment Variables": "环境变量",
    "Exit Codes": "退出码",
    "Logging": "日志",
    "Monitoring": "监控",
    "Templates": "模板",
    "Template Syntax": "模板语法",
    "Schema": "架构",
    "Validation": "验证",
    "Validation Rules": "验证规则",
    "Advanced Usage": "高级用法",
    "Advanced usage": "高级用法",
    "Advanced Options": "高级选项",
    "Advanced": "高级",
    "Customization": "自定义",
    "Customizing": "自定义",
    "Extending": "扩展",
    "Plugins": "插件",
    "Plugin Development": "插件开发",
    "Contributing": "贡献指南",
    "Support": "支持",
    "License": "许可证",
    "Quick Auth Detection": "快速身份验证检测",
    "Extracting Owner/Repo from the Git Remote": "从 Git 远程仓库提取 Owner/Repo",
    "Typical structure": "典型结构",
    "Portable Install Pattern": "便携版安装模式",
    "Add to Windows PATH Permanently": "永久添加到 Windows PATH",
    "Confirm the addition": "确认添加结果",
    "Edit the registry directly": "直接编辑注册表",
    "Shell integration": "Shell 集成",
    "Install Fonts": "安装字体",
    "Start / Stop / Restart": "启动/停止/重启",
    "Container run (single turn)": "容器运行（单轮对话）",
    "Container shell (interactive)": "容器 Shell（交互式）",
    "Build from source": "从源码构建",
    "Using Docker (optional)": "使用 Docker（可选）",
    "Initialize a new project": "初始化新项目",
    "Production deployment": "生产环境部署",
    "Local development": "本地开发",
    "Multi-turn conversation": "多轮对话",
    "Single query": "单次查询",
    "Run as subprocess": "以子进程运行",
    "Docker-based isolation": "基于 Docker 的隔离",
    "With MCP servers": "使用 MCP 服务器",
    "Code Review Process": "代码审查流程",
    "The Review Checklist": "审查清单",
    "Security Scan": "安全扫描",
    "Quality Gates": "质量门禁",
    "Auto-fix": "自动修复",
    "Sending Feedback": "提交反馈",
    "Approving Changes": "批准变更",
    "Requesting Changes": "请求变更",
    "Merging": "合并",
    "Creating a Pull Request": "创建 Pull Request",
    "Opening a PR": "打开 PR",
    "Reviewing a PR": "审查 PR",
    "CI Checks": "CI 检查",
    "Before You Start": "开始之前",
    "After the PR": "PR 之后",
    "Branch Naming": "分支命名",
    "Commit Messages": "提交信息",
}

# 部分标题前缀翻译（如 "## Overview of Features" 中的" Overview of"）
HEADING_PREFIX_TRANS = {
    "Overview of": "概述：",
    "Introduction to": "介绍：",
    "Guide to": "指南：",
    "How to ": "如何",
    "About ": "关于",
}

# ============================================================
# 2. YAML 字段翻译
# ============================================================
# YAML tag 翻译
TAG_TRANS = {
    "windows": "Windows",
    "setup": "设置",
    "portable": "便携版",
    "environment": "环境",
    "path": "路径",
    "terminal": "终端",
    "powershell": "PowerShell",
    "fonts": "字体",
    "testing": "测试",
    "tdd": "TDD",
    "development": "开发",
    "quality": "质量",
    "debugging": "调试",
    "troubleshooting": "故障排除",
    "problem-solving": "问题解决",
    "root-cause": "根因分析",
    "investigation": "调查",
    "git": "Git",
    "github": "GitHub",
    "pull-requests": "Pull Request",
    "code-review": "代码审查",
    "automation": "自动化",
    "merge": "合并",
    "ci/cd": "CI/CD",
    "research": "研究",
    "paper": "论文",
    "academic": "学术",
    "ml": "机器学习",
    "llm": "LLM",
    "inference": "推理",
    "quantization": "量化",
    "model": "模型",
    "deployment": "部署",
    "fine-tuning": "微调",
    "training": "训练",
    "evaluation": "评估",
    "pipeline": "流水线",
    "data": "数据",
    "visualization": "可视化",
    "creative": "创意",
    "design": "设计",
    "image": "图像",
    "video": "视频",
    "audio": "音频",
    "ascii": "ASCII",
    "diagram": "图表",
    "architecture": "架构",
    "note-taking": "笔记",
    "productivity": "效率",
    "email": "邮件",
    "smart-home": "智能家居",
    "automation-testing": "自动化测试",
    "security": "安全",
    "docs": "文档",
    "api": "API",
    "cli": "CLI",
    "mcp": "MCP",
    "plugin": "插件",
    "integration": "集成",
    "backup": "备份",
    "monitoring": "监控",
    "notification": "通知",
    "cron": "定时任务",
    "scheduler": "调度器",
}

# 常见的 trigger 短语翻译
TRIGGER_PHRASE_TRANS = {
    "User asks to": "用户要求",
    "User needs to": "用户需要",
    "User wants": "用户希望",
    "User is working": "用户正在",
    "User asks about": "用户询问",
    "User wants to run": "用户想要运行",
    "User wants to create": "用户想要创建",
    "User reports that": "用户报告",
    "When user says": "当用户说",
    "When user asks": "当用户问",
    "When user needs": "当用户需要",
    "For ANY technical issue": "适用于任何技术问题",
    "Use for ANY": "适用于任何",
    "Test": "测试",
    "Tests": "测试",
    "Bugs": "Bug",
    "Bug": "Bug",
    "Unexpected behavior": "异常行为",
    "Performance problems": "性能问题",
    "Performance": "性能",
    "Build failures": "构建失败",
    "Integration issues": "集成问题",
    "Especially when": "尤其是在以下情况",
    "Use this ESPECIALLY when": "尤其适用于以下情况",
    "Don't skip when": "以下情况也不应跳过",
    "Under time pressure": "时间紧迫时",
    "Seems obvious": "看似显而易见",
    "You've already tried": "已经尝试过",
    "Previous fix didn't work": "之前的修复无效",
    "You don't fully understand": "未完全理解问题",
    "Issue seems simple": "问题看似简单",
    "You're in a hurry": "赶时间时",
    "Someone wants it fixed NOW": "有人要求立即修复时",
}


# ============================================================
# 3. 常用正文段落/短语翻译
# ============================================================
BODY_PHRASE_TRANS = {
    "Random fixes waste time and create new bugs. Quick patches mask underlying issues.":
        "随机修复浪费时间并制造新 Bug。快速补丁只会掩盖根本问题。",
    "Write the test first. Watch it fail. Write minimal code to pass.":
        "先写测试。看它失败。写最少代码让它通过。",
    "If you didn't watch the test fail, you don't know if it tests the right thing.":
        "如果你没看到测试失败，你就无法确定它测的是否正确。",
    "ALWAYS find root cause before attempting fixes. Symptom fixes are failure.":
        "在尝试修复之前务必找到根本原因。治标不治本是失败的。",
    "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST":
        "未经根因调查，不得进行修复",
    "Complete guide for managing the PR lifecycle.":
        "管理 PR 生命周期的完整指南。",
    "Each section shows the `gh` way first, then the `git` + `curl` fallback for machines without `gh`.":
        "每个部分先展示 `gh` 方式，再展示没有 `gh` 时的 `git` + `curl` 备选方案。",
    "Authenticated with GitHub": "已通过 GitHub 认证",
    "Inside a git repository with a GitHub remote": "在包含 GitHub 远程仓库的 git 仓库内",
    "Guide for setting up Windows development tools from portable/zip distributions — no MSI, MSIX, or winget required.":
        "从便携版/压缩包分发版安装 Windows 开发工具的指南 — 无需 MSI、MSIX 或 winget。",
    "Many Windows tools (PowerShell, Windows Terminal, VS Code, etc.) offer a zip/portable download alongside the installer.":
        "许多 Windows 工具（PowerShell、Windows Terminal、VS Code 等）除了安装程序外，还提供压缩包/便携版下载。",
    "The zip version is a self-contained directory you can place anywhere.":
        "压缩包版本是一个可以放在任何位置的独立目录。",
    "There is no installer to run — the tool works as soon as you run the .exe.":
        "无需运行安装程序 — 只要运行 .exe 即可使用。",
    "Since you're in git-bash, use PowerShell to update the User-level PATH:":
        "由于你在 git-bash 中，请使用 PowerShell 更新用户级 PATH：",
}


# ============================================================
# 翻译核心逻辑
# ============================================================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def translate_heading(heading_text):
    """翻译 Markdown 标题文本"""
    stripped = heading_text.strip()
    # 精确匹配
    if stripped in HEADING_TRANS:
        return HEADING_TRANS[stripped]
    # 前缀匹配
    for prefix, replacement in HEADING_PREFIX_TRANS.items():
        if stripped.startswith(prefix):
            rest = stripped[len(prefix):].strip()
            return replacement + rest
    # 尝试移除括号内容再匹配
    base = re.sub(r'\s*\(.*?\)\s*$', '', stripped).strip()
    if base in HEADING_TRANS:
        paren = stripped[len(base):]
        return HEADING_TRANS[base] + paren
    return stripped  # 不翻译

def translate_triggers(triggers_text, indent=""):
    """翻译 YAML triggers 列表"""
    translations = []
    for item in triggers_text:
        translated = item
        # 按优先级替换已知短语
        for eng, cn in sorted(TRIGGER_PHRASE_TRANS.items(), key=lambda x: -len(x[0])):
            if translated.startswith(eng):
                translated = cn + translated[len(eng):]
                break
        translations.append(translated)
    return translations

def translate_tags(tags_text):
    """翻译 YAML tags 列表"""
    translations = []
    for tag in tags_text:
        tag_lower = tag.lower()
        if tag_lower in TAG_TRANS:
            translations.append(TAG_TRANS[tag_lower])
        else:
            translations.append(tag)
    return translations

def translate_body_paragraph(text):
    """翻译正文段落中的已知短语"""
    # 不处理纯空行和代码行
    stripped = text.strip()
    if not stripped or stripped.startswith('```') or stripped.startswith('|'):
        return text
    # 检查是否在代码块内（由调用者处理）
    # 精确短语匹配
    for eng, cn in sorted(BODY_PHRASE_TRANS.items(), key=lambda x: -len(x[0])):
        if stripped == eng:
            return text.replace(stripped, cn)
    return text

def process_skill_file(skill_path, skill_name, state, force=False):
    """处理单个 SKILL.md 文件 - 全面翻译"""
    if skill_name in state and not force:
        return False, "already_translated"

    with open(skill_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 分离 YAML 前置元数据和正文
    yaml_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not yaml_match:
        return False, "no_yaml"

    yaml_text = yaml_match.group(1)
    frontmatter = yaml_match.group(0)
    body = content[len(frontmatter):]

    # ---- 翻译 YAML ----
    new_yaml = yaml_text

    # 翻译 description 字段
    new_yaml = re.sub(
        r'^description:\s*"([^"]*)"',
        lambda m: f'description: "{m.group(1)}"',  # 保持原样（已翻译）
        new_yaml,
        flags=re.MULTILINE
    )

    # 翻译 tags 字段中的标签
    def translate_yaml_tags(match):
        tag_list = match.group(1)
        tags = re.findall(r'\[?([\w-]+)\]?', tag_list)
        translated = [TAG_TRANS.get(t.lower(), t) for t in tags if t]
        return f"tags: [{', '.join(translated)}]"
    new_yaml = re.sub(
        r'^tags:\s*\[([^\]]+)\]',
        translate_yaml_tags,
        new_yaml,
        flags=re.MULTILINE
    )

    # 翻译 triggers 列表
    trigger_lines = []
    in_triggers = False
    for line in new_yaml.split('\n'):
        if re.match(r'^triggers:', line):
            in_triggers = True
            trigger_lines.append(line)
        elif in_triggers:
            m = re.match(r'^(\s+-\s+)(.*)', line)
            if m:
                indent = m.group(1)
                trig_text = m.group(2)
                # 翻译 trigger 文本
                for eng, cn in sorted(TRIGGER_PHRASE_TRANS.items(), key=lambda x: -len(x[0])):
                    if trig_text.startswith(eng):
                        trig_text = cn + trig_text[len(eng):]
                        break
                trigger_lines.append(f"{indent}{trig_text}")
            else:
                in_triggers = False
                trigger_lines.append(line)
        else:
            trigger_lines.append(line)
    new_yaml = '\n'.join(trigger_lines)

    # 重建 YAML 前置元数据
    new_frontmatter = f"---\n{new_yaml}\n---"

    # ---- 翻译 Markdown 正文 ----
    lines = body.split('\n')
    new_lines = []
    in_code_block = False
    in_table = False
    changes_made = 0

    for line in lines:
        stripped = line.strip()

        # 跟踪代码块状态
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            new_lines.append(line)
            continue

        # 跟踪表格
        if stripped.startswith('|') and stripped.endswith('|'):
            in_table = True
            new_lines.append(line)
            continue
        elif in_table and not stripped.startswith('|'):
            in_table = False

        if in_code_block or in_table:
            new_lines.append(line)
            continue

        # 翻译标题
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            h_level = heading_match.group(1)
            h_text = heading_match.group(2)
            new_h = translate_heading(h_text)
            if new_h != h_text:
                changes_made += 1
            new_lines.append(f"{h_level} {new_h}")
            continue

        # 翻译常见短语 (但不包括行内代码、链接、URL)
        if '{' not in stripped and '}' not in stripped and '[' not in stripped:
            for eng, cn in sorted(BODY_PHRASE_TRANS.items(), key=lambda x: -len(x[0])):
                if stripped == eng:
                    new_lines.append(line.replace(stripped, cn))
                    changes_made += 1
                    break
                elif stripped.startswith(eng):
                    suffix = stripped[len(eng):]
                    indent = line[:len(line) - len(stripped)]
                    new_lines.append(f"{indent}{cn}{suffix}")
                    changes_made += 1
                    break
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    new_body = '\n'.join(new_lines)

    # ---- 写入文件（先备份） ----
    new_content = new_frontmatter + new_body
    if new_content != content or changes_made > 0:
        _backup_file(skill_path, subdir="skills")
        with open(skill_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        state[skill_name] = datetime.now().isoformat()
        return True, "translated"
    else:
        return False, "no_changes"


def main():
    print("=" * 60)
    print("Hermes 技能全面中文翻译工具 v2.0")
    print("=" * 60)

    if not os.path.exists(SKILLS_DIR):
        print(f"✗ 技能目录不存在: {SKILLS_DIR}")
        return

    state = load_state()
    translated = 0
    skipped = 0
    errors = 0

    # 收集所有技能文件
    skills_found = []
    for root, dirs, files in os.walk(SKILLS_DIR):
        if 'SKILL.md' not in files:
            continue
        skill_path = os.path.join(root, 'SKILL.md')
        skill_name = os.path.basename(root)
        skills_found.append((skill_path, skill_name))

    skills_found.sort(key=lambda x: x[1])
    print(f"\n共发现 {len(skills_found)} 个技能文件\n")

    for idx, (skill_path, skill_name) in enumerate(skills_found, 1):
        try:
            ok, reason = process_skill_file(skill_path, skill_name, state)
            if ok:
                print(f"  ✓ [{idx}/{len(skills_found)}] {skill_name} - 已翻译")
                translated += 1
            else:
                if reason == "already_translated":
                    skipped += 1
                else:
                    print(f"  → [{idx}/{len(skills_found)}] {skill_name} - {reason}")
                    skipped += 1
        except Exception as e:
            print(f"  ✗ [{idx}/{len(skills_found)}] {skill_name} - 错误: {e}")
            errors += 1

    save_state(state)

    print(f"\n{'=' * 60}")
    print(f"完成! 翻译: {translated}, 跳过: {skipped}, 错误: {errors}")
    print(f"状态记录: {STATE_FILE}")
    print(f"提示: 再次运行会跳过已翻译的。")
    print(f"如果技能更新后需要重新翻译，请删除 {STATE_FILE} 再运行本脚本。")
    print(f"{'=' * 60}")


# ============================================================
# 4. 源文件界面翻译补丁
# ============================================================
# 修复 Hermes 源文件（banner.py、branding.tsx、theme.ts、verbs.ts、display.py）
# 中的硬编码英文 UI 文本，翻译为中文。
# 注意：这些修改会在 Hermes 更新后被覆盖。

HERMES_AGENT_DIR = os.path.join(HERMES_HOME, "hermes-agent")

# ============================================================
# tips.py 完整中文翻译内容
# ============================================================
TIPS_TRANSLATED_CONTENT = '''"""CLI 会话启动时展示的随机提示，帮助用户发现功能。"""

import random


# ---------------------------------------------------------------------------
# 提示语库 —— 涵盖斜杠命令、CLI 标志、配置、快捷键、工具、网关、技能、
# 配置文件和工作流技巧。
# ---------------------------------------------------------------------------

TIPS = [
    # --- 斜杠命令 ---
    "/background <prompt>（别名 /bg 或 /btw）在独立会话中执行任务，当前会话不受影响。",
    "/branch 复制当前会话，让你可以探索不同方向而不丢失进度。",
    "/compress 手动压缩对话上下文 —— 内容太长时很有用。",
    "/rollback 列出文件系统检查点 —— 可还原代理修改过的文件到任意之前的状态。",
    "/rollback diff 2 预览检查点 2 以来的变更，无需实际还原。",
    "/rollback 2 src/file.py 从指定检查点还原单个文件。",
    '/title "我的项目" 为会话命名 —— 之后可用 /resume 或 hermes -c 恢复。',
    "/resume 恢复之前命名的会话，从上次中断处继续。",
    "/queue <prompt> 将消息排队到下一轮，不会打断当前轮次。",
    "/undo 移除对话中最后一轮用户/助手的交流。",
    "/retry 重发上一条消息 —— 当代理回复不太对劲时很有用。",
    "/verbose 切换工具进度显示模式：关闭 → 新 → 全部 → 详细。",
    "/reasoning high 增加模型的思考深度。/reasoning show 显示推理过程。",
    "/fast 切换优先处理模式，加快 API 响应速度（取决于提供商）。",
    "/yolo 在当前会话剩余时间内跳过所有危险命令的审批提示。",
    "/model 让你在会话中切换模型 —— 试试 /model sonnet 或 /model gpt-5。",
    "/model --global 永久更改默认模型。",
    '/personality pirate 设置有趣的个性 —— 从 kawaii 到 shakespeare 共 14 种内置选项。',
    "/skin 切换 CLI 主题 —— 试试 ares、mono、slate、poseidon 或 charizard。",
    "/statusbar 切换持久状态栏，显示模型、令牌数、上下文填充百分比、花费和耗时。",
    "/tools disable browser 临时移除当前会话的浏览器工具。",
    "/browser connect 通过 CDP 将浏览器工具附加到正在运行的 Chromium 系浏览器。",
    "/plugins 列出已安装的插件及其状态。",
    "/cron 管理计划任务 —— 设置定时提示，可投递到任意平台。",
    "/reload-mcp 热重载 MCP 服务器配置，无需重启。",
    "/usage 显示令牌用量、费用明细和会话时长。",
    "/insights 显示最近 30 天的使用分析。",
    "/paste 检查剪贴板中的图片并附加到下一条消息中。",
    "/profile 显示当前使用的配置文件和其主目录。",
    "/config 快速一览当前配置。",
    "/stop 终止代理启动的所有正在运行的后台进程。",

    # --- @ 上下文引用 ---
    "@file:path/to/file.py 将文件内容直接注入消息中。",
    "@file:main.py:10-50 只注入文件的第 10-50 行。",
    "@folder:src/ 注入目录树列表。",
    "@diff 将未暂存的 git 变更注入消息。",
    "@staged 将已暂存的 git 变更（git diff --staged）注入消息。",
    "@git:5 注入最近 5 次提交及完整补丁。",
    "@url:https://example.com 获取网页内容并注入消息。",
    "输入 @ 会触发文件系统路径补全 —— 可交互式导航到任意文件。",
    '组合多个引用："Review @file:main.py and @file:test.py for consistency."',

    # --- 快捷键 ---
    "Alt+Enter 插入换行用于多行输入。（Windows Terminal 拦截 Alt+Enter —— 请改用 Ctrl+Enter。）",
    "Ctrl+C 中断代理。2 秒内按两次可强制退出。",
    "Ctrl+Z 将 Hermes 挂起到后台 —— 在 shell 中运行 fg 恢复。",
    "Tab 接受自动建议的幽灵文本或自动补全斜杠命令。",
    "在代理工作时输入新消息可以中断并重定向它。",
    "Alt+V 从剪贴板粘贴图片到对话中。",
    "粘贴 5 行以上会自动保存到文件，并插入紧凑的引用。",

    # --- CLI 标志 ---
    "hermes -c 恢复最近的 CLI 会话。hermes -c \\"项目名称\\" 按标题恢复。",
    "hermes -w 创建独立的 git worktree —— 适合并行代理工作流。",
    'hermes -w -q "修复 issue #42" 结合 worktree 隔离与一次性查询。',
    "hermes chat -t web,terminal 只启用特定的工具集，创建聚焦的会话。",
    "hermes chat -s github-pr-workflow 启动时预加载技能。",
    'hermes chat -q "query" 运行一次性非交互查询后退出。',
    "hermes chat --max-turns 200 覆盖默认的每轮 90 次迭代限制。",
    "hermes chat --checkpoints 在每次破坏性文件变更前启用文件系统快照。",
    "hermes --yolo 在整个会话中跳过所有危险命令审批提示。",
    "hermes chat --source telegram 为会话打标签，便于在 hermes sessions list 中筛选。",
    "hermes -p work chat 使用指定配置文件运行，不更改默认配置。",

    # --- CLI 子命令 ---
    "hermes doctor --fix 诊断并自动修复配置和依赖问题。",
    "hermes dump 输出紧凑的设置摘要 —— 适合用于 bug 报告。",
    "hermes config set KEY VALUE 自动将密钥路由到 .env，其他内容路由到 config.yaml。",
    "hermes config edit 在默认编辑器中打开 config.yaml。",
    "hermes config check 扫描缺失或过期的配置选项。",
    "hermes sessions browse 打开交互式会话选择器，支持搜索。",
    "hermes sessions stats 按平台显示会话数量和数据库大小。",
    "hermes sessions prune --older-than 30 清理旧会话。",
    "hermes skills search react --source skills-sh 搜索 skills.sh 公共目录。",
    "hermes skills check 扫描已安装的 hub 技能是否有上游更新。",
    "hermes skills tap add myorg/skills-repo 添加自定义 GitHub 技能源。",
    "hermes skills snapshot export setup.json 导出技能配置用于备份或分享。",
    "hermes mcp add github --command npx 从命令行添加 MCP 服务器。",
    "hermes mcp serve 让 Hermes 自身作为 MCP 服务器供其他代理使用。",
    "hermes auth add 让你添加多个 API 密钥用于凭证池轮换。",
    "hermes completion bash >> ~/.bashrc 为所有命令和配置文件启用 Tab 补全。",
    "hermes logs -f 实时追踪 agent.log。--level WARNING --since 1h 可过滤输出。",
    "hermes backup 创建整个 Hermes 主目录的 zip 备份。",
    "hermes profile create coder 创建隔离的配置文件，可变成独立命令。",
    "hermes profile create work --clone 将当前配置和密钥复制到新配置文件。",
    "hermes update 自动将新捆绑的技能同步到所有配置文件。",
    "hermes gateway install 将 Hermes 设置为系统服务（systemd/launchd）。",
    "hermes memory setup 让你配置外部记忆提供商（Honcho、Mem0 等）。",
    "hermes webhook subscribe 创建事件驱动的 webhook 路由，支持 HMAC 验证。",
    "节省费用：hermes tools 可禁用不用的工具，hermes skills config 可精简技能。",
    "/reasoning low 或 /reasoning minimal 将思考深度降至默认（medium）以下 —— 更快、更便宜的响应。",
    "hermes models routes 将视觉、压缩和辅助任务路由到更便宜的模型 —— 将后台令牌成本降低 85% 以上，同时不影响主聊天模型。",

    # --- 配置 ---
    "设置 display.bell_on_complete: true 在 config.yaml 中，长任务完成时会听到提示音。",
    "设置 display.streaming: true 可实时看到模型生成的令牌。",
    "设置 display.show_reasoning: true 可观察模型的思维链推理过程。",
    "设置 display.compact: true 可减少输出中的空白，信息更密集。",
    "设置 display.busy_input_mode: queue 可将消息排队而不是打断代理；设为 steer 可通过 /steer 在运行中注入消息。",
    "设置 display.resume_display: minimal 可在恢复会话时跳过完整的对话回顾。",
    "设置 compression.threshold: 0.50 控制自动压缩触发的时机（默认：上下文 50%）。",
    "设置 agent.max_turns: 200 让代理在每轮中执行更多工具调用步骤。",
    "设置 file_read_max_chars: 200000 提高每次 read_file 调用的最大内容量。",
    "设置 approvals.mode: smart 让 LLM 自动批准安全命令并自动拒绝危险命令。",
    "在 config.yaml 中设置 fallback_model，可在提供商故障时自动切换到备份提供商。",
    "设置 privacy.redact_pii: true 在发送到 LLM 前对用户 ID 和电话号码进行哈希处理。",
    "设置 browser.record_sessions: true 自动将浏览器会话录制为 WebM 视频。",
    "在 config.yaml 中设置 worktree: true 可始终创建 git worktree（等同于 hermes -w）。",
    "设置 security.website_blocklist.enabled: true 可阻止特定域名被 web 工具访问。",
    "设置 cron.wrap_response: false 可投递原始代理输出，不带 cron 页眉/页脚。",
    "HERMES_TIMEZONE 可用任意 IANA 时区字符串覆盖服务器时区。",
    "config.yaml 中支持环境变量替换：使用 ${VAR_NAME} 语法。",
    "config.yaml 中的快速命令（Quick commands）可即时执行 shell 命令，零令牌消耗。",
    "自定义个性可在 config.yaml 的 agent.personalities 下定义。",
    "provider_routing 控制 OpenRouter 的提供商排序、白名单和黑名单。",

    # --- 工具与能力 ---
    "execute_code 可以运行调用 Hermes 工具的 Python 脚本 —— 结果不会进入上下文窗口。",
    "delegate_task 默认可生成最多 3 个并发子代理（delegation.max_concurrent_children），每个有独立的上下文。",
    "web_extract 支持 PDF URL —— 传入任意 PDF 链接，会转为 Markdown。",
    "search_files 基于 ripgrep，比 grep 更快 —— 用它替代终端中的 grep。",
    "patch 使用 9 种模糊匹配策略，细微的空白差异不会破坏编辑。",
    "patch 支持 V4A 格式，一次调用即可批量编辑多个文件。",
    "read_file 在文件未找到时会建议相似的文件名。",
    "read_file 会自动去重 —— 重复读取未变更的文件会返回轻量存根。",
    "browser_vision 截取屏幕截图并用 AI 分析 —— 适用于验证码和视觉内容。",
    "browser_console 可以在页面上下文中执行 JavaScript 表达式。",
    "image_generate 使用 FLUX 2 Pro 创建图像，并自动 2 倍放大。",
    "text_to_speech 将文本转为音频 —— 在 Telegram 上以语音气泡播放。",
    "send_message 可在会话中向任意已连接的消息平台发送消息。",
    "todo 工具帮助代理在会话期间跟踪复杂的多步骤任务。",
    "session_search 可对所有历史对话进行全文搜索。",
    "代理会自动将偏好、修正和环境信息保存到记忆。",
    "mixture_of_agents 将难题路由到 4 个前沿 LLM 协作解决。",
    "终端命令支持后台模式（带 notify_on_complete）用于长时间运行的任务。",
    "终端后台进程支持 watch_patterns，可在特定输出行时发出提醒。",
    "终端工具支持 6 种后端：本地、Docker、SSH、Modal、Daytona 和 Singularity。",

    # --- 配置文件 ---
    "每个配置文件都有独立的配置、API 密钥、记忆、会话、技能和定时任务。",
    "配置文件名称会成为 shell 命令 —— 'hermes profile create coder' 会创建 'coder' 命令。",
    "hermes profile export coder -o backup.tar.gz 创建可移植的配置文件归档。",
    "如果两个配置文件意外共享了同一个机器人令牌，第二个网关会收到明确错误并被阻止。",

    # --- 会话 ---
    "会话在第一次交流后会自动生成描述性标题 —— 无需手动命名。",
    "会话标题支持谱系：\\"我的项目\\" → \\"我的项目 #2\\" → \\"我的项目 #3\\"。",
    "退出时，Hermes 会打印包含会话 ID 和统计数据的恢复命令。",
    "hermes sessions export backup.jsonl 导出所有会话用于备份或分析。",
    "hermes -r SESSION_ID 可按 ID 恢复任意历史会话。",

    # --- 记忆 ---
    "记忆是冻结的快照 —— 变更只会在下次会话启动时出现在系统提示中。",
    "记忆条目会自动扫描提示注入和数据泄露模式。",
    "代理有两种记忆存储：个人笔记（约 2200 字符）和用户画像（约 1375 字符）。",
    '你对代理的纠正（"不，这样做"）通常会自动保存到记忆中。',

    # --- 技能 ---
    "超过 80 个内置技能，涵盖 GitHub、创意、MLOps、生产力、研究等领域。",
    "每个已安装的技能会自动成为斜杠命令 —— 输入 / 可查看全部。",
    "hermes skills install official/security/1password 从仓库安装可选技能。",
    "技能可以限制特定操作系统平台 —— 有些只在 macOS 或 Linux 上加载。",
    "config.yaml 中的 skills.external_dirs 可从自定义目录加载技能。",
    "代理可以使用 skill_manage 创建自己的技能作为过程性记忆。",
    "plan 技能将 Markdown 计划保存到活动工作区的 .hermes/plans/ 目录。",

    # --- 定时任务与调度 ---
    'hermes cron add --skill blogwatcher "检查新文章" —— 定时任务可附加技能。',
    "定时任务投递目标包括 Telegram、Discord、Slack、Email、SMS 等 12+ 平台。",
    "如果定时任务响应以 [SILENT] 开头，则禁止投递 —— 适用于纯监控任务。",
    "定时任务支持相对延迟（30m）、间隔（every 2h）、cron 表达式和 ISO 时间戳。",
    "定时任务在完全全新的代理会话中运行 —— 提示必须自包含。",

    # --- 语音 ---
    "如果安装了 faster-whisper（免费的本地语音转文字），语音模式不需要任何 API 密钥。",
    "五种 TTS 提供商可选：Edge TTS（免费）、ElevenLabs、OpenAI、NeuTTS（免费本地）、MiniMax。",
    "/voice on 在 CLI 中启用语音模式。Ctrl+B 切换按键通话录音。",
    "流式 TTS 可在生成过程中逐句播放语音 —— 无需等待完整响应。",
    "Telegram、Discord、WhatsApp 和 Slack 上的语音消息会自动转写。",

    # --- 网关与消息 ---
    "Hermes 运行在 21 个消息平台上：Telegram、Discord、Slack、WhatsApp、Signal、Matrix、IRC、Microsoft Teams、电子邮件等。",
    "hermes gateway install 将其设置为开机启动的系统服务。",
    "钉钉使用流模式 —— 无需 Webhook 或公网 URL。",
    "BlueBubbles 通过本地 macOS 服务器将 iMessage 接入 Hermes。",
    "Webhook 路由支持 HMAC 验证、速率限制和事件过滤。",
    "API 服务器暴露出兼容 OpenAI 的端点，可与 Open WebUI 和 LibreChat 配合使用。",
    "Discord 语音频道模式：机器人加入语音频道、转写语音并回复。",
    "group_sessions_per_user: true 在群聊中为每个人分配独立会话。",
    "/sethome 将当前聊天标记为定时任务投递的主频道。",
    "网关支持基于不活跃时间的超时 —— 活跃代理可无限运行。",

    # --- 安全 ---
    "危险命令审批有 4 级：once（一次）、session（会话内）、always（永久白名单）、deny（拒绝）。",
    "智能审批模式使用 LLM 自动批准安全命令并标记危险命令。",
    "SSRF 保护阻止私网、回环、链路本地和云元数据地址。",
    "Tirith 执行前扫描可检测同形 URL 欺骗和管道到解释器模式。",
    "MCP 子进程收到过滤后的环境变量 —— 只有安全系统变量通过。",
    "上下文文件（.hermes.md、AGENTS.md）在加载前会进行安全扫描，防止提示注入。",
    "config.yaml 中的 command_allowlist 可永久批准特定的 shell 命令模式。",

    # --- 上下文与压缩 ---
    "上下文在达到阈值时自动压缩 —— 记忆被刷新，历史被摘要化。",
    "状态栏随上下文填充量依次变为黄色、橙色、红色。",
    "SOUL.md 是代理的主要身份文件 —— 自定义它以塑造行为。",
    "Hermes 按顺序加载项目上下文：.hermes.md、AGENTS.md、CLAUDE.md 或 .cursorrules（找到即止）。",
    "子目录中的 AGENTS.md 文件会在代理进入文件夹时渐进发现。",
    "上下文文件上限为 20,000 字符，超出部分智能截取首尾。",

    # --- 浏览器 ---
    "五种浏览器提供商：本地 Chromium、Browserbase、Browser Use、Camofox 和 Firecrawl。",
    "Camofox 是反检测浏览器 —— 基于 Firefox 分支，带有 C++ 指纹伪造。",
    "browser_navigate 会自动返回页面快照 —— 无需再调用 browser_snapshot。",
    "browser_vision 设置 annotate=true 可为交互元素叠加编号标签。",

    # --- MCP ---
    "hermes mcp 打开交互式选择器，可一键安装 Nous 批准的 MCP。",
    "hermes mcp catalog 列出仓库附带的 Nous 批准 MCP 服务器。",
    "hermes mcp install <name> 安装目录条目，提示输入凭证，并让你选择启用哪些工具。",
    "MCP 服务器在 config.yaml 中配置 —— 支持 stdio 和 HTTP 传输方式。",
    "每个服务器的工具过滤：tools.include 设置白名单，tools.exclude 设置黑名单。",
    "MCP 服务器在运行时自动生成工具集 —— hermes tools 可按平台切换。",
    "MCP OAuth 支持：auth: oauth 启用基于浏览器的 PKCE 授权。",

    # --- 检查点与回滚 ---
    "文件未修改时检查点零开销 —— 默认启用。",
    "回滚前会自动保存快照，因此可以撤销撤销操作。",
    "/rollback 同时会撤销对话回合，这样代理不会记得已回滚的变更。",
    "检查点使用 ~/.hermes/checkpoints/ 中的影子仓库 —— 不会触碰项目的 .git。",

    # --- 批量与数据 ---
    "batch_runner.py 可并行处理数百个提示，用于训练数据生成。",
    "hermes chat -Q 启用静默模式，用于编程调用 —— 隐藏横幅和旋转指示器。",
    "轨迹保存（--save-trajectories）捕获完整的工具使用记录，用于模型训练。",

    # --- 插件 ---
    "三种插件类型：通用（工具/钩子）、记忆提供商和上下文引擎。",
    "hermes plugins install owner/repo 直接从 GitHub 安装插件。",
    "8 种外部记忆提供商可用：Honcho、OpenViking、Mem0、Hindsight 等。",
    "插件钩子包括 pre/post_tool_call、pre/post_llm_call 和 transform_terminal_output（用于输出规范化）。",

    # --- 杂项 ---
    "提示缓存（Anthropic）通过重用缓存的系统提示前缀降低成本。",
    "代理在后台线程中自动生成会话标题 —— 零延迟影响。",
    "智能模型路由可自动将简单查询路由到更便宜的模型。",
    "斜杠命令支持前缀匹配：/h 解析为 /help，/mod 解析为 /model。",
    "将文件路径拖入终端可自动附加图片或作为上下文发送。",
    "仓库根目录下的 .worktreeinclude 列出应复制到 worktree 中的 gitignore 文件。",
    "hermes acp 将 Hermes 作为 ACP 服务器运行，用于 VS Code、Zed 和 JetBrains 集成。",
    "自定义提供商：在 config.yaml 的 custom_providers 下保存命名端点。",
    "HERMES_EPHEMERAL_SYSTEM_PROMPT 注入永不保存到历史的系统提示。",
    "credential_pool_strategies 支持 fill_first、round_robin、least_used 和 random 轮换策略。",
    "hermes auth add nous 或 hermes auth add openai-codex 设置基于 OAuth 的提供商。",
    "API 服务器同时支持 Chat Completions 和 Responses API，带服务端状态。",
    "设置 tool_preview_length: 0 可在旋转指示器的活动信息流中显示完整文件路径。",
    "hermes status --deep 对所有组件运行更深的诊断检查。",

    # --- 隐藏技巧与高级用户技巧 ---
    "定时任务可以附加 Python 脚本（--script），其 stdout 会作为上下文注入提示。",
    "定时任务脚本存放在 ~/.hermes/scripts/，在代理之前运行 —— 非常适合数据收集管道。",
    "config.yaml 中的 prefill_messages_file 可向每次 API 调用注入 few-shot 示例，永不保存到历史。",
    "SOUL.md 完全替换代理的默认身份 —— 重写它让 Hermes 成为你自己的。",
    "SOUL.md 在首次运行时自动生成默认个性。编辑它以定制。",
    "/compress <关注主题> 将约 60-70% 的摘要预算分配给指定主题，积极裁剪其余内容。",
    "第二次及后续压缩时，压缩器会更新之前的摘要而不是从头开始。",
    "在网关会话重置前，Hermes 会在后台自动将重要事实刷新到记忆。",
    "config.yaml 中的 network.force_ipv4: true 可修复 IPv6 故障服务器上的卡顿问题 —— 会 monkey-patch socket。",
    "终端工具会注解常见退出码：grep 返回 1 = '未找到匹配（非错误）'。",
    "失败的前景终端命令会自动重试最多 3 次，采用指数退避（2s、4s、8s）。",
    "裸 sudo 命令会自动重写为从 .env 传入 SUDO_PASSWORD —— 无需交互式提示。",
    "execute_code 内置辅助函数：json_parse()（宽容解析）、shell_quote() 和 retry()（带退避）。",
    "execute_code 的 7 个沙箱工具（web_search、terminal、read/write/search/patch）使用 RPC —— 从不进入上下文。",
    "同一文件区域被读取 3 次以上会触发警告。4 次以上会被硬性阻止，防止循环。",
    "write_file 和 patch 会检测文件自上次读取后是否被外部修改，并提示过期。",
    "V4A 补丁格式支持添加文件、删除文件和移动文件指令 —— 不仅仅是更新。",
    "MCP 服务器可以通过采样请求 LLM 补全 —— 代理成为服务器的工具。",
    "MCP 服务器发送 notifications/tools/list_changed 可触发自动工具重新注册，无需重启。",
    "delegate_task 设置 acp_command: 'claude' 可在任意平台将 Claude Code 作为子代理生成。",
    "委派有心跳线程 —— 子活动会传播到父进程，防止网关超时。",
    "当提供商返回 HTTP 402（需要付款）时，辅助客户端会自动回退到下一个提供商。",
    "agent.tool_use_enforcement 引导倾向于描述行为而不是调用工具的模型 —— GPT/Codex 自动启用。",
    "agent.restart_drain_timeout（默认 60s）让正在运行的代理在网关重启生效前完成。",
    "agent.api_max_retries（默认 3）控制代理重试失败 API 调用的次数 —— 降低它以实现快速回退。",
    "网关会缓存每个会话的 AIAgent 实例 —— 销毁此缓存会破坏 Anthropic 提示缓存。",
    "任意网站可通过 /.well-known/skills/index.json 暴露技能 —— 技能中心会自动发现它们。",
    "技能审计日志位于 ~/.hermes/skills/.hub/audit.log，记录每次安装和移除操作。",
    "过期的 git worktree 会自动清理：24-72 小时无未推送提交的 worktree 在启动时被修剪。",
    "配置文件通过 HERMES_HOME 限定 Hermes 状态；宿主机工具子进程保留真实的 HOME，除非 terminal.home_mode 设为 profile。",
    "HERMES_HOME_MODE 环境变量（八进制，如 0701）设置 Web 服务器遍历所需的自定义目录权限。",
    "容器模式：在 HERMES_HOME 中放置 .container-mode 文件，宿主 CLI 会自动在容器中执行。",
    "Ctrl+C 有 5 个优先级层级：取消录音 → 取消提示 → 取消选择器 → 中断代理 → 退出。",
    "代理运行期间的每次中断都会记录到 ~/.hermes/interrupt_debug.log，带时间戳。",
    "BROWSER_CDP_URL 可将浏览器工具连接到任意正在运行的 Chromium 系浏览器 —— 接受 WebSocket、HTTP 或 host:port。",
    "BROWSERBASE_ADVANCED_STEALTH=true 启用高级反检测，配合自定义 Chromium（Scale 套餐）。",
    "CLI 在宽度小于 80 列的终端中会自动切换到紧凑模式。",
    "快速命令支持两种类型：exec（直接运行 shell 命令）和 alias（重定向到另一命令）。",
    "每任务委派模型：config.yaml 中的 delegation.model 和 delegation.provider 可将子代理路由到更便宜的模型。",
    "delegation.reasoning_effort 可独立控制子代理的思考深度。",
    "config.yaml 中的 display.platforms 允许按平台设置显示覆盖：{telegram: {tool_progress: all}}。",
    "config.yaml 中的 human_delay.mode 模拟人类打字速度 —— 可配置 min_ms/max_ms 范围。",
    "配置版本迁移在加载时自动运行 —— 无需手动干预即可出现新的配置键。",
    "GPT 和 Codex 模型会获得专门系统提示指导，以增强工具纪律和强制工具使用。",
    "Gemini 模型会获得针对绝对路径、并行工具调用和非交互式命令的定制指令。",
    "config.yaml 中的 context.engine 可设置为插件名称，用于替代的上下文管理策略。",
    "令牌数超过 8000 的浏览器页面会由辅助 LLM 自动摘要后返回给代理。",
    "压缩器会进行廉价预处理：超过 200 字符的工具输出会在 LLM 运行前替换为占位符。",
    "当压缩失败时，进一步尝试会暂停 10 分钟，避免 API 频繁调用。",
    "过长的危险命令（>70 字符）在审批提示中会提供 'view' 选项，可先查看完整文本。",
    "音频电平可视化在语音录音期间显示 ▁▂▃▄▅▆▇ 条，基于麦克风 RMS 电平。",
    "配置文件名称不能与现有 PATH 二进制文件冲突 —— 'hermes profile create ls' 会被拒绝。",
    "hermes profile create backup --clone-all 复制所有内容（配置、密钥、SOUL.md、记忆、技能、会话）。",
    "语音录音键可通过 config.yaml 中的 voice.record_key 配置 —— 不仅限于 Ctrl+B。",
    ".cursorrules 和 .cursor/rules/*.mdc 文件会被自动检测并作为项目上下文加载。",
    '上下文文件支持检测 10+ 种提示注入模式 —— 不可见 Unicode、"忽略指令"、数据外泄尝试等。',
    "GPT-5 和 Codex 使用 'developer' 角色而不是消息格式中的 'system'。",
    "每任务辅助覆盖：config.yaml 中的 auxiliary.vision.provider、auxiliary.compression.model 等。",
    "辅助客户端将 'main' 视为提供商别名 —— 解析为实际的主提供商 + 模型。",
    "hermes claw migrate --dry-run 预览 OpenClaw 迁移，不写入任何内容。",
    "带引号或转义空格的粘贴文件路径会自动处理 —— 无需手动清理。",
    "斜杠命令不会触发大粘贴折叠 —— 带大参数的 /command 也能正常工作。",
    "在中断模式下，代理执行期间输入的斜杠命令会绕过中断逻辑并立即执行。",
    "HERMES_DEV=1 绕过容器模式检测，用于本地开发。",
    "每个 MCP 服务器都有自己的工具集（mcp-服务器名），可通过 hermes tools 独立开关。",
    "配置中的 MCP ${ENV_VAR} 占位符在服务器生成时解析 —— 包括来自 ~/.hermes/.env 的变量。",
    "来自受信任仓库（NousResearch）的技能获得 'trusted' 安全级别；社区技能会经过额外扫描。",
    "技能隔离区位于 ~/.hermes/skills/.hub/quarantine/，存放待安全审查的技能。",

    # --- 高级斜杠命令 ---
    '/steer <prompt> 在下次工具调用后注入一条备注 —— 在任务中调整方向而不中断。',
    '/goal <text> 设置持续性的 Ralph 循环目标 —— Hermes 自动一轮接一轮继续，直到评判器认为完成。',
    '/snapshot create [label] 保存 Hermes 配置的完整状态快照；/snapshot restore <id> 后可还原。',
    '/copy [N] 将最近一次助手回复复制到剪贴板；加数字则复制倒数第 N 次。',
    '/redraw 强制完全重绘 UI，修复 tmux 调整大小或鼠标选择后的终端漂移。',
    '/agents（别名 /tasks）显示当前会话中的活动代理和正在运行的后台任务。',
    '/footer 切换最终回复上的网关页脚，显示模型、上下文百分比和当前工作目录。',
    '/busy queue|steer|interrupt 控制 Hermes 工作时按 Enter 键的行为。',
    '/topic 在 Telegram DM 中启用用户管理的多会话主题模式 —— /topic <id> 可内联恢复历史会话。',
    '/approve session|always 以选择的信任范围运行待处理的危险命令；/deny 拒绝它。',
    '/restart 在排空活动运行后优雅重启网关，恢复后通知请求者。',
    '/kanban boards switch <slug> 从聊天内部切换活动的多项目看板。',
    '/reload 将 ~/.hermes/.env 重新加载到运行中的会话 —— 无需重启即可使用新的 API 密钥。',

    # --- 定时任务（no-agent 与脚本） ---
    'cronjob 设置 no_agent=True 可按计划运行脚本并直接发送 stdout —— 零令牌、零 LLM。',
    '定时任务脚本 stdout 为空表示静默触发 —— 不投递任何内容，适合阈值看门狗。',
    'HERMES_CRON_MAX_PARALLEL（默认 4）限制每个 tick 同时运行的定时任务数，防止突发占用过多密钥。',

    # --- 网关钩子 ---
    '网关钩子存放在 ~/.hermes/hooks/<name>/ 目录下，包含 HOOK.yaml + handler.py —— handler 函数必须命名为 `handle`。',
    '钩子事件包括 gateway:startup、session:start、agent:step 和 command:* 通配符订阅。',
    '放置 ~/.hermes/BOOT.md 清单并配合 gateway:startup 钩子，可在每次启动时以一次性代理运行它。',

    # --- 策展人 ---
    'hermes curator run --dry-run 预览策展人会归档或合并的内容，不实际修改任何内容。',
    'hermes curator pin <skill> 对技能进行硬围栏保护，防止自动归档和代理的 skill_manage 工具删除。',
    'hermes curator rollback 从运行前快照恢复技能 —— 备份位于 skills/.curator_backups/。',

    # --- 凭证池与路由 ---
    'hermes auth reset <provider> 清除指定凭证池上的所有冷却和耗尽标志。',
    'credential_pool_strategies.<provider>: round_robin 平均轮换密钥，而不是默认的 fill_first。',
    '为工具设置 use_gateway: true 可将 web、图像、TTS 或浏览器路由通过你的 Nous 订阅 —— 无需额外密钥。',
    'provider_routing.data_collection: deny 排除 OpenRouter 上存储数据的提供商。',
    'provider_routing.require_parameters: true 仅将请求路由到支持每个参数的服务商。',

    # --- TUI 与仪表盘 ---
    'HERMES_TUI_RESUME=1 在启动时自动重新连接到最近的 TUI 会话 —— SSH 断线后很方便。',
    "HERMES_TUI_THEME=light|dark|<hex> 在未设置 COLORFGBG 的终端上强制 TUI 主题。",
    '在 TUI 中按 Ctrl+G 或 Ctrl+X Ctrl+E 可在 $EDITOR 中打开输入缓冲区，用于长多行提示。',
    'TUI 可内联渲染 LaTeX —— $E=mc^2$ 会变成 Unicode 数学符号而不是原始 TeX。',
    'hermes dashboard 在 127.0.0.1:9119 启动本地 Web UI —— 零数据离开本地主机。',
    'hermes dashboard 通过 xterm.js 和 WebSocket PTY 在浏览器中嵌入完整的 Hermes TUI。',
    '在 ~/.hermes/dashboard-themes/ 中放置包含两个调色板颜色的 YAML 文件，即可重新设置整个仪表盘主题。',
    '仪表盘插件即插即用：manifest.json + JS 包放在 ~/.hermes/dashboard-plugins/ —— 无需 npm 构建。',
    '仪表盘主题中的 layoutVariant: cockpit 会添加 260px 左侧导轨，插件可通过 sidebar 插槽填充。',

    # --- 环境变量与配置开关 ---
    'config.yaml 中的 display.tool_progress_command: true 可在消息平台上暴露 /verbose；默认仅 CLI 可用。',
    'HERMES_BACKGROUND_NOTIFICATIONS=result 只在后台任务完成时通知（vs all/error/off）。',
    'HERMES_WRITE_SAFE_ROOT 将 write_file 和 patch 限制到目录前缀；在此之外写入需要审批。',
    'HERMES_IGNORE_RULES 跳过 AGENTS.md、SOUL.md、.cursorrules、记忆和预加载技能的自动注入。',
    'HERMES_ACCEPT_HOOKS 自动批准 config.yaml 中声明的未见过的 shell 钩子，无需 TTY 提示。',
    'auxiliary.goal_judge.model 将 /goal 评判器路由到便宜的快速模型，保持循环成本接近零。',
    '检查点会跳过文件数超过 50,000 的目录，避免在巨大单体仓库上执行缓慢的 git 操作。',

    # --- TTS ---
    'tts.provider: piper 在 CPU 上运行 44 语言本地 TTS —— 语音文件自动下载到 ~/.hermes/cache/piper-voices/。',
    'tts.providers.<name>.type: command 可连接任何 CLI TTS 引擎，使用 {input_path} 和 {output_path} 占位符。',

    # --- API 服务器与代理 ---
    'API_SERVER_ENABLED=true 在网关旁运行兼容 OpenAI 的端点，用于 Open WebUI 和 LibreChat。',
    'GATEWAY_PROXY_URL 运行拆分设置：平台 I/O 在本地，代理工作委派给远程 API 服务器。',

    # --- 平台特定 ---
    'MATRIX_DEVICE_ID 固定稳定的设备 ID 用于 E2EE —— 没有它，密钥每次启动都会轮换，历史解密会失效。',
    '设置 TELEGRAM_WEBHOOK_URL 时必须设置 TELEGRAM_WEBHOOK_SECRET —— 使用 openssl rand -hex 32 生成。',

    # --- 批量 ---
    'batch_runner.py --resume 通过文本内容匹配已完成的提示，因此数据集重新排序不会重复运行已完成的工作。',

    # --- 较少人知的斜杠命令 ---
    '/new（别名 /reset）在原地启动全新会话 —— 新会话 ID、干净历史，CLI 保持打开。',
    '/clear 清空终端屏幕并启动新会话 —— 一个快捷键实现视觉重置。',
    '/history 在不离开 CLI 的情况下内联打印当前对话 —— 适合快速回顾。',
    '/save 将当前对话保存到磁盘，不结束会话。',
    '/status 快速查看会话信息：ID、标题、模型、令牌用量和已用时间。',
    '/image <path> 为下一条提示附加本地图片文件，无需粘贴或拖放。',
    '/platforms 从聊天内部直接显示网关和消息平台连接状态。',
    '/commands 分页显示完整斜杠命令和已安装技能列表 —— 在无 Tab 补全的平台上很有用。',
    '/toolsets 列出所有可用的工具集，方便你了解 -t/--toolsets 接受哪些参数。',
    '/gquota 在提供商为 Google Gemini Code Assist 时，以进度条显示配额使用情况。',
    '/voice tts 切换到只 TTS 模式 —— 代理语音回复，但你仍然打字输入提示。',
    '/reload-skills 重新扫描 ~/.hermes/skills/，使即时添加的技能无需重启会话即可生效。',
    '/indicator kaomoji|emoji|unicode|ascii 选择代理运行期间 TUI 繁忙指示器的样式。',
    '/debug 上传支持包（系统信息 + 日志）并返回可分享的链接 —— 在聊天中也能用。',

    # --- CLI 子命令与标志 ---
    'hermes -z "<prompt>" 是最纯粹的一次性命令：最终答案输出到 stdout，无其他内容 —— 适合在脚本中管道使用。',
    'hermes chat --pass-session-id 将会话 ID 注入系统提示，让代理可以自我引用。',
    'hermes chat --image path/to/pic.png 在 -q 查询中附加本地图片，无需单独上传步骤。',
    'hermes chat --ignore-user-config 跳过活动用户配置 —— 用于可重现的 bug 报告和 CI 运行。',
    "hermes chat --source tool 标记编程聊天，使其不会在 hermes sessions list 中造成混乱。",
    'hermes dump --show-keys 包含打了码的 API 密钥指纹，便于深入支持调试。',
    'hermes sessions rename <ID> "新标题" 重命名任意历史会话；hermes sessions delete <ID> 删除会话。',
    'hermes import 恢复由 sessions export 或 profile export 生成的会话导出或配置文件归档。',
    'hermes fallback 以交互方式管理 fallback_model 链 —— 无需手动编辑 config.yaml。',
    'hermes pairing 轮换 DM 配对令牌 —— 轮换后的第一个消息发送者获得机器人访问权。',
    'hermes setup 以交互式流程引导首次用户完成提供商、密钥和平台配置。',
    'hermes status --deep 对所有组件运行完整的健康检查；普通 hermes status 是快速视图。',

    # --- 代理行为环境变量 ---
    'HERMES_AGENT_TIMEOUT=0 禁用运行中代理的网关不活跃杀死 —— 用于长时间研究运行。',
    'HERMES_ENABLE_PROJECT_PLUGINS=1 自动加载仓库本地插件 ./.hermes/plugins/ —— 设计上需要信任授权。',
    "HERMES_DISABLE_FILE_STATE_GUARD=1 关闭 patch 和 write_file 的'自上次读取后文件已更改'保护。",
    'HERMES_ALLOW_PRIVATE_URLS=true 允许 web 工具访问 localhost 和私网 —— 网关模式下默认关闭。',
    'HERMES_OPTIONAL_SKILLS=name1,name2 在每个配置文件首次运行时自动安装附加的可选目录技能。',
    'HERMES_BUNDLED_SKILLS 指向自定义捆绑技能树 —— 由 Homebrew 和 Nix 打包使用。',
    'HERMES_DUMP_REQUEST_STDOUT=1 将每次 API 请求负载转储到 stdout 而不是日志文件。',
    'HERMES_OAUTH_TRACE=1 记录经编辑的 OAuth 令牌交换和刷新尝试，用于调试提供商认证。',
    'HERMES_STREAM_RETRIES（默认 3）控制流中因瞬时网络错误而重新连接的次数。',

    # --- 网关行为环境变量 ---
    'HERMES_GATEWAY_BUSY_ACK_ENABLED=false 在用户向忙碌的代理发消息时，静默 ⚡/⏳/⏩ 确认消息。',
    'HERMES_AGENT_NOTIFY_INTERVAL（默认 180s）设置网关在长时间运行中发送进度通知的频率。',
    'HERMES_RESTART_DRAIN_TIMEOUT（默认 900s）限制 /restart 等待进行中运行完成的最长时间。',
    'HERMES_CHECKPOINT_TIMEOUT（默认 30s）限制文件系统检查点的创建时间 —— 在巨大单体仓库上可增大此值。',

    # --- 辅助任务与图像生成 ---
    'config.yaml 中的 image_gen.model 选择 FAL 模型：flux-2/klein、gpt-image-2、nano-banana-pro 等。',
    'image_gen.provider 将图像生成路由到插件（OpenAI Images、Codex、FAL）而不是默认方式。',
    'AUXILIARY_VISION_BASE_URL + AUXILIARY_VISION_API_KEY 可将视觉分析指向任意 OpenAI 兼容端点。',

    # --- 安全 ---
    'security.tirith_fail_open: false 使 tirith 扫描器自身出错时 Hermes 仍会阻止命令。',
    'TIRITH_FAIL_OPEN 环境变量覆盖 tirith_fail_open 配置 —— 在不编辑 config.yaml 的情况下快速切换。',

    # --- 会话与来源标签 ---
    '--source tool 的聊天默认不会出现在 hermes sessions list 中 —— 明确设置 --source 才能看到它们。',
    '会话 ID 带有时间戳前缀（20250305_091523_abcd），因此在 ls 和 jq 中自然排序。',

    # --- 杂项 ---
    'API_SERVER_MODEL_NAME 自定义 /v1/models 上的模型名称 —— 多配置文件的 Open WebUI 设置中必不可少。',
    '仪表盘插件从 /dashboard-plugins/<name>/ 提供 —— 将文件放入 ~/.hermes/dashboard-plugins/。',
]


def get_random_tip(exclude_recent: int = 0) -> str:
    """返回随机提示字符串。

    Args:
        exclude_recent: 目前未使用；预留用于将来的会话间去重。
    """
    return random.choice(TIPS)
'''

SOURCE_PATCHES = {
    # banner.py - Rich CLI 欢迎界面
    os.path.join("hermes_cli", "banner.py"): [
        ("[bold {accent}]Available Tools[/]", "[bold {accent}]可用工具[/]"),
        ("[bold {accent}]Available Skills[/]", "[bold {accent}]可用技能[/]"),
        ("[bold {accent}]MCP Servers[/]", "[bold {accent}]MCP 服务器[/]"),
        ("[bold red]⚠ YOLO mode[/] [dim {dim}]— all approval prompts bypassed[/]",
         "[bold red]⚠ YOLO 模式[/] [dim {dim}]— 所有审批提示已跳过[/]"),
        ("[dim {session_color}]Session: ", "[dim {session_color}]会话: "),
        ("[dim {dim}]No skills installed[/]", "[dim {dim}]未安装任何技能[/]"),
        ("[dim {dim}](and {remaining_toolsets} more toolsets...)[/]",
         "[dim {dim}]（还有 {remaining_toolsets} 个工具集…）[/]"),
        ("{srv['tools']} tool(s)[/]", "{srv['tools']} 个工具[/]"),
        ("— disabled[/]", "— 已禁用[/]"),
        ("— connecting[/]", "— 连接中[/]"),
        ("— configured[/]", "— 已配置[/]"),
        ("— failed[/]", "— 失败[/]"),
        ("/help for commands", "/help 查看命令"),
        ('f"{{len(tools)}} tools", f"{{total_skills}} skills"',
         'f"{{len(tools)}} 个工具", f"{{total_skills}} 个技能"'),
        ('f"{{mcp_connected}} MCP servers"', 'f"{{mcp_connected}} 个 MCP 服务器"'),
        ('"commit" if behind == 1 else "commits"', '"个提交" if behind == 1 else "个提交"'),
        ('{{commits_word}} behind', '{{commits_word}} 落后'),
        ('"[dim yellow] — run [bold]', '"[dim yellow] — 运行 [bold]'),
        ('[/bold] to update[/]"', '[/bold] 更新[/]"'),
        ('"⚠ update available"', '"⚠ 有可用更新"'),
        ('Runtime:', '运行环境:'),
        ('Profile:', '配置文件:'),
        ('terminal/file ops/MCP run inside codex', '终端/文件操作/MCP 在 codex 中运行'),
    ],
    # skin_engine.py - 所有皮肤的欢迎/再见文本
    os.path.join("hermes_cli", "skin_engine.py"): [
        # 5 个皮肤各有同一个 welcome 文本
        ('"welcome": "Welcome to Hermes Agent! Type your message or /help for commands."',
         '"welcome": "欢迎使用 Hermes Agent！输入消息或 /help 查看命令。"'),
    ],
    # cli.py - CLI 欢迎文本回退
    os.path.join("cli.py"): [
        ('_welcome_skin.get_branding("welcome", "Welcome to Hermes Agent! Type your message or /help for commands.")',
         '_welcome_skin.get_branding("welcome", "欢迎使用 Hermes Agent！输入消息或 /help 查看命令。")'),
        ('_welcome_text = "Welcome to Hermes Agent! Type your message or /help for commands."',
         '_welcome_text = "欢迎使用 Hermes Agent！输入消息或 /help 查看命令。"'),
    ],
    # branding.tsx - TUI 欢迎界面
    os.path.join("ui-tui", "src", "components", "branding.tsx"): [
        ("title=\"Available Tools\"", 'title="可用工具"'),
        ("title=\"Available Skills\"", 'title="可用技能"'),
        ("title=\"MCP Servers\"", 'title="MCP 服务器"'),
        ("title=\"System Prompt\"", 'title="系统提示词"'),
        ("'Messenger of the Digital Gods'", "'数字信使之神'"),
        ("'Nous Research · Messenger of the Digital Gods'", "'Nous Research · 数字信使之神'"),
        ("Session: ", "会话: "),
        ("/help for commands", "/help 查看命令"),
        ("No system prompt loaded.", "未加载系统提示词。"),
        ("{toolsTotal} tools{' · '}{skillsTotal} skills",
         "{toolsTotal} 个工具{' · '}{skillsTotal} 个技能"),
        ("'in {skillsCatCount} categor{skillsCatCount === 1 ? 'y' : 'ies'}`",
         "'在 {skillsCatCount} 个分类中`"),
        ("suffix=\"connected\"", 'suffix="已连接"'),
        ("{info.update_behind === 1 ? 'commit' : 'commits'} behind",
         "{info.update_behind} 个提交落后"),
        ("- run{' ", "— 运行{' "),
        ("to update", "更新"),
    ],
    # theme.ts - 品牌文字
    os.path.join("ui-tui", "src", "theme.ts"): [
        ("'Type your message or /help for commands.'", "'输入消息或 /help 查看命令。'"),
        ("'Goodbye! ⚕'", "'再见！⚕'"),
        ("'(^_^)? Commands'", "'(^_^)? 命令'"),
    ],
    # verbs.ts - 思考动词 / 工具动词
    os.path.join("ui-tui", "src", "content", "verbs.ts"): {
        "full_replace": True,
        "content": '''export const TOOL_VERBS: Record<string, string> = {
  browser: '浏览中',
  clarify: '询问中',
  create_file: '创建中',
  delegate_task: '委派中',
  delete_file: '删除中',
  execute_code: '执行中',
  image_generate: '生成中',
  list_files: '列表中',
  memory: '记忆存储中',
  patch: '修补中',
  read_file: '读取中',
  run_command: '运行中',
  search_code: '搜索中',
  search_files: '搜索中',
  terminal: '终端中',
  web_extract: '提取中',
  web_search: '搜索中',
  write_file: '写入中'
}

export const VERBS = [
  '沉思',
  '思考',
  '思索',
  '考量',
  '反思',
  '斟酌',
  '推敲',
  '反省',
  '处理',
  '推理',
  '分析',
  '计算',
  '综合',
  '构思',
  '头脑风暴'
]
''',
    },
    # background_review.py - 自我改进审查提示
    os.path.join("agent", "background_review.py"): [
        ('  💾 Self-improvement review: ', '  💾 自我改进审查: '),
        ('💾 Self-improvement review: ', '💾 自我改进审查: '),
    ],
    # display.py - CLI 思考动词
    os.path.join("agent", "display.py"): [
        ('"pondering", "contemplating", "musing", "cogitating", "ruminating",',
         '"沉思", "思考", "思索", "考量", "反思",'),
        ('"deliberating", "mulling", "reflecting", "processing", "reasoning",',
         '"斟酌", "推敲", "反省", "处理", "推理",'),
        ('"analyzing", "computing", "synthesizing", "formulating", "brainstorming",',
         '"分析", "计算", "综合", "构思", "头脑风暴",'),
    ],
    # tips.py - CLI 启动提示（完整中文翻译替换）
    os.path.join("hermes_cli", "tips.py"): {
        "full_replace": True,
        "content": TIPS_TRANSLATED_CONTENT,
    },
    # models.py - Provider 选择菜单中文描述
    os.path.join("hermes_cli", "models.py"): [
        ('ProviderEntry("nous",           "Nous Portal",              "Nous Portal (Everything your agent needs, 300+ models with bundled tool use)")',
         'ProviderEntry("nous",           "Nous Portal",              "Nous Portal（一站式智能体平台，300+ 模型，内置工具调用）")'),
        ('ProviderEntry("openrouter",     "OpenRouter",               "OpenRouter (Pay-per-use API aggregator)")',
         'ProviderEntry("openrouter",     "OpenRouter",               "OpenRouter（按量付费 API 聚合器）")'),
        ('ProviderEntry("novita",         "NovitaAI",                 "NovitaAI (Cloud: Model API, Agent Sandbox, GPU Cloud)")',
         'ProviderEntry("novita",         "NovitaAI",                 "NovitaAI（云端：模型 API、智能体沙箱、GPU 云）")'),
        ('ProviderEntry("lmstudio",       "LM Studio",                "LM Studio (Local desktop app with built-in model server)")',
         'ProviderEntry("lmstudio",       "LM Studio",                "LM Studio（本地桌面应用，内置模型服务器）")'),
        ('ProviderEntry("anthropic",      "Anthropic",                "Anthropic (Claude models via API key or Claude Code)")',
         'ProviderEntry("anthropic",      "Anthropic",                "Anthropic（通过 API Key 或 Claude Code 使用 Claude 模型）")'),
        ('ProviderEntry("openai-codex",   "OpenAI Codex",             "OpenAI Codex (Codex CLI via ChatGPT subscription or API key)")',
         'ProviderEntry("openai-codex",   "OpenAI Codex",             "OpenAI Codex（通过 ChatGPT 订阅或 API Key 使用 Codex CLI）")'),
        ('ProviderEntry("openai-api",     "OpenAI API",               "OpenAI API (api.openai.com, API key)")',
         'ProviderEntry("openai-api",     "OpenAI API",               "OpenAI API（api.openai.com，API Key）")'),
        ('ProviderEntry("alibaba",        "Qwen Cloud",               "Qwen Cloud / DashScope (Qwen + multi-provider)")',
         'ProviderEntry("alibaba",        "Qwen 云",                   "Qwen 云 / DashScope（通义千问 + 多模型聚合）")'),
        ('ProviderEntry("xai-oauth",      "xAI Grok OAuth (SuperGrok / Premium+)", "xAI Grok OAuth (SuperGrok / Premium+ subscription)")',
         'ProviderEntry("xai-oauth",      "xAI Grok OAuth（SuperGrok / Premium+）", "xAI Grok OAuth（SuperGrok / Premium+ 订阅）")'),
        ('ProviderEntry("xiaomi",         "Xiaomi MiMo",              "Xiaomi MiMo (MiMo-V2.5 and V2 models: pro, omni, flash)")',
         'ProviderEntry("xiaomi",         "小米 MiMo",                "小米 MiMo（MiMo-V2.5 和 V2 模型：pro、omni、flash）")'),
        ('ProviderEntry("tencent-tokenhub", "Tencent TokenHub",       "Tencent TokenHub (Hy3 Preview via tokenhub.tencentmaas.com)")',
         'ProviderEntry("tencent-tokenhub", "腾讯 TokenHub",          "腾讯 TokenHub（通过 tokenhub.tencentmaas.com 使用 Hy3 Preview）")'),
        ('ProviderEntry("nvidia",         "NVIDIA NIM",               "NVIDIA NIM (Nemotron models via build.nvidia.com or local NIM)")',
         'ProviderEntry("nvidia",         "NVIDIA NIM",               "NVIDIA NIM（通过 build.nvidia.com 或本地 NIM 使用 Nemotron）")'),
        ('ProviderEntry("copilot",        "GitHub Copilot",           "GitHub Copilot (Uses GITHUB_TOKEN or gh auth token)")',
         'ProviderEntry("copilot",        "GitHub Copilot",           "GitHub Copilot（使用 GITHUB_TOKEN 或 gh auth token）")'),
        ('ProviderEntry("copilot-acp",    "GitHub Copilot ACP",       "GitHub Copilot ACP (Spawns copilot --acp --stdio)")',
         'ProviderEntry("copilot-acp",    "GitHub Copilot ACP",       "GitHub Copilot ACP（启动 copilot --acp --stdio 子进程）")'),
        ('ProviderEntry("huggingface",    "Hugging Face",             "Hugging Face Inference Providers")',
         'ProviderEntry("huggingface",    "Hugging Face",             "Hugging Face 推理提供商")'),
        ('ProviderEntry("gemini",         "Google AI Studio",         "Google AI Studio (Native Gemini API)")',
         'ProviderEntry("gemini",         "Google AI Studio",         "Google AI Studio（原生 Gemini API）")'),
        ('ProviderEntry("google-gemini-cli", "Google Gemini (OAuth)",   "Google Gemini via OAuth + Code Assist (Code Assist OAuth flow)")',
         'ProviderEntry("google-gemini-cli", "Google Gemini（OAuth）", "Google Gemini 通过 OAuth + Code Assist（Code Assist OAuth 流程）")'),
        ('ProviderEntry("deepseek",       "DeepSeek",                 "DeepSeek (V3, R1, coder, direct API)")',
         'ProviderEntry("deepseek",       "DeepSeek",                 "DeepSeek（V3、R1、coder 等模型，直连 API）")'),
        ('ProviderEntry("xai",            "xAI",                      "xAI Grok (Direct API)")',
         'ProviderEntry("xai",            "xAI",                      "xAI Grok（直连 API）")'),
        ('ProviderEntry("zai",            "Z.AI / GLM",               "Z.AI / GLM (Zhipu direct API)")',
         'ProviderEntry("zai",            "智谱 AI / GLM",            "智谱 AI / GLM（智谱直连 API）")'),
        ('ProviderEntry("kimi-coding",    "Kimi / Kimi Coding Plan",  "Kimi Coding Plan (api.kimi.com & Moonshot API)")',
         'ProviderEntry("kimi-coding",    "Kimi / Kimi Coding Plan",  "Kimi Coding Plan（api.kimi.com 和 Moonshot API）")'),
        ('ProviderEntry("kimi-coding-cn", "Kimi / Moonshot (China)",  "Kimi / Moonshot China (Domestic direct API)")',
         'ProviderEntry("kimi-coding-cn", "Kimi / 月之暗面（国内）",  "Kimi / 月之暗面国内版（国内直连 API）")'),
        ('ProviderEntry("stepfun",        "StepFun Step Plan",       "StepFun Step Plan (Agent / coding models via Step Plan API)")',
         'ProviderEntry("stepfun",        "阶跃星辰 Step Plan",       "阶跃星辰 Step Plan（通过 Step Plan API 使用 Agent/编程模型）")'),
        ('ProviderEntry("minimax",        "MiniMax",                  "MiniMax (Global direct API)")',
         'ProviderEntry("minimax",        "MiniMax",                  "MiniMax（海外直连 API）")'),
        ('ProviderEntry("minimax-oauth",  "MiniMax (OAuth)",          "MiniMax via OAuth browser login (Coding Plan, minimax.io)")',
         'ProviderEntry("minimax-oauth",  "MiniMax（OAuth）",          "MiniMax 通过 OAuth 浏览器登录（Coding Plan，minimax.io）")'),
        ('ProviderEntry("minimax-cn",     "MiniMax (China)",          "MiniMax China (Domestic direct API)")',
         'ProviderEntry("minimax-cn",     "MiniMax（国内）",           "MiniMax 国内版（国内直连 API）")'),
        ('ProviderEntry("ollama-cloud",   "Ollama Cloud",             "Ollama Cloud (Cloud-hosted open models, ollama.com)")',
         'ProviderEntry("ollama-cloud",   "Ollama 云",                "Ollama 云（云端托管开源模型，ollama.com）")'),
        ('ProviderEntry("arcee",          "Arcee AI",                 "Arcee AI (Trinity models, direct API)")',
         'ProviderEntry("arcee",          "Arcee AI",                 "Arcee AI（Trinity 系列模型，直连 API）")'),
        ('ProviderEntry("gmi",            "GMI Cloud",                "GMI Cloud (Multi-model direct API)")',
         'ProviderEntry("gmi",            "GMI 云",                   "GMI 云（多模型直连 API）")'),
        ('ProviderEntry("kilocode",       "Kilo Code",                "Kilo Code (Kilo Gateway API)")',
         'ProviderEntry("kilocode",       "Kilo Code",                "Kilo Code（Kilo Gateway API）")'),
        ('ProviderEntry("opencode-zen",   "OpenCode Zen",             "OpenCode Zen (Curated models, pay-as-you-go)")',
         'ProviderEntry("opencode-zen",   "OpenCode Zen",             "OpenCode Zen（精选模型，按量付费）")'),
        ('ProviderEntry("opencode-go",    "OpenCode Go",              "OpenCode Go (Open models subscription)")',
         'ProviderEntry("opencode-go",    "OpenCode Go",              "OpenCode Go（开源模型订阅）")'),
        ('ProviderEntry("bedrock",        "AWS Bedrock",              "AWS Bedrock (Claude, Nova, Llama, DeepSeek; IAM or API key)")',
         'ProviderEntry("bedrock",        "AWS Bedrock",              "AWS Bedrock（Claude、Nova、Llama、DeepSeek；IAM 或 API Key）")'),
        ('ProviderEntry("azure-foundry",  "Azure Foundry",            "Azure Foundry (OpenAI-style or Anthropic-style endpoint, your Azure AI deployment)")',
         'ProviderEntry("azure-foundry",  "Azure Foundry",            "Azure Foundry（OpenAI 兼容或 Anthropic 兼容端点，你的 Azure AI 部署）")'),
        ('ProviderEntry("qwen-oauth",     "Qwen OAuth (Portal)",      "Qwen OAuth (Reuses local Qwen CLI login)")',
         'ProviderEntry("qwen-oauth",     "Qwen OAuth（Portal）",     "Qwen OAuth（复用本地 Qwen CLI 登录状态）")'),
    ],
}


def patch_source_file(rel_path, patches_or_dict):
    """Apply translations to a Hermes source file."""
    full_path = os.path.join(HERMES_AGENT_DIR, rel_path)
    if not os.path.exists(full_path):
        return False, f"文件不存在: {rel_path}"

    if isinstance(patches_or_dict, dict) and patches_or_dict.get("full_replace"):
        # 完整替换文件内容（先备份）
        _backup_file(full_path, subdir="source")
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(patches_or_dict["content"])
        return True, f"完整替换: {rel_path}"

    # 逐行替换
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"读取失败: {e}"

    original = content
    changes = 0
    for old, new in patches_or_dict:
        # 处理 f-string 变量展开：{var} → {{var}} 避免 format 冲突
        old_normalized = old.replace("{behind}", "{Behind}").replace("{tools}", "{Tools}")
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            changes += count

    if changes == 0:
        return False, f"无匹配: {rel_path}"

    # 先备份原文件，再写入
    _backup_file(full_path, subdir="source")
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, f"翻译 {changes} 处: {rel_path}"
    except Exception as e:
        return False, f"写入失败: {e}"


def patch_all_source_files():
    """翻译所有 Hermes 源文件界面文字"""
    print("\n" + "=" * 60)
    print("Hermes 源文件界面翻译")
    print("=" * 60)
    success = 0
    failed = 0

    for rel_path, patches in SOURCE_PATCHES.items():
        ok, msg = patch_source_file(rel_path, patches)
        if ok:
            print(f"  ✓ {msg}")
            success += 1
        else:
            print(f"  → {msg}")
            failed += 1

    print(f"\n结果: {success} 成功, {failed} 跳过")
    return success, failed


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--restore':
        # 从备份还原
        ts = sys.argv[2] if len(sys.argv) > 2 else None
        restore_all(timestamp=ts)
    elif len(sys.argv) > 1 and sys.argv[1] == '--backup-only':
        # 仅备份所有文件，不翻译
        print("=" * 60)
        print("仅备份模式 — 不执行翻译")
        print("=" * 60)
        count = 0
        # 备份所有 SKILL.md
        for root, dirs, files in os.walk(SKILLS_DIR):
            if 'SKILL.md' in files:
                fp = os.path.join(root, 'SKILL.md')
                _backup_file(fp, subdir="skills")
                count += 1
        # 备份所有源代码文件
        for rel_path in SOURCE_PATCHES:
            fp = os.path.join(HERMES_AGENT_DIR, rel_path)
            if os.path.exists(fp):
                _backup_file(fp, subdir="source")
                count += 1
        ts = _get_backup_timestamp()
        backup_root = os.path.join(BACKUP_DIR, ts)
        print(f"已备份 {count} 个文件到: {backup_root}")
        print(f"还原命令: python translate_hermes_skills.py --restore {ts}")
    else:
        main()
        print()
        patch_all_source_files()
