# Problem Review

[English](README.md) | [简体中文](README.zh-CN.md)

A small, offline Windows app for revisiting coding problems whose solutions you understood but could not solve independently.

Record a problem, its learning date and a note. Open the app later to see what is due, then mark each problem as reviewed. No account, server or internet connection is required.

## Features

- Switch between English and Simplified Chinese inside the app. The choice is remembered; your problem names and notes keep their original language.
- Store problem names, dates, optional links and multiline notes locally in SQLite.
- See today's due problems and unfinished overdue problems in one list.
- Mark a problem reviewed once per day, or undo today's completion.
- Switch between notes and review history in the same panel.
- Use rounded blue scrollbars with drag, wheel and page scrolling.
- Archive a problem to pause reminders while keeping its content and history.
- Delete a problem from its edit window after a second confirmation. The confirmation defaults to No.
- Export and restore validated JSON backups, including backups from the earlier Chinese version.
- Render text and layout at the screen's DPI. Layout checks cover 100%, 150% and 200% scaling.

## Requirements

- Windows 10 or 11.
- Python 3.10 or later with Tkinter and SQLite support. Development and automated checks use Python 3.13.
- No third-party Python packages are required at runtime.

To check Tkinter:

```powershell
python -m tkinter
```

## Run

From the project folder:

```powershell
python app.py
```

Or double-click `Start.cmd`. A release package may also include `ProblemReview.exe`; that small launcher uses an existing Python installation and must stay beside the Python source files. It does not bundle Python.

Choose **English** or **简体中文** in the language selector at the bottom of the sidebar. You can also choose the initial language from the command line:

```powershell
python app.py --language en
python app.py --language zh-CN
python app.py --data-dir "D:\ReviewData"
```

The sidebar choice is saved in the data directory. The `--language` option overrides it for that launch.

## Daily workflow

1. Add a problem after understanding its solution. Use that day's date as the first learned date.
2. Open **Today's reviews** to see due and overdue problems.
3. Study a problem again, then select **Mark reviewed**.
4. Use **Reviewed today** and **Undo today's review** if you marked a problem by mistake.

Changing the UI language does not translate or modify saved problem content.

## Review schedule

Intervals are **1, 3, 7, 14, 30 and 60 days**, measured from the actual learning or review date. After reaching the last stage, each completed review schedules another review 60 days later.

For example, learning on November 8 schedules a review on November 9. Completing that review on November 9 schedules the next one on November 12. Completing it late, on November 11, schedules the next one on November 14.

- Unfinished problems stay due; they do not advance automatically.
- Each overdue problem appears once, regardless of how long it has been overdue.
- Scheduling uses calendar days in **UTC+08:00**, in both UI languages.
- Completion means “studied again.” The app does not assess recall quality or predict an individual's forgetting curve.
- The intervals are a fixed design choice based on spaced-practice principles, rather than a scientifically optimal schedule for every person or problem. Background: [Cepeda et al., 2008](https://digitalcommons.usf.edu/psy_facpub/1766/).

## Archive, delete and backups

**Archive** pauses reminders and preserves the problem and its review history. Restoring an archived problem keeps its previous due date, so it may become overdue immediately.

**Delete** is available only when editing an existing problem. Confirming deletes that problem, its notes and all review events in one database transaction. Canceling leaves both saved data and unsaved edits intact. There is no undo-delete action.

Data is stored beside the app unless `--data-dir` is provided:

```text
data/
  review.sqlite3
  settings.json
  app.log
  backups/
    auto-YYYY-MM-DD.json
    before-restore-<timestamp>.json
```

A daily JSON snapshot is updated after changes and on exit. Restoring a backup replaces the entire current problem collection; a pre-restore backup is saved first. Invalid or inconsistent backups are rejected before changing current data. Historical backups are separate copies: manually restoring an older backup restores the whole collection as it existed at that time.

Upgrading in the same folder keeps the existing database. The backup format is compatible with the original Chinese version.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl + N` | Add a problem |
| `Ctrl + F` | Focus search |
| `Ctrl + Enter` | Save an open problem form |
| `F5` | Refresh |
| `Esc` | Close a problem or backup dialog |

## Test

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary data. UI tests require a graphical desktop; they exercise form actions, deletion confirmation, language switching, scrolling and DPI layouts.

## Build a Windows launcher

The optional launcher uses the Windows .NET Framework C# compiler:

```powershell
.\build.ps1
```

Keep `ProblemReview.exe` beside `app.py`, `review_core.py`, `i18n.py` and `scrollbars.py`. `Start.cmd` and `python app.py` remain alternatives.

## Repository contents

```text
app.py                 UI, language preference and application startup
review_core.py         SQLite storage, scheduling and validated backups
i18n.py                Chinese / English UI strings
scrollbars.py          Rounded Canvas scrollbars
launcher.cs            Optional Windows launcher
app.manifest           Native DPI declaration
Start.cmd              Python launcher
build.ps1              Optional launcher build
tests/                 Automated checks using temporary data
README.md              English documentation
README.zh-CN.md        Chinese documentation
```

The supplied `.gitignore` excludes local data, settings, backups, logs, caches and generated binaries. The GitHub source archive contains source, tests and documentation only.
