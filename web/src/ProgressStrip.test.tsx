import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Job, JobStep } from "./api";
import ProgressStrip, { stripOf } from "./ProgressStrip";

function job(state: Job["state"], steps: JobStep[], overrides: Partial<Job> = {}): Job {
  return {
    id: "job000000000001", ownerId: "owner0000000001", parentId: null, kind: "enrich",
    subject: { kind: "lexeme", id: "lexemepicar0001" }, input: {}, state, trigger: "save", steps,
    rerun: false, cancelRequested: false, dismissed: false, error: null, message: null,
    notBefore: null, createdAt: "2026-09-17T10:00:00.000Z", startedAt: null, finishedAt: null,
    ...overrides
  };
}

describe("what the strip says", () => {
  it("names every phase still ahead, and marks the one being worked on", () => {
    expect(stripOf(job("running", [
      { name: "clips", state: "running" },
      { name: "pictures", state: "pending" },
      { name: "pronunciations", state: "pending" }
    ]))).toEqual({
      phases: [
        { text: "Finding recorded examples", current: true },
        { text: "Drawing pictures", current: false },
        { text: "Recording audio", current: false }
      ],
      failure: null
    });
  });

  it("counts the pictures, and leaves out what is finished or skipped", () => {
    expect(stripOf(job("running", [
      { name: "clips", state: "skipped" },
      { name: "pictures", state: "running", done: 1, total: 3 },
      { name: "pronunciations", state: "skipped" }
    ]))?.phases).toEqual([{ text: "Drawing 2 of 3", current: true }]);
  });

  it("says when a step is waiting out a busy provider", () => {
    expect(stripOf(job("queued", [
      { name: "clips", state: "done" },
      { name: "pictures", state: "waiting", done: 0, total: 2, rests: 1 }
    ]))?.phases[0].text).toBe("Drawing 1 of 2 (the provider is busy)");
  });

  it("names what a step is waiting for when the server says", () => {
    expect(stripOf(job("queued", [
      { name: "pictures", state: "waiting", done: 0, total: 2, rests: 1,
        waitingOn: "Vertex AI is out of allowance for now" }
    ]))?.phases[0].text).toBe("Drawing 1 of 2 — Vertex AI is out of allowance for now");
  });

  it("names the steps of the other kinds too", () => {
    expect(stripOf(job("running", [{ name: "draw", state: "running" }], { kind: "image.redraw" }))?.phases)
      .toEqual([{ text: "Drawing", current: true }]);
    expect(stripOf(job("running", [
      { name: "capture", state: "running", detail: { words: [{}, {}] } }
    ], { kind: "capture" }))?.phases[0].text).toBe("Reading the text · 2 so far");
  });

  it("says a job has not started yet", () => {
    expect(stripOf(job("queued", []))?.phases).toEqual([{ text: "Waiting to start", current: false }]);
  });

  it("collapses when the job is done or cancelled", () => {
    expect(stripOf(job("done", [{ name: "clips", state: "done" }]))).toBeNull();
    expect(stripOf(job("cancelled", []))).toBeNull();
    expect(stripOf(undefined)).toBeNull();
  });

  it("leaves one line for a failure, saying what was drawn", () => {
    expect(stripOf(job("failed", [
      { name: "clips", state: "done" },
      { name: "pictures", state: "failed", done: 3, total: 3, detail: { refused: 1 }, error: "image_refused" }
    ]))?.failure).toBe("2 of 3 pictures drawn");
    expect(stripOf(job("failed", [{ name: "clips", state: "failed", error: "corpus_unavailable" }]))?.failure)
      .toBe("Couldn't search recorded speech");
    expect(stripOf(job("failed", [], { error: "interrupted" }))?.failure)
      .toBe("Interrupted when the server restarted");
  });
});

