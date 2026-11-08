# 题目复习助手 · Problem Review

[English](README.md) | [简体中文](README.zh-CN.md)

为什么题目刷了老是记不住！ \
英语单词背诵都这么科学，我们刷题也得跟上！ \
为你而生的刷题科学记忆软件，每天提醒你今天该刷什么，从此让面试官吓得瘫在椅子上！ \

<img width="1220" height="898" alt="download" src="https://github.com/user-attachments/assets/172bf0bc-5ce2-44c0-8af2-5c00bf65c131" />

## 功能

- 在程序内切换简体中文和英文，记住上次的选择；题目名称和备注保留原文。
- 用本地 SQLite 保存题目名称、日期、可选链接和多行备注。
- 同时显示今天到期和以前未完成的题目。
- 同一道题每天最多记录一次有效复习，支持撤销当天的完成记录。
- 在同一个区域切换文字备注与复习记录。
- 蓝色圆角滚动条，支持拖动、滚轮及点击轨道翻页。
- 归档时暂停提醒，保留内容和历史。
- 在编辑窗口删除题目，经过二次确认后才执行，默认选“否”。
- 导出和恢复经过校验的 JSON 备份，兼容之前中文版的备份。
- 按屏幕 DPI 绘制文字与布局，布局检查覆盖 100%、150%、200% 缩放。

## 运行环境

- Windows 10 或 Windows 11。
- Python 3.10 及以上，包含 Tkinter 和 SQLite；开发和自动检查使用 Python 3.13。
- 运行程序不需要安装第三方 Python 包。

可以这样检查 Tkinter：

```powershell
python -m tkinter
```

## 启动

在项目文件夹执行：

```powershell
python app.py
```

也可以双击 `Start.cmd`。发布包可能附带 `ProblemReview.exe`，它使用电脑上已有的 Python，需要与 Python 源文件放在同一文件夹；这个启动器没有内置 Python。

在侧栏底部选择 **简体中文** 或 **English**。也可以通过命令行指定本次启动的语言和数据目录：

```powershell
python app.py --language zh-CN
python app.py --language en
python app.py --data-dir "D:\ReviewData"
```

侧栏切换的语言会保存到数据目录；`--language` 参数只覆盖本次启动的语言。

## 每天怎么使用

1. 看懂题解后添加题目，以当天作为初次学习日期。
2. 打开“今日复习”，查看到期和逾期的题目。
3. 重新学习后，点击“已重新学习，安排下次”。
4. 如果点错，到“今日已学习”中撤销当天的完成记录。

切换界面语言不会翻译或修改已保存的题目内容。

## 复习规则

间隔依次为 **1、3、7、14、30、60 天**，从实际学习或复习完成的日期开始计算。到达最后一档后，每次完成再安排 60 天后的复习。

例如，11 月 8 日学习，第一次复习安排在 11 月 9 日；11 月 9 日完成后，下次是 11 月 12 日。如果拖到 11 月 11 日才完成，下次则是 11 月 14 日。

- 未完成的题目继续保留，不会自动推进复习档位。
- 同一道逾期题只显示一次。
- 中英文界面都按 **北京时间 UTC+08:00 的自然日**安排。
- 标记完成只表示“已经重新学习”，程序不评估回忆质量，也不预测个人遗忘时间。
- 这是一套基于间隔练习原则的固定间隔，并不代表对每个人、每道题都科学最优。研究背景：[Cepeda 等，2008](https://digitalcommons.usf.edu/psy_facpub/1766/)。

## 归档、删除与备份

**归档**暂停提醒，同时保留题目和复习历史。恢复后沿用原来的日期，因此可能立即成为逾期题。

**删除题目**只在编辑已有题目时出现。确认后，在同一数据库事务中删除该题、备注和全部复习记录；取消后保留原数据及未保存的编辑内容。程序没有“撤销删除”入口。

默认数据保存在程序旁边，也可用 `--data-dir` 指定：

```text
data/
  review.sqlite3
  settings.json
  app.log
  backups/
    auto-YYYY-MM-DD.json
    before-restore-<timestamp>.json
```

修改数据和退出时更新当天的 JSON 快照。恢复备份会替换当前全部题目，恢复前先保留当前数据的备份；损坏或内容不一致的备份会先被拒绝。历史备份是独立副本，手动恢复旧备份会把整个题库恢复到备份时的状态。

在原文件夹更新程序会继续使用已有数据库，备份格式兼容最初的中文版。

## 快捷键

| 快捷键 | 操作 |
| --- | --- |
| `Ctrl + N` | 新增题目 |
| `Ctrl + F` | 搜索 |
| `Ctrl + Enter` | 保存打开的编辑窗口 |
| `F5` | 刷新 |
| `Esc` | 关闭编辑或备份窗口 |

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试使用临时数据。界面测试需要图形桌面，覆盖表单操作、删除确认、语言切换、滚动和 DPI 布局。

## 构建 Windows 启动器

可选启动器使用 Windows 自带的 .NET Framework C# 编译器：

```powershell
.\build.ps1
```

生成的 `ProblemReview.exe` 需与 `app.py`、`review_core.py`、`i18n.py`、`scrollbars.py` 放在一起。也可继续用 `Start.cmd` 或 `python app.py` 启动。

## 项目结构

```text
app.py                 界面、语言设置和启动逻辑
review_core.py         本地数据库、排期与备份校验
i18n.py                中英文界面文案
scrollbars.py          Canvas 圆角滚动条
launcher.cs            可选 Windows 启动器
app.manifest           原生 DPI 声明
Start.cmd              Python 启动入口
build.ps1              启动器构建脚本
tests/                 使用临时数据的自动检查
README.md              英文说明
README.zh-CN.md        中文说明
```

附带的 `.gitignore` 排除了本地题库、设置、备份、日志、缓存和生成的程序文件。GitHub 源码包只包含源码、测试和文档。
