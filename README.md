# Hermes Agent 中文汉化

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

将 Hermes Agent 界面文本翻译为中文的脚本和补丁集合。

## 用法

### 备份 + 翻译（推荐）

```bash
python translate_hermes_skills.py
```

翻译前会自动备份原文件到 `translation_backups/<时间戳>/`。

### 仅备份，不翻译

```bash
python translate_hermes_skills.py --backup-only
```

### 从备份还原

```bash
python translate_hermes_skills.py --restore
python translate_hermes_skills.py --restore 20260618_204450  # 指定备份
```

## 翻译内容

### 技能文件（SKILL.md）
- YAML 前置元数据（标题、描述、标签、触发器）
- Markdown 章节标题
- 常用正文段落

### Hermes 源代码界面
| 文件 | 内容 |
|------|------|
| `hermes_cli/banner.py` | CLI 启动欢迎界面 |
| `hermes_cli/skin_engine.py` | 5 个皮肤的欢迎文本 |
| `cli.py` | CLI 回退欢迎文本 |
| `hermes_cli/tips.py` | 381 条启动提示（完整中文版） |
| `agent/display.py` | CLI 思考动词 |
| `agent/background_review.py` | 自我改进审查提示 |
| `ui-tui/src/components/branding.tsx` | TUI 界面文字 |
| `ui-tui/src/theme.ts` | 品牌文字 |
| `ui-tui/src/content/verbs.ts` | 工具动词（完整中文版） |

## 工作原理

每次运行 `hermes update` 后，源代码会被恢复为英文。只需重新运行本脚本即可重新应用所有中文翻译。

- SKILL.md 的翻译状态记录在 `.translation_state.json`，已翻译的会跳过
- 源代码补丁在 `SOURCE_PATCHES` 字典中定义，运行时逐行替换
- `tips.py` 和 `verbs.ts` 使用完整文件替换方式
