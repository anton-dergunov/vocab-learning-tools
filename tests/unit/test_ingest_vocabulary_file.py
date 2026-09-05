"""The Obsidian ingest walk, against a stubbed ingest endpoint.

The interesting behaviour is entirely in how the walk advances: the server says how many leading
lines one entry occupied, and the script has to move by exactly that, resume where it stopped, and
never lose a word to a bad answer.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "ingest_vocabulary_file", REPO_ROOT / "scripts" / "ingest_vocabulary_file.py"
)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


# The shapes the real notes actually take: blank-line-separated blocks, `---` rules, and runs of
# consecutive one-line entries with no separator at all.
NOTES = """inquisitive - любознательный
Inquisitive about coffee? - Хотите узнать больше о кофе?

---

turmoil - суматоха
Since then I have been navigating the job market.

Toil - тяжёлый труд
Consonant - согласный
"""


class Stub:
    """Stands in for the server: hands back a fixed sequence of capture answers."""

    def __init__(self, answers: list[dict], languages: list[str] | None = None,
                 topics: list[str] | None = None) -> None:
        self.answers = answers
        self.languages = languages if languages is not None else ["en"]
        self.topics = topics if topics is not None else ["Slang"]
        self.requests: list[dict] = []
        self.calls = 0

    @property
    def received(self) -> list[str]:
        return [request.get("text", "") for request in self.requests]

    def next_answer(self, payload: dict) -> dict:
        self.requests.append(payload)
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return answer


@pytest.fixture
def server():
    holder: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # noqa: N802 - silence the default access log
            pass

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path.endswith("/session"):
                body, status = {"data": {"token": "t", "user": {"id": "o", "email": "e"}}}, 200
            else:
                answer = holder["stub"].next_answer(payload)
                if "error" in answer:
                    body, status = {"error": answer["error"]}, answer["error"].get("status", 400)
                else:
                    body, status = {"data": answer}, 200
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
            stub = holder["stub"]
            body = {"data": {"changes": {
                "vocabularies": [
                    {"language": language, "deleted": False} for language in stub.languages
                ],
                "topics": [
                    {"name": topic, "deleted": False} for topic in stub.topics
                ],
            }}}
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    holder["url"] = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield holder
    httpd.shutdown()


def answer(headword: str, consumed: int, duplicates: list | None = None) -> dict:
    return {
        "resolution": {
            "language": "en", "headword": headword, "lemma": headword, "pos": "noun",
            "sentences": [], "note": None, "consumedLines": consumed, "consumedText": None,
        },
        "duplicates": duplicates or [],
        "draft": {"headword": headword, "senses": [{}]},
        "applied": {"lexemeId": "a" * 15},
    }


def run(server, source: Path, checkpoints: Path, monkeypatch, *extra: str) -> int:
    monkeypatch.setenv("ACERVO_PASSWORD", "secret")
    monkeypatch.setattr("sys.argv", [
        "ingest_vocabulary_file.py", str(source),
        "--server-url", server["url"], "--owner-email", "learner@account.example.com",
        "--checkpoint-dir", str(checkpoints), "--rate-limit", "0", *extra,
    ])
    return ingest.main()


def test_walks_the_file_one_entry_at_a_time_without_touching_it(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "English vocabulary.md"
    source.write_text(NOTES, encoding="utf-8")
    original = source.read_text(encoding="utf-8")
    server["stub"] = Stub([answer("inquisitive", 2), answer("turmoil", 2), answer("toil", 1), answer("consonant", 1)])

    assert run(server, source, tmp_path / "state", monkeypatch) == 0

    # The default mode is non-destructive: the notes are exactly as they were.
    assert source.read_text(encoding="utf-8") == original
    assert "4 created" in capsys.readouterr().out
    # Each call starts on the entry after the one before, and the rule between blocks is skipped
    # locally rather than costing a call.
    assert server["stub"].received[0].startswith("inquisitive")
    assert server["stub"].received[1].startswith("turmoil")
    assert server["stub"].received[2].startswith("Toil")
    assert server["stub"].received[3].startswith("Consonant")


def test_resumes_from_the_checkpoint_rather_than_starting_again(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    checkpoints = tmp_path / "state"
    server["stub"] = Stub([answer("inquisitive", 2)])
    assert run(server, source, checkpoints, monkeypatch, "--limit", "1") == 0
    capsys.readouterr()

    server["stub"] = Stub([answer("turmoil", 2)])
    assert run(server, source, checkpoints, monkeypatch, "--limit", "1") == 0
    assert server["stub"].received[0].startswith("turmoil")

    # And --restart deliberately ignores what was already done.
    server["stub"] = Stub([answer("inquisitive", 2)])
    assert run(server, source, checkpoints, monkeypatch, "--limit", "1", "--restart") == 0
    assert server["stub"].received[0].startswith("inquisitive")


def test_consume_cuts_each_entry_out_so_what_is_left_is_the_queue(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    server["stub"] = Stub([answer("inquisitive", 2), answer("turmoil", 2)])

    assert run(server, source, tmp_path / "state", monkeypatch, "--consume", "--limit", "2") == 0

    remaining = source.read_text(encoding="utf-8")
    assert "inquisitive" not in remaining
    assert "turmoil" not in remaining
    assert remaining.strip().startswith("Toil")
    # The original is recoverable, which is what makes cutting safe to offer at all.
    assert "inquisitive" in (tmp_path / "notes.md.bak").read_text(encoding="utf-8")


def test_a_duplicate_is_reported_and_the_walk_carries_on(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    server["stub"] = Stub([
        answer("inquisitive", 2, duplicates=[{"id": "b" * 15, "headword": "inquisitive"}]),
        answer("turmoil", 2),
    ])

    assert run(server, source, tmp_path / "state", monkeypatch, "--limit", "2") == 0
    output = capsys.readouterr().out
    assert "already in your vocabulary" in output
    assert "1 created, 1 already known" in output


def test_an_unreadable_block_is_skipped_instead_of_stalling_the_walk(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    server["stub"] = Stub([
        {"error": {"code": "unreadable_input", "message": "Not a word.", "status": 422}},
        answer("turmoil", 2),
    ])

    assert run(server, source, tmp_path / "state", monkeypatch, "--limit", "2") == 0
    # Without the local fallback the walk would resubmit the same lines for ever.
    assert server["stub"].received[1].startswith("turmoil")
    assert "1 created, 0 already known, 1 skipped" in capsys.readouterr().out


def test_an_unconfigured_language_stops_the_run_rather_than_failing_every_entry(server, tmp_path, monkeypatch):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    server["stub"] = Stub([
        {"error": {"code": "language_not_configured", "message": "No en vocabulary.", "status": 409}},
    ])

    assert run(server, source, tmp_path / "state", monkeypatch) == 1
    assert server["stub"].calls == 1


def test_preflight_refuses_a_missing_language_and_topic_before_capture(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    checkpoints = tmp_path / "state"
    server["stub"] = Stub([answer("inquisitive", 2)], languages=["es"], topics=["Food"])

    assert run(server, source, checkpoints, monkeypatch, "--language", "en") == 1
    assert server["stub"].calls == 0
    assert not checkpoints.exists()
    assert "no en vocabulary" in capsys.readouterr().err

    server["stub"] = Stub([answer("inquisitive", 2)], languages=["en"], topics=["Food"])
    assert run(server, source, checkpoints, monkeypatch, "--topic", "Actions") == 1
    assert server["stub"].calls == 0
    assert "missing Actions" in capsys.readouterr().err


def test_transient_provider_failures_retry_then_succeed(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    server["stub"] = Stub([
        {"error": {"code": "llm_rate_limited", "message": "Busy.", "status": 503}},
        {"error": {"code": "llm_unavailable", "message": "Unavailable.", "status": 503}},
        answer("inquisitive", 2),
    ])
    sleeps = []
    monkeypatch.setattr(ingest.time, "sleep", sleeps.append)

    assert run(server, source, tmp_path / "state", monkeypatch, "--limit", "1") == 0
    assert server["stub"].calls == 3
    assert sleeps == [15, 30]
    assert "1 created" in capsys.readouterr().out


def test_exhausted_transient_retries_do_not_advance_checkpoint(server, tmp_path, monkeypatch):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    checkpoints = tmp_path / "state"
    failure = {"error": {"code": "llm_rate_limited", "message": "Busy.", "status": 503}}
    server["stub"] = Stub([failure, failure, failure, failure])
    monkeypatch.setattr(ingest.time, "sleep", lambda _seconds: None)

    assert run(server, source, checkpoints, monkeypatch, "--limit", "1") == 1
    assert server["stub"].calls == 4
    assert not checkpoints.exists()


def test_checkpoints_are_specific_to_the_resolved_source_path(server, tmp_path, monkeypatch, capsys):
    first = tmp_path / "one" / "notes.md"
    second = tmp_path / "two" / "notes.md"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text(NOTES, encoding="utf-8")
    second.write_text(NOTES, encoding="utf-8")
    checkpoints = tmp_path / "state"

    server["stub"] = Stub([answer("inquisitive", 2)])
    assert run(server, first, checkpoints, monkeypatch, "--limit", "1") == 0
    capsys.readouterr()
    server["stub"] = Stub([answer("inquisitive", 2)])
    assert run(server, second, checkpoints, monkeypatch, "--limit", "1") == 0
    capsys.readouterr()
    assert len(list(checkpoints.glob("notes.md.*.json"))) == 2

    server["stub"] = Stub([answer("turmoil", 2)])
    assert run(server, first, checkpoints, monkeypatch, "--limit", "1") == 0
    assert server["stub"].received[0].startswith("turmoil")


def test_a_dry_run_creates_nothing_and_leaves_no_checkpoint(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    checkpoints = tmp_path / "state"
    server["stub"] = Stub([answer("inquisitive", 2)])

    assert run(server, source, checkpoints, monkeypatch, "--dry-run", "--limit", "1") == 0
    assert not checkpoints.exists()
    assert "not created" in capsys.readouterr().out
    # The flag the server acts on, not merely what the script printed.
    assert server["stub"].requests[0]["apply"] is False


def test_a_real_run_asks_the_server_to_apply_and_passes_the_topic_through(server, tmp_path, monkeypatch, capsys):
    source = tmp_path / "notes.md"
    source.write_text(NOTES, encoding="utf-8")
    server["stub"] = Stub([answer("inquisitive", 2)])

    assert run(server, source, tmp_path / "state", monkeypatch, "--limit", "1", "--topic", "Slang") == 0
    request = server["stub"].requests[0]
    assert request["apply"] is True
    assert request["mode"] == "stream"
    # Files already filed under a heading know their own topic better than the model can infer it.
    assert request["topics"] == ["Slang"]


def test_the_local_block_fallback_stops_at_a_separator():
    lines = ["turmoil - суматоха", "an example line", "", "---", "", "Toil - тяжёлый труд"]
    assert ingest.logical_block(lines) == 5
    # No separator anywhere: consume the window rather than guessing a smaller step.
    assert ingest.logical_block(["one", "two"]) == 2