describe("the strip", () => {
  it("offers Try again and dismissal on a failure", () => {
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(<ProgressStrip
      job={job("failed", [{ name: "pronunciations", state: "failed" }])}
      onRetry={onRetry} onDismiss={onDismiss}
    />);
    expect(screen.getByText("Some audio could not be recorded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when there is nothing to say", () => {
    const { container } = render(<ProgressStrip job={undefined} onRetry={vi.fn()} onDismiss={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("a loop being made", () => {
  const rendering = (detail: Record<string, unknown>) => stripOf(job("running", [
    { name: "loop.render", state: "running", detail },
    { name: "loop.store", state: "pending" }
  ], { kind: "loop" }));

  it("says what the generator says it is doing, in its own words", () => {
    // "Synthesizing speech", "Rendering the music bed", "Mixing" — the phrases come from the render
    // itself, because it is the only thing that knows and a sentence invented here would drift.
    expect(rendering({ doing: "Rendering the music bed", progress: 0.78 })?.phases[0].text)
      .toBe("Rendering the music bed · 78%");
  });

  it("still says something useful before the first progress arrives", () => {
    expect(rendering({ words: 12 })?.phases[0].text).toBe("Making the loop from 12 words");
  });

  it("keeps the reason a render failed rather than replacing it with a constant", () => {
    // The generator records it, it survives into the step, and this is the last place it could be
    // thrown away — which is exactly where it was being thrown away.
    const line = stripOf(job("failed", [
      { name: "loop.render", state: "failed", error: "loops_failed",
        message: "No samples cached for 'salamander'." }
    ], { kind: "loop" }));
    expect(line?.failure).toContain("No samples cached for 'salamander'.");
  });
});

describe("a story being made", () => {
  const story = (steps: JobStep[], overrides: Partial<Job> = {}) => stripOf(job("running", steps, {
    kind: "story", subject: { kind: "story", id: "storypicada0001" }, ...overrides
  }));
  const steps = (
    states: JobStep["state"][], draw: Partial<JobStep> = {}, audio: Partial<JobStep> = {}
  ): JobStep[] => [
    { name: "story.write", state: states[0] },
    { name: "story.translate", state: states[1] },
    { name: "story.brief", state: states[2] },
    { name: "story.draw", state: states[3], ...draw },
    { name: "story.audio", state: states[4] ?? "pending", ...audio }
  ];

  it("is one line, with the overall percentage before the step it is on", () => {
    const line = story(steps(["running", "pending", "pending", "pending"]));
    expect(line?.phases).toEqual([{ text: "0% · Writing the story", current: true }]);
  });

  /* The three text steps take about fifteen seconds between them and the two long ones take minutes.
     Naming each text step flashed three phrases past unreadably, and weighting them evenly put half
     the bar on the fastest fifth of the work. */
  it("calls all three text steps one thing, and gives them a tenth of the bar between them", () => {
    expect(story(steps(["done", "running", "pending", "pending"]))?.phases[0].text)
      .toBe("5% · Writing the story");
    expect(story(steps(["done", "done", "running", "pending"]))?.phases[0].text)
      .toBe("8% · Writing the story");
    expect(story(steps(["done", "done", "done", "running"]))?.phases[0].text)
      .toBe("10% · Drawing the pictures");
  });

  it("gives the pictures and the recording the rest of the bar, where the time actually goes", () => {
    // 10 for the text + 35 * 2/4 for the drawing.
    expect(story(steps(["done", "done", "done", "running"], { done: 2, total: 4 }))?.phases[0].text)
      .toBe("27% · Drawing picture 3 of 4");
    // 45 for everything up to the recording + 55 * 1/3 of it.
    expect(story(steps(["done", "done", "done", "done", "running"], {}, { done: 1, total: 3 }))?.phases[0].text)
      .toBe("63% · Recording part 2 of 3");
  });

  it("counts a recording that was switched off as finished, so it does not hold the figure back", () => {
    expect(story(steps(["done", "done", "done", "running", "skipped"], { done: 0, total: 4 }))?.phases[0].text)
      .toBe("65% · Drawing picture 1 of 4");
  });

  it("never says 100% while it is still working", () => {
    expect(story(steps(["done", "done", "done", "done", "running"], {}, { done: 3, total: 3 }))?.phases[0].text)
      .toMatch(/^99% · /);
  });

  it("says when the provider is busy without losing the number", () => {
    expect(story(steps(["done", "done", "done", "done", "waiting"], {}, { done: 1, total: 4 }))?.phases[0].text)
      .toBe("58% · Recording part 2 of 4 (the provider is busy)");
  });

  /* "Waiting to start" means waiting to start. It used to be whatever came out when no step was
     *running*, which covered a ten-minute rest and the whole of the job closing. */
  it("says it is waiting to start only before anything has run", () => {
    expect(story(steps(["pending", "pending", "pending", "pending"]))?.phases[0].text)
      .toBe("0% · Waiting to start");
  });

  it("names the step that is resting rather than claiming it has not begun", () => {
    const due = new Date(Date.now() + 60_000);
    const line = story(steps(["done", "done", "done", "done", "pending"], {}, { done: 2, total: 4 }),
                       { notBefore: due.toISOString() });
    const at = due.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    expect(line?.phases[0].text).toBe(`72% · Recording part 3 of 4 (the provider is busy · next try ${at})`);
  });

  /* The row of twelve stories that said "the provider is busy" for an hour, while Gemini's free tier
     was overloaded and Cloudflare's daily allowance had gone: the server names both now, and this
     says them, with when it will ask again. */
  it("says which providers it is waiting for and when it will ask again", () => {
    const due = new Date(Date.now() + 600_000);
    const writing: JobStep[] = steps(["waiting", "pending", "pending", "pending", "pending"]);
    writing[0] = { ...writing[0], rests: 3,
      waitingOn: "Gemini (free tier) is overloaded; Cloudflare Workers AI is out of allowance for now" };
    const at = due.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    expect(story(writing, { notBefore: due.toISOString() })?.phases[0].text).toBe(
      "0% · Writing the story — Gemini (free tier) is overloaded; Cloudflare Workers AI is out of "
      + `allowance for now · next try ${at}`);
  });

  it("says it is finishing once every step is done and the job is still closing", () => {
    const line = story(steps(["done", "done", "done", "done", "done"]));
    expect(line?.phases[0].text).toBe("99% · Finishing");
  });

  it("keeps the reason a step failed, and still names the step it failed in", () => {
    expect(stripOf(job("failed", [
      { name: "story.write", state: "failed", message: "that word is a slur" }
    ], { kind: "story" }))?.failure).toBe("The story could not be written — that word is a slur");
    expect(stripOf(job("failed", [
      { name: "story.translate", state: "failed", message: "it would not hold its shape" }
    ], { kind: "story" }))?.failure).toBe("The story could not be translated — it would not hold its shape");
  });

  it("keeps the reason a recording failed, and says it was the recording", () => {
    const line = stripOf(job("failed", [
      { name: "story.audio", state: "failed", message: "The speech model credential was rejected." }
    ], { kind: "story" }));
    expect(line?.failure).toBe("Some parts could not be recorded — The speech model credential was rejected.");
  });
});
