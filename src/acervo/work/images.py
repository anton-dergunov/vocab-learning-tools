"""`image.redraw` and `image.rebrief`: the picture actions a person asks for (§4.1, §5).

A redraw is a job even though somebody pressed the button, because the point of pressing it was to
go on reading while the picture is made — and a request that dies when the article closes is not
that. Each calls the service function the routes call, once; the runner decides whether to ask
again.
"""

from __future__ import annotations

from acervo.errors import ApiError
from acervo.services import images
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Step

DEVICE = "acervoimages"


def draw(context: JobContext, step: Step) -> None:
    step.gate()
    # Edit-and-draw carries the edited brief and style; a plain redraw carries neither and draws
    # the stored brief again with a fresh seed.
    overrides = {key: context.input[key] for key in ("prompt", "styleId") if context.input.get(key)}
    drawn = images.render_prompt(context.settings, context.owner, DEVICE, context.subject_id, overrides)
    if not drawn.get("imageRef"):
        # Recorded on the picture's own row as `failureReason`; the job says it too.
        raise ApiError(502, "image_refused", drawn.get("failureReason") or "The provider declined to draw this.")


def rebrief(context: JobContext, step: Step) -> None:
    step.gate()
    # Asked from one sense's picture dialog, that sense is briefed even if it was ruled out.
    images.brief_lexeme(context.settings, context.owner, DEVICE, context.subject_id,
                        revive=context.input.get("senseId") or None)


register(Kind("image.redraw", ("draw",),
              lambda context: context.step("draw", lambda step: draw(context, step), lane="image")))
register(Kind("image.rebrief", ("brief",),
              lambda context: context.step("brief", lambda step: rebrief(context, step), lane="image")))
