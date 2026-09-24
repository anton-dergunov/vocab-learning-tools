"""The job record and the runner, with a test kind standing in for real work.

What is pinned here is the machinery every kind inherits (`docs/plans/processing-flow.md` §4.2,
§4.5, §4.6): queue, run, rest, cancel, interrupted-on-restart, one open `enrich` per word, and
nothing kept past its retention except a failure nobody has dismissed.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from acervo import admin
from acervo.errors import ApiError
from acervo.repository import jobs
from acervo.repository.session import transaction
from acervo.work import kinds, retry
from acervo.work.kinds import Kind
from acervo.work.runner import Runner, _epoch


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def runner(server, clock) -> Runner:
    return Runner(server.settings, clock=clock)


@pytest.fixture
def script():
    """A test kind whose steps do whatever the test lists, in order, once per run."""
    plan: dict[str, list] = {"first": [], "second": []}
    seen: list[str] = []

    def act(name):
        def body(step):
            seen.append(name)
            outcome = plan[name].pop(0) if plan[name] else None
            if isinstance(outcome, BaseException):
                raise outcome
            if callable(outcome):
                return outcome(step)
            return outcome
        return body

    def handler(context):
        context.step("first", act("first"), lane="text")
        context.step("second", act("second"), lane="image")

    registered = {name: kinds.find(name) for name in ("test.script", "enrich")}
    kinds.register(Kind("test.script", ("first", "second"), handler))
    kinds.register(Kind("enrich", ("first", "second"), handler))
    yield plan, seen
    for name, kind in registered.items():
        if kind is None:
            kinds.unregister(name)
        else:
            kinds.register(kind)


def queue(server, kind="test.script", **overrides):
    return jobs.enqueue(server.owner, kind, trigger=overrides.pop("trigger", "manual"), **overrides)


# ── running ─────────────────────────────────────────────────────────────────


def test_a_queued_job_runs_its_steps_in_order_and_finishes(server, runner, script):
    plan, seen = script
    queued = queue(server)
    assert queued["state"] == "queued"
    assert runner.run_until_idle() == 1
    finished = jobs.get(server.owner, queued["id"])
    assert finished["state"] == "done"
    assert seen == ["first", "second"]
    assert [(s["name"], s["state"]) for s in finished["steps"]] == [
        ("first", "done"), ("second", "done")
    ]
    assert finished["startedAt"] and finished["finishedAt"]


def test_a_step_with_nothing_to_do_is_skipped_rather_than_done(server, runner, script):
    plan, _ = script
    plan["first"].append("skipped")
    queued = queue(server)
    runner.run_until_idle()
    assert jobs.get(server.owner, queued["id"])["steps"][0]["state"] == "skipped"


def test_a_failed_step_is_recorded_and_the_next_one_still_runs(server, runner, script):
    plan, seen = script
    plan["first"].append(ApiError(502, "corpus_failed", "The corpus refused."))
    queued = queue(server)
    runner.run_until_idle()
    finished = jobs.get(server.owner, queued["id"])
    assert seen == ["first", "second"]
    assert finished["state"] == "failed"
    assert finished["error"] == "corpus_failed"
    assert finished["steps"][0] == {
        "name": "first", "state": "failed", "error": "corpus_failed",
        "message": "The corpus refused.",
    }
    assert finished["steps"][1]["state"] == "done"


def test_a_crashing_step_is_a_failed_step_not_a_dead_runner(server, runner, script):
    plan, seen = script
    plan["first"].append(RuntimeError("boom"))
    queued = queue(server)
    runner.run_until_idle()
    finished = jobs.get(server.owner, queued["id"])
    assert finished["steps"][0]["error"] == "server_error"
    assert seen == ["first", "second"]


def test_an_unknown_kind_fails_rather_than_waiting_forever(server, runner):
    queued = queue(server, kind="no.such.kind")
    runner.run_until_idle()
    finished = jobs.get(server.owner, queued["id"])
    assert (finished["state"], finished["error"]) == ("failed", "unknown_kind")


# ── retry ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", sorted(retry.TRANSIENT))
def test_a_transient_failure_rests_and_the_job_yields_the_lane(server, runner, script, clock, code):
    plan, seen = script
    plan["first"].append(ApiError(503, code, "Busy."))
    queued = queue(server)

    assert runner.run_until_idle() == 1
    resting = jobs.get(server.owner, queued["id"])
    assert resting["state"] == "queued"
    assert resting["notBefore"] is not None
    assert resting["steps"][0]["state"] == "waiting"
    assert resting["steps"][0]["rests"] == 1
    assert seen == ["first"], "the job must not go on while its step waits"

    # Not due yet: nothing to take.
    assert runner.run_until_idle() == 0
    clock.advance(retry.FIRST_REST + 1)
    assert runner.run_until_idle() == 1
    finished = jobs.get(server.owner, queued["id"])
    assert finished["state"] == "done"
    assert seen == ["first", "first", "second"]


def test_a_resting_step_says_what_it_is_waiting_for_and_forgets_it_once_it_answers(
        server, runner, script, clock):
    plan, _ = script
    plan["first"].append(ApiError(503, "llm_unavailable", "Busy.",
                                  "Gemini (free tier) is overloaded"))
    queued = queue(server)
    runner.run_until_idle()
    assert jobs.get(server.owner, queued["id"])["steps"][0]["waitingOn"] == \
        "Gemini (free tier) is overloaded"

    clock.advance(retry.FIRST_REST + 1)
    runner.run_until_idle()
    assert "waitingOn" not in jobs.get(server.owner, queued["id"])["steps"][0]


def test_a_kind_that_is_nothing_until_its_step_succeeds_waits_longer(server, runner, script, clock):
    """A story rests twenty times, about three hours, where a word's enrichment rests six: a story
    that gives up is a Try again button with nothing behind it."""
    plan, seen = script
    patient = kinds.find("test.script")
    kinds.register(Kind("test.script", patient.steps, patient.handler, rests=retry.MAX_RESTS + 3))
    plan["first"].extend(ApiError(503, "llm_unavailable", "Busy.") for _ in range(retry.MAX_RESTS + 3))
    queued = queue(server)
    for _ in range(retry.MAX_RESTS + 4):
        runner.run_until_idle()
        clock.advance(retry.LONGEST_REST + 1)
    finished = jobs.get(server.owner, queued["id"])
    assert finished["state"] == "done", "the tenth try answered, inside its patience"
    assert seen.count("first") == retry.MAX_RESTS + 4
    assert kinds.find("story").rests == retry.STORY_RESTS > retry.MAX_RESTS


def test_a_step_that_got_somewhere_before_it_was_refused_rests_from_the_first_rest(
        server, runner, script, clock):
    """Two pictures and then a 429 is an allowance refilling, not a provider failing: the lane's
    rest starts again from thirty seconds instead of doubling towards ten minutes."""
    plan, _ = script

    def drew_two_then_refused(step):
        step.progress(2, 4)
        raise ApiError(503, "llm_rate_limited", "Quota.")

    for _ in range(3):  # a streak, as a lane that kept being refused would have
        runner.lanes["text"].penalise()
    plan["first"].append(drew_two_then_refused)
    queued = queue(server)
    runner.run_until_idle()
    resting = jobs.get(server.owner, queued["id"])
    waited = _epoch(resting["notBefore"]) - clock()
    assert waited == pytest.approx(retry.FIRST_REST, abs=1)


def test_a_paced_lane_says_it_is_keeping_to_its_allowance(server, script, monkeypatch):
    """One picture a minute is kept to rather than discovered by refusal, and the row says so."""
    monkeypatch.setitem(retry.LANES, "image", 1)
    runner = Runner(server.settings)
    plan, seen = script

    def draw_twice(step):
        step.gate()
        step.gate()

    plan["second"].append(draw_twice)
    queued = queue(server)
    runner.run_until_idle()
    waiting = jobs.get(server.owner, queued["id"])
    assert waiting["state"] == "queued"
    assert waiting["steps"][1]["state"] == "waiting"
    assert waiting["steps"][1]["waitingOn"] == "keeping to 1 picture a minute"


def test_a_resting_job_does_not_hold_up_the_next_one(server, runner, script):
    plan, _ = script
    plan["first"].append(ApiError(503, "llm_rate_limited", "Quota."))
    resting = queue(server)
    behind = queue(server)
    runner.run_until_idle()
    assert jobs.get(server.owner, resting["id"])["state"] == "queued"
    assert jobs.get(server.owner, behind["id"])["state"] == "done"


@pytest.mark.parametrize("code", ["llm_authentication", "llm_failed", "llm_unusable", "not_found"])
def test_anything_else_is_not_worth_asking_again(server, runner, script, code):
    plan, seen = script
    plan["first"].append(ApiError(502, code, "No."))
    queued = queue(server)
    runner.run_until_idle()
    assert jobs.get(server.owner, queued["id"])["steps"][0]["state"] == "failed"
    assert seen == ["first", "second"]


def test_a_step_gives_up_after_so_many_rests(server, runner, script, clock):
    plan, seen = script
    plan["first"].extend(
        ApiError(503, "llm_unavailable", "Busy.") for _ in range(retry.MAX_RESTS + 1)
    )
    queued = queue(server)
    for _ in range(retry.MAX_RESTS + 1):
        runner.run_until_idle()
        clock.advance(retry.LONGEST_REST + 1)
    finished = jobs.get(server.owner, queued["id"])
    assert finished["state"] == "failed"
    assert finished["steps"][0]["error"] == "llm_unavailable"
    assert seen.count("first") == retry.MAX_RESTS + 1
    assert seen[-1] == "second"


def test_a_resting_lane_is_waited_out_before_the_call_not_after(server, runner, script, clock):
    """A gate before each model call is what stops a second job spending a refused allowance."""
    plan, seen = script
    runner.lanes["text"].penalise()
    plan["first"].append(lambda step: step.gate())
    queued = queue(server)
    runner.run_until_idle()
    waiting = jobs.get(server.owner, queued["id"])
    assert waiting["state"] == "queued"
    assert waiting["steps"][0]["state"] == "waiting"
    assert "rests" not in waiting["steps"][0], "waiting out someone else's rest is not a retry"


# ── cancelling ──────────────────────────────────────────────────────────────


def test_a_queued_job_is_cancelled_at_once(server, runner, script):
    queued = queue(server)
    cancelled = jobs.request_cancel(server.owner, queued["id"])
    assert cancelled["state"] == "cancelled"
    assert runner.run_until_idle() == 0


def test_a_running_job_stops_at_its_next_check(server, runner, script):
    plan, seen = script
    queued = queue(server)
    plan["first"].append(lambda step: jobs.request_cancel(server.owner, queued["id"]) and None)
    runner.run_until_idle()
    finished = jobs.get(server.owner, queued["id"])
    assert finished["state"] == "cancelled"
    assert seen == ["first"]


def test_somebody_elses_job_cannot_be_cancelled_or_read(server, other, runner, script):
    queued = queue(server)
    assert jobs.request_cancel(other.owner, queued["id"]) is None
    assert jobs.get(other.owner, queued["id"]) is None
    assert jobs.get(server.owner, queued["id"])["state"] == "queued"


def test_a_late_finish_does_not_revive_a_cancelled_job(server, script):
    queued = queue(server)
    claimed = jobs.claim_next("9999-12-31T00:00:00.000Z")
    assert claimed["id"] == queued["id"]
    jobs.cancel_all()
    jobs.abandon_running()
    finished, _ = jobs.finish(queued["id"], "done")
    assert finished["state"] == "cancelled"


# ── restarts and retention ──────────────────────────────────────────────────


def test_a_job_running_when_the_process_stopped_is_marked_interrupted(server, runner, script):
    queued = queue(server)
    waiting = queue(server)
    jobs.claim_next("9999-12-31T00:00:00.000Z")  # the process that took it went away
    runner.recover()
    interrupted = jobs.get(server.owner, queued["id"])
    assert (interrupted["state"], interrupted["error"]) == ("failed", jobs.INTERRUPTED)
    assert jobs.get(server.owner, waiting["id"])["state"] == "queued", "queued jobs simply start"
    runner.run_until_idle()
    assert jobs.get(server.owner, waiting["id"])["state"] == "done"


def test_finished_jobs_are_pruned_but_an_undismissed_failure_is_kept(server, runner, script):
    plan, _ = script
    done = queue(server)
    runner.run_until_idle()
    plan["first"].append(ApiError(502, "llm_failed", "No."))
    failed = queue(server)
    runner.run_until_idle()
    dismissed_failure = queue(server)
    plan["first"].append(ApiError(502, "llm_failed", "No."))
    runner.run_until_idle()
    jobs.dismiss(server.owner, dismissed_failure["id"])

    assert jobs.prune("9999-12-31T00:00:00.000Z") == 2
    assert jobs.get(server.owner, done["id"]) is None
    assert jobs.get(server.owner, dismissed_failure["id"]) is None
    assert jobs.get(server.owner, failed["id"])["state"] == "failed"


def test_an_open_job_cannot_be_dismissed(server, script):
    queued = queue(server)
    assert jobs.dismiss(server.owner, queued["id"])["dismissed"] is False


# ── one open enrich per word ────────────────────────────────────────────────


def _enrich(server, lexeme="lexemepicar0001"):
    with transaction() as connection:
        return jobs.enqueue_enrich(connection, server.owner, lexeme, trigger="save")


def test_a_second_request_meets_the_queued_job_and_does_nothing(server, script):
    first = _enrich(server)
    second = _enrich(server)
    assert second["id"] == first["id"]
    assert len(jobs.open_jobs(server.owner)) == 1


def test_a_request_during_a_run_queues_one_more_run_after_it(server, runner, script):
    plan, seen = script
    first = _enrich(server)

    def meanwhile(step):
        again = _enrich(server)
        assert again["id"] == first["id"]
        assert again["rerun"] is True
        _enrich(server)  # a third request asks for nothing more

    plan["first"].append(meanwhile)
    assert runner.run_until_idle() == 2
    finished = [j for j in jobs.recent(server.owner) if j["kind"] == "enrich"]
    assert [j["state"] for j in finished] == ["done", "done"]
    assert seen == ["first", "second", "first", "second"]


def test_each_word_has_its_own_enrich(server, script):
    _enrich(server, "lexemepicar0001")
    _enrich(server, "lexemepicar0002")
    assert len(jobs.open_jobs(server.owner)) == 2


def test_the_index_refuses_a_second_open_enrich_if_the_check_is_ever_skipped(server, script):
    """The guard behind the guard."""
    from sqlalchemy.exc import IntegrityError

    _enrich(server)
    with pytest.raises(IntegrityError):
        with transaction() as connection:
            jobs._insert(connection, server.owner, "enrich", trigger="save",
                         subject_kind="lexeme", subject_id="lexemepicar0001")


def test_a_child_names_its_parent_and_the_parent_lists_it(server, script):
    parent = queue(server, kind="test.script")
    with transaction() as connection:
        child = jobs.enqueue_enrich(connection, server.owner, "lexemepicar0001",
                                    trigger="ingest", parent=parent["id"])
    assert child["parentId"] == parent["id"]
    assert [c["id"] for c in jobs.get(server.owner, parent["id"])["children"]] == [child["id"]]


def test_cancelling_a_parent_cancels_its_open_children(server, script):
    parent = queue(server, kind="test.script")
    with transaction() as connection:
        child = jobs.enqueue_enrich(connection, server.owner, "lexemepicar0001",
                                    trigger="ingest", parent=parent["id"])
    jobs.request_cancel(server.owner, parent["id"])
    assert jobs.get(server.owner, child["id"])["state"] == "cancelled"


# ── the served application ──────────────────────────────────────────────────


def test_the_served_application_runs_its_runner(server, script):
    """Entered as a context manager, the test client runs the lifespan — as uvicorn does."""
    with TestClient(server.client.app):
        queued = queue(server)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if jobs.get(server.owner, queued["id"])["state"] == "done":
                break
            time.sleep(0.05)
    assert jobs.get(server.owner, queued["id"])["state"] == "done"


def test_a_job_queued_by_another_process_is_found_by_polling(server, script):
    from acervo import notify

    runner = server.client.app.state.runner
    runner.poll = 0.1
    with TestClient(server.client.app):
        queued = queue(server)
        notify.work_arrived.clear()  # as though nothing in this process had been told
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if jobs.get(server.owner, queued["id"])["state"] == "done":
                break
            time.sleep(0.05)
    assert jobs.get(server.owner, queued["id"])["state"] == "done"


# ── the admin commands a deploy runs ─────────────────────────────────────────


def test_admin_reports_open_jobs_as_json(server, script, capsys):
    queue(server)
    queue(server)
    _enrich(server)
    assert admin.main(["jobs", "open", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "open": 3, "byKind": {"enrich": 1, "test.script": 2}
    }


def test_admin_reports_nothing_open(server, capsys):
    assert admin.main(["jobs", "open", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"open": 0, "byKind": {}}


def test_admin_cancels_everything_and_abandons_a_job_the_runner_never_let_go(server, script, capsys):
    running = queue(server)
    queued = queue(server)
    jobs.claim_next("9999-12-31T00:00:00.000Z")  # takes the oldest
    assert admin.main(["jobs", "cancel", "--all", "--wait", "0.2"]) == 0
    assert jobs.open_jobs() == []
    assert jobs.get(server.owner, queued["id"])["state"] == "cancelled"
    assert jobs.get(server.owner, running["id"])["state"] == "cancelled"
    assert "Abandoned 1" in capsys.readouterr().out
