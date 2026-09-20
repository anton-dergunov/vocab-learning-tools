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

/** One passage of a part the server has just recorded. */
const fresh = (digest: string) => ({
  text: unrecorded.text, direction: "", audioMime: "audio/ogg", durationSeconds: 2,
  audioRef: `stories/storypicada0001/storypart000002-00-${digest}.ogg`
});

async function playing(): Promise<void> {
  await vi.waitFor(() => expect(player.storyPlayback().status).toBe("playing"));
}

beforeEach(async () => {
  reported = 0; asked = null; paused = true; made = null; frames = []; plays = 0;

  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true, get: () => reported, set: (value: number) => { asked = value; reported = value; }
  });
  Object.defineProperty(HTMLMediaElement.prototype, "paused", { configurable: true, get: () => paused });
  // jsdom has no media pipeline, so an element never reaches HAVE_METADATA on its own and never
  // fires `loadedmetadata`. The player waits for that before moving to a passage, so the fake says
  // what a browser says once a blob is in hand.
  Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => 1 });
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
  Reflect.deleteProperty(HTMLMediaElement.prototype, "readyState");
});

describe("pressing the button on a part", () => {
  it("plays a recorded part from the start, fetching the recording once", async () => {
    player.toggle(recorded);
    await playing();

    expect(player.storyPlayback().partId).toBe(recorded.id);
    // Every passage is fetched before the first sounds, so the swap between them is an assignment.
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]))
      .toBe(`https://acervo.example.com/media/${recorded.audioSegments[0].audioRef}`);
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
    player.toggle(recorded);
    await playing();
    expect(player.storyPlayback().segment).toBe(0);
  });

  it("is not ended by the silence that was started to keep the gesture", async () => {
    let arrive: (row: StoryPart) => void = () => undefined;
    vi.spyOn(api.backendSession, "recordStoryPart").mockReturnValue(new Promise((resolve) => { arrive = resolve; }));

    player.toggle(unrecorded);
    expect(player.storyPlayback().status).toBe("busy");
    made!.dispatchEvent(new Event("ended"));   // the silence finishing, long before the part exists
    expect(player.storyPlayback()).toMatchObject({ status: "busy", partId: unrecorded.id });

    arrive({ ...unrecorded, audioSegments: [fresh("aaaa1111")] });
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
    const row: StoryPart = { ...unrecorded, audioSegments: [fresh("aaaa1111")] };
    const record = vi.spyOn(api.backendSession, "recordStoryPart").mockResolvedValue(row);

    player.toggle(unrecorded);
    await playing();

    expect(record).toHaveBeenCalledWith(unrecorded.storyId, unrecorded.id, expect.any(String));
    expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]))
      .toBe(`https://acervo.example.com/media/${row.audioSegments[0].audioRef}`);
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
  /** A part of three passages, so "carry on to the end" has somewhere to carry on to. */
  const three: StoryPart = {
    ...recorded,
    audioSegments: [0, 1, 2].map((index) => ({
      text: `Passage ${index}. `, direction: "", audioMime: "audio/ogg", durationSeconds: 1,
      audioRef: `stories/storypicada0001/storypart000001-0${index}-aaaa000${index}.ogg`
    }))
  };
  /** The passage that just ended, so the next one starts — what a browser does at the end of a file. */
  const ended = () => made!.dispatchEvent(new Event("ended"));

  it("marks the passage that is sounding, and moves the mark when that file ends", async () => {
    player.toggle(recorded);
    await playing();
    expect(player.storyPlayback().segment).toBe(0);

    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
  });

  it("plays only the passage that was touched when nothing of the part is playing", async () => {
    player.playSegment(three, 1);
    await playing();

    expect(player.storyPlayback().segment).toBe(1);
    // Only that passage was even fetched: the point of a file each is that nothing else is needed.
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]))
      .toContain("storypart000001-01-");

    ended();

    expect(player.storyPlayback()).toMatchObject({ status: "idle", partId: null });
  });

  it("carries on to the end of the part when a passage is touched while it is playing", async () => {
    player.toggle(three);
    await playing();
    (fetch as unknown as { mockClear(): void }).mockClear();

    player.playSegment(three, 1);
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));

    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(2));
    ended();
    expect(player.storyPlayback()).toMatchObject({ status: "idle", partId: null });
  });

  it("ignores a passage the part does not have", () => {
    player.playSegment(recorded, 7);
    expect(player.storyPlayback().status).toBe("idle");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("ends when the last passage does", async () => {
    player.toggle(recorded);
    await playing();

    ended();                                   // the first passage; the second follows
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
    ended();                                   // the last

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
    (fetch as unknown as { mockClear(): void }).mockClear();

    player.toggle(recorded);
    player.toggle(recorded);

    expect(fetch).not.toHaveBeenCalled();
    expect(plays).toBeGreaterThanOrEqual(2);
  });
});
