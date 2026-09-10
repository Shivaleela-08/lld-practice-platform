"""
LLD Practice Platform - server entrypoint.

Deliberately built on Python's stdlib http.server instead of Flask/FastAPI/
Express so there is nothing to `pip install` or `npm install` - just
`python server.py`. This sidesteps venv/path-length/package-version pain
entirely, which matters more than framework convenience for a 2-day
prototype meant to just run.

Routes
------
GET  /api/problems
GET  /api/problems/<id>
POST /api/attempts                       {problem_id, learner_id}
GET  /api/attempts?learner_id=<id>       -> attempt history
GET  /api/attempts/<id>
POST /api/attempts/<id>/submissions      {content, format}
POST /api/attempts/<id>/retry
GET  /api/submissions/<id>/feedback
GET  /                                   -> frontend/index.html (static files)
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from db import AttemptRepository, Database, EvaluationResultRepository, ProblemRepository, SubmissionRepository
from domain.models import Problem
from services.evaluation_service import EvaluationService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_LEARNER_ID = "default"  # auth is out of scope for this MVP - see DESIGN_NOTE.md

# -- bootstrap persistence + services (module-level singletons; fine for a
#    single-process prototype) --------------------------------------------
db = Database(os.path.join(DATA_DIR, "platform.db"))
problem_repo = ProblemRepository(db)
attempt_repo = AttemptRepository(db)
submission_repo = SubmissionRepository(db)
result_repo = EvaluationResultRepository(db)
service = EvaluationService(problem_repo, attempt_repo, submission_repo, result_repo)


def seed_problems():
    with open(os.path.join(DATA_DIR, "problems.json")) as f:
        raw = json.load(f)
    for p in raw:
        problem_repo.upsert(Problem(**p))


seed_problems()

ROUTES = [
    (re.compile(r"^/api/problems$"), "GET"),
    (re.compile(r"^/api/problems/(?P<id>[\w-]+)$"), "GET"),
    (re.compile(r"^/api/attempts$"), "POST"),
    (re.compile(r"^/api/attempts$"), "GET"),
    (re.compile(r"^/api/attempts/(?P<id>[\w-]+)$"), "GET"),
    (re.compile(r"^/api/attempts/(?P<id>[\w-]+)/submissions$"), "POST"),
    (re.compile(r"^/api/attempts/(?P<id>[\w-]+)/retry$"), "POST"),
    (re.compile(r"^/api/submissions/(?P<id>[\w-]+)/feedback$"), "GET"),
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    # -- helpers --------------------------------------------------------

    def _send_json(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str):
        self._send_json(status, {"error": message})

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _serve_static(self, path: str):
        if path == "/":
            path = "/index.html"
        file_path = os.path.normpath(os.path.join(FRONTEND_DIR, path.lstrip("/")))
        if not file_path.startswith(FRONTEND_DIR) or not os.path.isfile(file_path):
            self._send_error_json(404, "Not found")
            return
        content_type = {
            ".html": "text/html", ".js": "application/javascript", ".css": "text/css",
        }.get(os.path.splitext(file_path)[1], "application/octet-stream")
        with open(file_path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- HTTP verbs -------------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not path.startswith("/api/"):
            self._serve_static(path)
            return

        try:
            if path == "/api/problems":
                problems = [p.to_dict() for p in problem_repo.list_all()]
                self._send_json(200, {"problems": problems})
                return

            m = re.match(r"^/api/problems/(?P<id>[\w-]+)$", path)
            if m:
                p = problem_repo.get(m.group("id"))
                if not p:
                    return self._send_error_json(404, "Problem not found")
                return self._send_json(200, p.to_dict())

            if path == "/api/attempts":
                qs = parse_qs(parsed.query)
                learner_id = qs.get("learner_id", [DEFAULT_LEARNER_ID])[0]
                attempts = [a.to_dict() for a in attempt_repo.list_for_learner(learner_id)]
                return self._send_json(200, {"attempts": attempts})

            m = re.match(r"^/api/attempts/(?P<id>[\w-]+)$", path)
            if m:
                a = attempt_repo.get(m.group("id"))
                if not a:
                    return self._send_error_json(404, "Attempt not found")
                return self._send_json(200, a.to_dict())

            m = re.match(r"^/api/submissions/(?P<id>[\w-]+)/feedback$", path)
            if m:
                fb = service.get_feedback(m.group("id"))
                if not fb:
                    return self._send_json(200, {"ready": False})
                return self._send_json(200, {"ready": True, "feedback": fb.to_dict()})

            self._send_error_json(404, "Not found")
        except Exception as exc:  # noqa: BLE001
            self._send_error_json(500, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        try:
            if path == "/api/attempts":
                problem_id = body.get("problem_id")
                learner_id = body.get("learner_id", DEFAULT_LEARNER_ID)
                attempt = service.start_attempt(problem_id, learner_id)
                return self._send_json(201, attempt.to_dict())

            m = re.match(r"^/api/attempts/(?P<id>[\w-]+)/submissions$", path)
            if m:
                content = body.get("content", "")
                fmt = body.get("format", "TEXT_DESIGN")
                attempt = service.submit(m.group("id"), content, fmt)
                return self._send_json(202, attempt.to_dict())

            m = re.match(r"^/api/attempts/(?P<id>[\w-]+)/retry$", path)
            if m:
                attempt = service.retry(m.group("id"))
                return self._send_json(202, attempt.to_dict())

            self._send_error_json(404, "Not found")
        except ValueError as exc:
            self._send_error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._send_error_json(500, str(exc))


def main():
    port = int(os.environ.get("PORT", 8000))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"LLD Practice Platform running on http://localhost:{port}")
    if not os.environ.get("GEMINI_API_KEY"):
        print("NOTE: GEMINI_API_KEY is not set - AI-dimension feedback will be unavailable and evaluation will fall back to deterministic-only results (or FAIL if that also fails). See README.md.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
