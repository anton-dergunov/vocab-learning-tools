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
  const steps = (states: JobStep["state"][], draw: Partial<JobStep> = {}): JobStep[] => [
    { name: "story.write", state: states[0] },
    { name: "story.translate", state: states[1] },
    { name: "story.brief", state: states[2] },
    { name: "story.draw", state: states[3], ...draw }
  ];

  it("is one line, with the overall percentage before the step it is on", () => {
    const line = story(steps(["running", "pending", "pending", "pending"]));
    expect(line?.phases).toEqual([{ text: "0% · Writing the story", current: true }]);
  });

  it("counts a finished step as its share of the whole", () => {
    // Write 30 + translate 15 of 100.
    expect(story(steps(["done", "done", "running", "pending"]))?.phases[0].text)
      .toBe("45% · Planning the pictures");
  });

  it("says which picture it is on, and counts the pictures already drawn towards the total", () => {
    // 55 for the first three steps + 45 * 2/4 for the drawing = 77.5, shown rounded down.
    expect(story(steps(["done", "done", "done", "running"], { done: 2, total: 4 }))?.phases[0].text)
      .toBe("77% · Drawing picture 3 of 4");
  });

  it("never says 100% while it is still working", () => {
    expect(story(steps(["done", "done", "done", "running"], { done: 4, total: 4 }))?.phases[0].text)
      .toMatch(/^99% · /);
  });

  it("says when the provider is busy without losing the number", () => {
    expect(story(steps(["done", "waiting", "pending", "pending"]))?.phases[0].text)
      .toBe("30% · Translating it (the provider is busy)");
  });

  it("says it is waiting to start before anything has begun", () => {
    expect(story(steps(["pending", "pending", "pending", "pending"]))?.phases[0].text)
      .toBe("0% · Waiting to start");
  });

  it("keeps the reason a step failed", () => {
    const line = stripOf(job("failed", [
      { name: "story.write", state: "failed", message: "that word is a slur" }
    ], { kind: "story" }));
    expect(line?.failure).toBe("The story could not be written — that word is a slur");
  });
});
