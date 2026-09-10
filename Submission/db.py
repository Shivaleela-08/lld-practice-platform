"""
Persistence layer.

Uses Python's built-in sqlite3 - no driver install, no separate DB server,
a single file (data/platform.db) the learner can delete to reset state.
One repository class per aggregate keeps SQL out of the domain/services
layers and gives a single seam to swap storage later (e.g. Postgres) by
reimplementing these four classes only.
"""

import json
import sqlite3
import threading
from typing import List, Optional

from domain.models import (
    Attempt,
    AttemptStatus,
    DimensionScore,
    EvaluationResult,
    EvaluatorKind,
    Problem,
    Submission,
    SubmissionFormat,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY,
    title TEXT, difficulty TEXT, summary TEXT,
    requirements TEXT, hints TEXT, tags TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    problem_id TEXT, learner_id TEXT, status TEXT,
    created_at REAL, updated_at REAL, submission_id TEXT, failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    attempt_id TEXT, content TEXT, format TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS evaluation_results (
    id TEXT PRIMARY KEY,
    submission_id TEXT, evaluator_kind TEXT, dimension_scores TEXT,
    confidence REAL, error TEXT
);
"""

_lock = threading.Lock()  # sqlite3 connections aren't safely shared across threads without care


class Database:
    def __init__(self, path: str = "data/platform.db"):
        self.path = path
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


class ProblemRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, p: Problem) -> None:
        with _lock:
            conn = self.db._connect()
            conn.execute(
                "INSERT OR REPLACE INTO problems VALUES (?,?,?,?,?,?,?)",
                (p.id, p.title, p.difficulty, p.summary,
                 json.dumps(p.requirements), json.dumps(p.hints), json.dumps(p.tags)),
            )
            conn.commit()
            conn.close()

    def get(self, problem_id: str) -> Optional[Problem]:
        with _lock:
            conn = self.db._connect()
            row = conn.execute("SELECT * FROM problems WHERE id=?", (problem_id,)).fetchone()
            conn.close()
        return self._row_to_problem(row) if row else None

    def list_all(self) -> List[Problem]:
        with _lock:
            conn = self.db._connect()
            rows = conn.execute("SELECT * FROM problems").fetchall()
            conn.close()
        return [self._row_to_problem(r) for r in rows]

    @staticmethod
    def _row_to_problem(row) -> Problem:
        return Problem(
            id=row["id"], title=row["title"], difficulty=row["difficulty"],
            summary=row["summary"], requirements=json.loads(row["requirements"]),
            hints=json.loads(row["hints"]), tags=json.loads(row["tags"]),
        )


class AttemptRepository:
    def __init__(self, db: Database):
        self.db = db

    def save(self, a: Attempt) -> None:
        with _lock:
            conn = self.db._connect()
            conn.execute(
                "INSERT OR REPLACE INTO attempts VALUES (?,?,?,?,?,?,?,?)",
                (a.id, a.problem_id, a.learner_id, a.status.value,
                 a.created_at, a.updated_at, a.submission_id, a.failure_reason),
            )
            conn.commit()
            conn.close()

    def get(self, attempt_id: str) -> Optional[Attempt]:
        with _lock:
            conn = self.db._connect()
            row = conn.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            conn.close()
        return self._row_to_attempt(row) if row else None

    def list_for_learner(self, learner_id: str) -> List[Attempt]:
        with _lock:
            conn = self.db._connect()
            rows = conn.execute(
                "SELECT * FROM attempts WHERE learner_id=? ORDER BY created_at DESC",
                (learner_id,),
            ).fetchall()
            conn.close()
        return [self._row_to_attempt(r) for r in rows]

    @staticmethod
    def _row_to_attempt(row) -> Attempt:
        return Attempt(
            id=row["id"], problem_id=row["problem_id"], learner_id=row["learner_id"],
            status=AttemptStatus(row["status"]), created_at=row["created_at"],
            updated_at=row["updated_at"], submission_id=row["submission_id"],
            failure_reason=row["failure_reason"],
        )


class SubmissionRepository:
    def __init__(self, db: Database):
        self.db = db

    def save(self, s: Submission) -> None:
        with _lock:
            conn = self.db._connect()
            conn.execute(
                "INSERT OR REPLACE INTO submissions VALUES (?,?,?,?,?)",
                (s.id, s.attempt_id, s.content, s.format.value, s.created_at),
            )
            conn.commit()
            conn.close()

    def get(self, submission_id: str) -> Optional[Submission]:
        with _lock:
            conn = self.db._connect()
            row = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
            conn.close()
        if not row:
            return None
        return Submission(
            id=row["id"], attempt_id=row["attempt_id"], content=row["content"],
            format=SubmissionFormat(row["format"]), created_at=row["created_at"],
        )


class EvaluationResultRepository:
    def __init__(self, db: Database):
        self.db = db

    def save(self, r: EvaluationResult) -> None:
        with _lock:
            conn = self.db._connect()
            conn.execute(
                "INSERT OR REPLACE INTO evaluation_results VALUES (?,?,?,?,?,?)",
                (r.id, r.submission_id, r.evaluator_kind.value,
                 json.dumps([d.to_dict() for d in r.dimension_scores]),
                 r.confidence, r.error),
            )
            conn.commit()
            conn.close()

    def list_for_submission(self, submission_id: str) -> List[EvaluationResult]:
        with _lock:
            conn = self.db._connect()
            rows = conn.execute(
                "SELECT * FROM evaluation_results WHERE submission_id=?", (submission_id,)
            ).fetchall()
            conn.close()
        results = []
        for row in rows:
            dims = [DimensionScore(**d) for d in json.loads(row["dimension_scores"])]
            results.append(EvaluationResult(
                id=row["id"], submission_id=row["submission_id"],
                evaluator_kind=EvaluatorKind(row["evaluator_kind"]),
                dimension_scores=dims, confidence=row["confidence"], error=row["error"],
            ))
        return results
