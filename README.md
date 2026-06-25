# Hermes Agent 中文汉化

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

将 Hermes Agent 界面文本翻译为中文的脚本和补丁集合。  
源文件补丁使用 **git apply** 机制，**永不产生 Git 合并冲突标记**。

## 用法

### 备份 + 翻译（首次运行）

```bash
python translate_hermes_skills.py
```

- 翻译 skills 目录下所有 SKILL.md
- 生成并应用 11 个源文件补丁（`patches/` 目录）
- 翻译前会自动备份原文件到 `translation_backups/<时间戳>/`

### 仅备份，不翻译

```bash
python translate_hermes_skills.py --backup-only
```

### 从备份还原

```bash
python translate_hermes_skills.py --restore
python translate_hermes_skills.py --restore 20260618_204450  # 指定备份
```

### 更新后重打补丁（每次 git pull 后执行）

```bash
# 更新 Hermes
cd ~/AppData/Local/hermes/hermes-agent
git pull

# 重打汉化补丁
python translate_hermes_skills.py --apply-patches
```

### 回退所有汉化补丁

```bash
python translate_hermes_skills.py --revert-patches
```

## 翻译内容

### 技能文件（SKILL.md）
- YAML 前置元数据（标题、描述、标签、触发器）
- Markdown 章节标题
- 常用正文段落

### Hermes 源代码界面（11 个补丁文件，位于 `patches/`）

| 补丁文件 | 原始文件 | 内容 |
|----------|---------|------|
| `agent_background_review.py.patch` | `agent/background_review.py` | 自我改进审查提示 |
| `agent_display.py.patch` | `agent/display.py` | CLI 思考动词 |
| `cli.py.patch` | `cli.py` | CLI 回退欢迎文本 |
| `hermes_cli_banner.py.patch` | `hermes_cli/banner.py` | CLI 启动欢迎界面 |
| `hermes_cli_commands.py.patch` | `hermes_cli/commands.py` | 斜杠命令描述 |
| `hermes_cli_models.py.patch` | `hermes_cli/models.py` | Provider 选择菜单 |
| `hermes_cli_skin_engine.py.patch` | `hermes_cli/skin_engine.py` | 5 个皮肤的欢迎文本 |
| `hermes_cli_tips.py.patch` | `hermes_cli/tips.py` | 381 条启动提示 |
| `ui-tui_src_components_branding.tsx.patch` | `ui-tui/.../branding.tsx` | TUI 欢迎界面 |
| `ui-tui_src_content_verbs.ts.patch` | `ui-tui/.../verbs.ts` | 工具动词 |
| `ui-tui_src_theme.ts.patch` | `ui-tui/.../theme.ts` | 品牌文字 |

## 工作原理

每次 `git pull` 更新 Hermes 后，源代码会被恢复为英文。使用 `--apply-patches` 即可重新应用所有中文补丁。

- SKILL.md 的翻译状态记录在 `.translation_state.json`，已翻译的会跳过
- 源文件补丁生成在 `translation_backups/patches/` 目录，使用 `git diff --no-index` 生成
- 补丁的 **回退** 使用 `git apply -R`，**重打** 使用 `git apply`
- 补丁文件可反复应用/回退，**永不产生 `<<<<<<<` 合并冲突标记**
- `tips.py` 和 `verbs.ts` 使用完整文件替换方式
