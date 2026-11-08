"""Local storage and calendar-day scheduling for the problem review assistant."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from i18n import tr

INTERVALS = (1, 3, 7, 14, 30, 60)
CHINA_TZ = timezone(timedelta(hours=8))
FORMAT = "problem-review-backup"
SCHEMA_VERSION = 1


class ReviewError(ValueError):
    """An expected, user-readable validation error."""
    def __init__(self, message):
        super().__init__(tr(message))


def current_day() -> date:
    return datetime.now(CHINA_TZ).date()


def timestamp() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="microseconds")


def parse_day(value: str) -> date:
    try:
        if not isinstance(value, str):
            raise ValueError
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ReviewError(tr('日期请填写为 YYYY-MM-DD，例如 2026-11-08。')) from None


def clean_fields(title: str, learned_on: str, notes: str, url: str) -> tuple:
    if not all(isinstance(value, str) for value in (title, learned_on, notes, url)):
        raise ReviewError(tr('题目名称、日期、备注和链接必须是文字。'))
    title, notes, url = title.strip(), notes.strip(), url.strip()
    if not title or len(title) > 200:
        raise ReviewError(tr('请填写题目名称，长度不超过 200 个字符。'))
    if len(notes) > 100_000:
        raise ReviewError(tr('这道题的备注过长，请控制在 100,000 个字符以内。'))
    learned = parse_day(learned_on)
    if learned == date.max:
        raise ReviewError(tr('学习日期超出可安排复习的范围。'))
    if url:
        try:
            parts = urlsplit(url)
            valid = parts.scheme in ("http", "https") and bool(parts.hostname)
        except ValueError:
            valid = False
        if not valid or len(url) > 2048 or any(char.isspace() for char in url):
            raise ReviewError(tr('题目链接请填写完整的 http:// 或 https:// 地址。'))
    return title, learned, notes, url


def atomic_json(path: Path, document: dict) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".review-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path


class Store:
    def __init__(self, data_dir: Path, today: Callable[[], date] = current_day):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "review.sqlite3"
        self.today = today
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self.db.close()
            raise ReviewError(tr('这份数据由更新版本创建，请使用更新版本的程序打开。'))
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS problems (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                learned_on TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                completed_count INTEGER NOT NULL DEFAULT 0 CHECK(completed_count >= 0),
                last_review_on TEXT,
                next_review_on TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                problem_id TEXT NOT NULL REFERENCES problems(id),
                reviewed_on TEXT NOT NULL,
                previous_next_on TEXT NOT NULL,
                previous_count INTEGER NOT NULL,
                previous_last_on TEXT,
                next_on TEXT NOT NULL,
                count_after INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                undone_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_review_per_day
                ON reviews(problem_id, reviewed_on) WHERE undone_at IS NULL;
            CREATE INDEX IF NOT EXISTS due_problems ON problems(archived, next_review_on);
            CREATE INDEX IF NOT EXISTS problem_reviews ON reviews(problem_id, reviewed_on);
            PRAGMA user_version = 1;
        """)

    def close(self):
        self.db.close()

    def get(self, problem_id: str) -> dict:
        row = self.db.execute("SELECT * FROM problems WHERE id = ?", (problem_id,)).fetchone()
        if row is None:
            raise ReviewError(tr('这道题已经不存在，请刷新列表。'))
        return dict(row)

    def all(self) -> list[dict]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM problems ORDER BY next_review_on, created_at, id"
        )]

    def history(self, problem_id: str) -> list[dict]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM reviews WHERE problem_id = ? ORDER BY created_at DESC, id DESC",
            (problem_id,),
        )]

    def active_history(self, problem_id: str) -> list[dict]:
        return [row for row in self.history(problem_id) if row["undone_at"] is None]

    def add(self, title: str, learned_on: str, notes: str = "", url: str = "") -> str:
        title, learned, notes, url = clean_fields(title, learned_on, notes, url)
        if learned > self.today():
            raise ReviewError(tr('学习日期不能晚于今天。'))
        problem_id, now = str(uuid.uuid4()), timestamp()
        with self.db:
            self.db.execute("""
                INSERT INTO problems(id, title, learned_on, notes, url, next_review_on,
                                     created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """, (problem_id, title, learned.isoformat(), notes, url,
                  (learned + timedelta(days=INTERVALS[0])).isoformat(), now, now))
        return problem_id

    def edit(self, problem_id: str, title: str, learned_on: str, notes: str, url: str):
        title, learned, notes, url = clean_fields(title, learned_on, notes, url)
        if learned > self.today():
            raise ReviewError(tr('学习日期不能晚于今天。'))
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            problem = self.get(problem_id)
            if problem["completed_count"] and learned_on != problem["learned_on"]:
                raise ReviewError(tr('这道题已有复习记录，初次学习日期不能修改；名称、备注和链接可以修改。'))
            next_on = problem["next_review_on"] if problem["completed_count"] else (
                learned + timedelta(days=INTERVALS[0])
            ).isoformat()
            self.db.execute("""
                UPDATE problems SET title = ?, learned_on = ?, notes = ?, url = ?,
                    next_review_on = ?, updated_at = ? WHERE id = ?
            """, (title, learned_on, notes, url, next_on, timestamp(), problem_id))

    def set_archived(self, problem_id: str, archived: bool):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.get(problem_id)
            self.db.execute("UPDATE problems SET archived = ?, updated_at = ? WHERE id = ?",
                            (int(archived), timestamp(), problem_id))

    def delete(self, problem_id: str):
        """Remove one problem and all its review events as one atomic operation."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.get(problem_id)
            self.db.execute("DELETE FROM reviews WHERE problem_id = ?", (problem_id,))
            self.db.execute("DELETE FROM problems WHERE id = ?", (problem_id,))

    def complete(self, problem_id: str) -> bool:
        actual_day = self.today()
        today = actual_day.isoformat()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            problem = self.get(problem_id)
            if self.db.execute("""SELECT 1 FROM reviews WHERE problem_id = ?
                AND reviewed_on = ? AND undone_at IS NULL""", (problem_id, today)).fetchone():
                return False
            if problem["archived"]:
                raise ReviewError(tr('请先将这道题恢复到进行中，再记录复习。'))
            if problem["next_review_on"] > today:
                raise ReviewError(tr('这道题的下次复习日期是 {v0}，尚未到期。', v0=problem['next_review_on']))
            if problem["last_review_on"] and problem["last_review_on"] > today:
                raise ReviewError(tr('电脑日期早于已有复习记录，请检查日期后再操作。'))
            new_count = problem["completed_count"] + 1
            interval = INTERVALS[min(new_count, len(INTERVALS) - 1)]
            next_on = (actual_day + timedelta(days=interval)).isoformat()
            now = timestamp()
            self.db.execute("""
                INSERT INTO reviews(id, problem_id, reviewed_on, previous_next_on,
                    previous_count, previous_last_on, next_on, count_after, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), problem_id, today, problem["next_review_on"],
                  problem["completed_count"], problem["last_review_on"], next_on, new_count, now))
            self.db.execute("""UPDATE problems SET completed_count = ?, last_review_on = ?,
                next_review_on = ?, updated_at = ? WHERE id = ?""",
                (new_count, today, next_on, now, problem_id))
        return True

    def undo_today(self, problem_id: str):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            problem = self.get(problem_id)
            row = self.db.execute("""SELECT * FROM reviews WHERE problem_id = ?
                AND undone_at IS NULL ORDER BY reviewed_on DESC LIMIT 1""", (problem_id,)).fetchone()
            if row is None or row["reviewed_on"] != self.today().isoformat():
                raise ReviewError(tr('只能撤销今天最近一次有效的复习记录。'))
            if problem["completed_count"] != row["count_after"]:
                raise ReviewError(tr('复习记录已发生变化，请刷新后重试。'))
            now = timestamp()
            self.db.execute("UPDATE reviews SET undone_at = ? WHERE id = ?", (now, row["id"]))
            self.db.execute("""UPDATE problems SET completed_count = ?, last_review_on = ?,
                next_review_on = ?, updated_at = ? WHERE id = ?""",
                (row["previous_count"], row["previous_last_on"], row["previous_next_on"], now, problem_id))

    def summary(self) -> dict:
        today = self.today().isoformat()
        result = {"active": 0, "due": 0, "overdue": 0, "done": 0}
        for problem in self.all():
            if not problem["archived"]:
                result["active"] += 1
                result["due"] += problem["next_review_on"] <= today
                result["overdue"] += problem["next_review_on"] < today
        result["done"] = self.db.execute("""SELECT COUNT(*) FROM reviews
            WHERE reviewed_on = ? AND undone_at IS NULL""", (today,)).fetchone()[0]
        return result

    def _document_snapshot(self) -> dict:
        problems = self.all()
        reviews = [dict(row) for row in self.db.execute(
            "SELECT * FROM reviews ORDER BY reviewed_on, created_at, id"
        )]
        return {"format": FORMAT, "version": SCHEMA_VERSION, "exported_at": timestamp(),
                "timezone": "Asia/Shanghai", "intervals": list(INTERVALS),
                "problems": problems, "reviews": reviews}

    def export_document(self) -> dict:
        # A read transaction keeps both tables in the same snapshot across app instances.
        with self.db:
            self.db.execute("BEGIN")
            return self._document_snapshot()

    def export_file(self, path: Path) -> Path:
        return atomic_json(path, self.export_document())

    def automatic_backup(self) -> Path:
        return self.export_file(self.data_dir / "backups" /
                                f"auto-{self.today().isoformat()}.json")

    def read_backup(self, path: Path) -> dict:
        path = Path(path)
        if path.stat().st_size > 25 * 1024 * 1024:
            raise ReviewError(tr('备份文件超过 25 MB，请选择本程序导出的备份。'))
        try:
            with path.open("r", encoding="utf-8-sig") as file:
                document = json.load(file)
        except (ValueError, UnicodeError, RecursionError):
            raise ReviewError(tr('这不是有效的 JSON 备份文件。')) from None
        self.validate_backup(document)
        return document

    @staticmethod
    def validate_backup(document: dict):
        def require(condition, message=None):
            if not condition:
                raise ReviewError(message or tr("备份内容不完整或不一致，未修改现有数据。"))

        def text(record, key, nullable=False):
            require(key in record)
            value = record.get(key)
            require((nullable and value is None) or isinstance(value, str))
            return value

        def integer(record, key):
            value = record.get(key)
            require(type(value) is int and 0 <= value <= 1_000_000)
            return value

        def valid_id(value):
            require(isinstance(value, str))
            try:
                uuid.UUID(value)
            except (ValueError, AttributeError):
                raise ReviewError(tr('备份中存在无效的题目或记录编号。')) from None
            return value

        require(isinstance(document, dict))
        require(document.get("format") == FORMAT and type(document.get("version")) is int
                and document["version"] == SCHEMA_VERSION, tr('请选择本程序导出的第 1 版备份文件。'))
        require(document.get("intervals") == list(INTERVALS), tr('备份使用了不同的复习规则，不能直接恢复。'))
        problems, reviews = document.get("problems"), document.get("reviews")
        require(isinstance(problems, list) and isinstance(reviews, list))
        require(len(problems) <= 100_000 and len(reviews) <= 500_000, tr('备份中的记录数量过多。'))
        by_id, history, review_ids = {}, {}, set()
        for problem in problems:
            require(isinstance(problem, dict))
            pid = valid_id(problem.get("id"))
            require(pid not in by_id)
            clean_fields(*(text(problem, key) for key in ("title", "learned_on", "notes", "url")))
            integer(problem, "completed_count")
            require(type(problem.get("archived")) is int and problem["archived"] in (0, 1))
            parse_day(text(problem, "next_review_on"))
            last = text(problem, "last_review_on", nullable=True)
            if last is not None:
                parse_day(last)
            for key in ("created_at", "updated_at"):
                require(bool(text(problem, key)))
            by_id[pid], history[pid] = problem, []
        for review in reviews:
            require(isinstance(review, dict))
            rid = valid_id(review.get("id"))
            pid = text(review, "problem_id")
            require(rid not in review_ids and pid in by_id)
            review_ids.add(rid)
            for key in ("reviewed_on", "previous_next_on", "next_on"):
                parse_day(text(review, key))
            last = text(review, "previous_last_on", nullable=True)
            if last is not None:
                parse_day(last)
            before, after = integer(review, "previous_count"), integer(review, "count_after")
            require(after == before + 1)
            try:
                expected = parse_day(review["reviewed_on"]) + timedelta(
                    days=INTERVALS[min(after, len(INTERVALS) - 1)])
            except OverflowError:
                raise ReviewError(tr('备份中的复习日期超出范围。')) from None
            require(review["next_on"] == expected.isoformat())
            require(bool(text(review, "created_at")))
            undone = text(review, "undone_at", nullable=True)
            require(undone is None or bool(undone))
            if undone is None:
                history[pid].append(review)
        for pid, problem in by_id.items():
            count, last = 0, None
            due = (parse_day(problem["learned_on"]) + timedelta(days=INTERVALS[0])).isoformat()
            for review in sorted(history[pid], key=lambda item: item["reviewed_on"]):
                require(review["previous_count"] == count and review["previous_last_on"] == last)
                require(review["previous_next_on"] == due and review["reviewed_on"] >= due)
                require(last is None or review["reviewed_on"] > last)
                count, last, due = review["count_after"], review["reviewed_on"], review["next_on"]
            require(problem["completed_count"] == count and problem["last_review_on"] == last
                    and problem["next_review_on"] == due)

    def restore_document(self, document: dict) -> Path:
        self.validate_backup(document)
        stamp = datetime.now(CHINA_TZ).strftime("%Y%m%d_%H%M%S_%f")
        snapshot = self.data_dir / "backups" / f"before-restore-{stamp}.json"
        problem_columns = ("id", "title", "learned_on", "notes", "url", "completed_count",
                           "last_review_on", "next_review_on", "archived", "created_at", "updated_at")
        review_columns = ("id", "problem_id", "reviewed_on", "previous_next_on", "previous_count",
                          "previous_last_on", "next_on", "count_after", "created_at", "undone_at")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            # Hold the writer lock while capturing the pre-restore state.
            atomic_json(snapshot, self._document_snapshot())
            self.db.execute("DELETE FROM reviews")
            self.db.execute("DELETE FROM problems")
            for table, columns, rows in (("problems", problem_columns, document["problems"]),
                                         ("reviews", review_columns, document["reviews"])):
                placeholders = ",".join("?" for _ in columns)
                self.db.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
                                    [tuple(row[column] for column in columns) for row in rows])
        return snapshot
