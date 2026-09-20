"""`story`: write a story, translate it, brief its pictures, draw them, read it aloud.

Five steps because five things can fail separately and four of them are worth keeping when the
fifth does not. A story that was written and translated but whose pictures failed is still a story
you can read; one that is only half written is not.

**Each of the first three skips itself when its work is already in the graph**, which is what makes
Try again safe. It queues a new job with every step pending, and a story whose recording failed would
otherwise be written a second time, beside the first, before the recording was reached.

**Nothing is held in memory between steps**, for `work/loop.py`'s reason: each step reads what it
needs back out of the graph, so a step that fails and is retried re-enters the handler from the top
with everything it needs. Here that is more than a rule of hygiene — it is what makes `story.draw`
idempotent, because "which parts still have no picture" is a question about the graph rather than
about this run.

The first three hold the `text` lane, drawing holds `image` and reading aloud holds `audio`, which
is the allowance each actually spends. Reading aloud is switched by Settings ▸ Stories, read when the
step starts, and a story recorded on demand instead simply skips it.
"""

from __future__ import annotations

from acervo.repository import pronunciation_settings
from acervo.services import stories, story_audio
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Step

# What the graph records as having written a story. The same device the enrichment job uses: both
# are this server doing its own work.
DEVICE = "acervorunner"


def _write(context: JobContext, step: Step, story_id: str) -> str | None:
    if stories.is_written(context.owner, story_id):
        return "skipped"
    step.gate()
    usage = stories.write_story(context.settings, context.owner, DEVICE, story_id)
    step.note(parts=usage["parts"], model=usage.get("model"), seconds=usage.get("seconds"))
    if usage["unused"]:
        # Not a failure — the story exists and is worth reading — but it is the thing most worth
        # knowing about a story, and the row is where somebody will look for it.
        step.note(unused=len(usage["unused"]))
    return None


def _translate(context: JobContext, step: Step, story_id: str) -> str | None:
    if stories.is_translated(context.owner, story_id):
        return "skipped"
    step.gate()
    usage = stories.translate_story(context.settings, context.owner, DEVICE, story_id)
    step.note(parts=usage["parts"], into=usage["into"], seconds=usage.get("seconds"))
    return None


def _brief(context: JobContext, step: Step, story_id: str) -> str | None:
    if stories.is_briefed(context.owner, story_id):
        return "skipped"
    step.gate()
    usage = stories.brief_story(context.settings, context.owner, DEVICE, story_id)
    step.note(parts=usage["parts"], seconds=usage.get("seconds"))
    return None


def _draw(context: JobContext, step: Step, story_id: str) -> str | None:
    # `gate` is handed down rather than called once here, so a story of six pictures can be
    # cancelled between them instead of only before the first. `progress` goes the same way, and is
    # what lets the row say "picture 2 of 4" while the step is still inside its loop.
    drawn = stories.draw_pictures(
        context.settings, context.owner, DEVICE, story_id,
        gate=step.gate, progress=step.progress,
    )
    step.note(drawn=drawn["drawn"], failed=len(drawn["failed"]))
    # A picture that could not be drawn is recorded on its own part and does not fail the job: the
    # story is readable without it, and Try again redraws exactly the ones still missing.
    return "partial" if drawn["failed"] else None


def _speak(context: JobContext, step: Step, story_id: str) -> str | None:
    if not pronunciation_settings.settings(context.owner).pregenerate[pronunciation_settings.STORIES]:
        return "skipped"
    # `gate` and `progress` go down for `_draw`'s reason: a story is several calls to a voice per
    # part, and the row should say "part 2 of 4" and be cancellable between them.
    done = story_audio.narrate_story(
        context.settings, context.owner, DEVICE, story_id,
        gate=step.gate, progress=step.progress,
    )
    step.note(recorded=done["recorded"])
    return None


def tell(context: JobContext) -> None:
    story_id = context.subject_id
    context.step("story.write", lambda step: _write(context, step, story_id), lane="text")
    context.step("story.translate", lambda step: _translate(context, step, story_id), lane="text")
    context.step("story.brief", lambda step: _brief(context, step, story_id), lane="text")
    context.step("story.draw", lambda step: _draw(context, step, story_id), lane="image")
    context.step("story.audio", lambda step: _speak(context, step, story_id), lane="audio")


register(Kind(
    "story", ("story.write", "story.translate", "story.brief", "story.draw", "story.audio"), tell,
))
