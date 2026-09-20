/**
 * Hearing a story: what a press does at each state of the part, and what leaving does.
 *
 * The element is played the way a browser plays it rather than the way `testSetup` fakes it — there,
 * a clip "plays" by ending on the next tick, which would finish every part before a test could look
 * at it. Here `play` and `pause` move a flag, `currentTime` is written by the player and read back
 * from what the test says the recording has reached, and `tick()` is one turn of the clock. The
 * pattern is `loops.test.ts`'s, for the same reason.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StoryPart } from "./domain";
import { MemoryMediaStore } from "./mediaStore";
import { testGraph } from "./testGraph";

let reported = 0;
let asked: number | null = null;
let paused = true;
let made: HTMLAudioElement | null = null;
let frames: FrameRequestCallback[] = [];
let plays = 0;

function tick(): void {
  const due = frames;
  frames = [];
  due.forEach((run) => run(performance.now()));
}

type Player = typeof import("./storyAudio");
type Speech = typeof import("./pronunciation");
let player: Player;
let speech: Speech;
let api: typeof import("./api");

const [recorded, unrecorded] = testGraph().storyParts;

async function playing(): Promise<void> {
  await vi.waitFor(() => expect(player.storyPlayback().status).toBe("playing"));
}

beforeEach(async () => {
  reported = 0; asked = null; paused = true; made = null; frames = []; plays = 0;

  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true, get: () => reported, set: (value: number) => { asked = value; reported = value; }
  });
  Object.defineProperty(HTMLMediaElement.prototype, "paused", { configurable: true, get: () => paused });
  const originalPlay = HTMLMediaElement.prototype.play;
  const originalPause = HTMLMediaElement.prototype.pause;
  HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
    plays += 1;
    paused = false;
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause(this: HTMLMediaElement) {
    if (paused) return;
    paused = true;
    this.dispatchEvent(new Event("pause"));
  };
  afterEachRestore = () => {
    HTMLMediaElement.prototype.play = originalPlay;
    HTMLMediaElement.prototype.pause = originalPause;
  };

  const Element = globalThis.Audio;
  vi.stubGlobal("Audio", class extends Element {
    constructor() { super(); made = this as unknown as HTMLAudioElement; }
  });
  vi.stubGlobal("requestAnimationFrame", (run: FrameRequestCallback) => { frames.push(run); return frames.length; });
  vi.stubGlobal("cancelAnimationFrame", () => { frames = []; });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, blob: async () => new Blob(["ogg"], { type: "audio/ogg" })
  }));

  // A fresh module graph, so the element and the registry of players are this test's own.
  vi.resetModules();
  player = await import("./storyAudio");
  speech = await import("./pronunciation");
  api = await import("./api");
  speech.replaceStoreForTests(new MemoryMediaStore());
  player.replaceForTests();
  vi.spyOn(api.backendSession, "mediaFileUrl").mockImplementation((reference) => `https://acervo.example.com/media/${reference}`);
  vi.spyOn(api.backendSession, "mediaHeaders").mockReturnValue({ Authorization: "Bearer token" });
  const sync = await import("./sync");
  vi.spyOn(sync.syncEngine, "syncNow").mockResolvedValue(sync.syncEngine.getStatus());
});

let afterEachRestore: () => void = () => undefined;
afterEach(() => {
  player.stop();
  afterEachRestore();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(HTMLMediaElement.prototype, "currentTime");
  Reflect.deleteProperty(HTMLMediaElement.prototype, "paused");
});

describe("pressing the button on a part", () => {
  it("plays a recorded part from the start, fetching the recording once", async () => {
    player.toggle(recorded);
    await playing();

    expect(player.storyPlayback().partId).toBe(recorded.id);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]))
      .toBe(`https://acervo.example.com/media/${recorded.audioRef}`);
    expect(asked).toBe(0);
  });

  it("pauses when it is playing and carries on from where it was when pressed again", async () => {
    player.toggle(recorded);
    await playing();
    reported = 1.4;

    player.toggle(recorded);
    expect(player.storyPlayback().status).toBe("paused");
    expect(paused).toBe(true);

    player.toggle(recorded);
    expect(player.storyPlayback().status).toBe("playing");
    expect(reported).toBe(1.4);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("stops and forgets the position when its page stops being the one on screen", async () => {
    player.toggle(recorded);
    await playing();

    player.stopPart("some-other-part");
    expect(player.storyPlayback().status).toBe("playing");

    player.stopPart(recorded.id);
    expect(player.storyPlayback()).toMatchObject({ partId: null, status: "idle", segment: null });
    expect(paused).toBe(true);

    // Coming back to it starts from the top, which is what swiping away and back is for.
    reported = 2;
    player.toggle(recorded);
    await playing();
    expect(asked).toBe(0);
  });

  it("is not ended by the silence that was started to keep the gesture", async () => {
    let arrive: (row: StoryPart) => void = () => undefined;
    vi.spyOn(api.backendSession, "recordStoryPart").mockReturnValue(new Promise((resolve) => { arrive = resolve; }));

    player.toggle(unrecorded);
    expect(player.storyPlayback().status).toBe("busy");
    made!.dispatchEvent(new Event("ended"));   // the silence finishing, long before the part exists
    expect(player.storyPlayback()).toMatchObject({ status: "busy", partId: unrecorded.id });

    arrive({ ...unrecorded, audioRef: "stories/storypicada0001/storypart000002-aaaa1111.ogg" });
    await playing();
  });

  it("pressing it while the part is still being recorded cancels that", async () => {
    vi.spyOn(api.backendSession, "recordStoryPart").mockReturnValue(new Promise(() => undefined));

    player.toggle(unrecorded);
    player.toggle(unrecorded);

    expect(player.storyPlayback()).toMatchObject({ status: "idle", partId: null });
  });
});

describe("a part that has not been recorded", () => {
  it("is recorded by the server when it is pressed, and plays the row that comes back", async () => {
    const row: StoryPart = { ...unrecorded, audioRef: "stories/storypicada0001/storypart000002-aaaa1111.ogg", audioMime: "audio/ogg" };
    const record = vi.spyOn(api.backendSession, "recordStoryPart").mockResolvedValue(row);

    player.toggle(unrecorded);
    await playing();

    expect(record).toHaveBeenCalledWith(unrecorded.storyId, unrecorded.id, expect.any(String));
    expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]))
      .toBe(`https://acervo.example.com/media/${row.audioRef}`);
  });

  it("says why when the server could not, and leaves the button pressable", async () => {
    vi.spyOn(api.backendSession, "recordStoryPart")
      .mockRejectedValue(new api.AcervoApiError("The speech model is temporarily rate limited.", 503, "llm_rate_limited"));

    player.toggle(unrecorded);
    await vi.waitFor(() => expect(player.storyPlayback().failed).not.toBeNull());

    expect(player.storyPlayback()).toMatchObject({
      partId: unrecorded.id, status: "idle", failed: "The speech model is temporarily rate limited."
    });
    expect(made!.getAttribute("src")).toBeNull();
  });

  it("says the server is needed when it cannot be reached", async () => {
    vi.spyOn(api.backendSession, "recordStoryPart")
      .mockRejectedValue(new api.AcervoApiError("offline", 0, "offline"));

    player.toggle(unrecorded);
    await vi.waitFor(() => expect(player.storyPlayback().failed).toMatch(/needs the server/));
  });
});

describe("the passages of a part", () => {
  it("marks the passage that is sounding, following the recording", async () => {
    player.toggle(recorded);
    await playing();
    expect(player.storyPlayback().segment).toBe(0);

    reported = 1.75;   // the second has started
    tick();
    expect(player.storyPlayback().segment).toBe(1);

    reported = 1.65;   // in the rest between the two, the first is still the one that was said
    tick();
    expect(player.storyPlayback().segment).toBe(0);
  });

  it("plays only the passage that was touched when nothing of the part is playing", async () => {
    player.playSegment(recorded, 1);
    await playing();

    expect(asked).toBe(1.72);
    expect(player.storyPlayback().segment).toBe(1);

    reported = 2.95;   // past where it ends
    tick();

    expect(player.storyPlayback()).toMatchObject({ status: "idle", partId: null });
    expect(paused).toBe(true);
  });

  it("moves the recording there, and carries on to the end, when the part is already playing", async () => {
    player.toggle(recorded);
    await playing();

    player.playSegment(recorded, 1);
    expect(asked).toBe(1.72);
    expect(player.storyPlayback()).toMatchObject({ status: "playing", segment: 1 });

    reported = 2.95;   // past the second's end, which would have stopped a passage played alone
    tick();
    expect(player.storyPlayback().status).toBe("playing");
  });

  it("ignores a passage the part does not have", async () => {
    player.playSegment(recorded, 7);
    expect(player.storyPlayback().status).toBe("idle");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("ends when the recording does", async () => {
    player.toggle(recorded);
    await playing();

    made!.dispatchEvent(new Event("ended"));

    expect(player.storyPlayback()).toMatchObject({ status: "idle", partId: null });
  });
});

describe("one sound at a time", () => {
  it("stops a word being read, and pauses every other player, before it plays", async () => {
    const stopSpeech = vi.spyOn(speech, "stop");
    const other = vi.fn();
    speech.registerPlayer(other);

    player.toggle(recorded);
    await playing();

    expect(stopSpeech).toHaveBeenCalled();
    expect(other).toHaveBeenCalled();
  });

  it("is paused by whatever else starts to play", async () => {
    player.toggle(recorded);
    await playing();

    speech.silencePlayers();   // what a word being read, or a loop, does before it makes a sound

    expect(player.storyPlayback().status).toBe("paused");
    expect(paused).toBe(true);
  });

  it("is not paused by itself", async () => {
    player.toggle(recorded);
    await playing();

    speech.silencePlayers(player.pause);

    expect(player.storyPlayback().status).toBe("playing");
  });
});

describe("resuming", () => {
  it("presses that only pause and resume do not fetch again", async () => {
    player.toggle(recorded);
    await playing();
    player.toggle(recorded);
    player.toggle(recorded);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(plays).toBeGreaterThanOrEqual(2);
  });
});
