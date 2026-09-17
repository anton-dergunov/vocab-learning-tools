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
