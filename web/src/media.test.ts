import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The reference counting, because it is the subtle part and the failure is visible: revoke a URL a
 * second component is still showing and its picture goes blank.
 */

const created: string[] = [];
const revoked: string[] = [];

describe("holding a picture", () => {
  let media: typeof import("./media");

  beforeEach(async () => {
    created.length = 0;
    revoked.length = 0;
    let serial = 0;
    // Spied rather than replaced: `new URL(...)` is used by fetch's own internals, so stubbing the
    // whole global takes the constructor with it.
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => {
      const url = `blob:picture-${++serial}`;
      created.push(url);
      return url;
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation((url) => { revoked.push(url); });
    vi.stubGlobal("indexedDB", undefined);
    vi.resetModules();
    vi.doMock("./api", () => ({
      backendSession: {
        mediaFileUrl: (reference: string) => `https://acervo.example.com/media/${reference}`,
        mediaHeaders: () => ({})
      }
    }));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new Blob(["webp"]))));
    media = await import("./media");
  });

  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.doUnmock("./api"); });

  it("fetches once for two holders and revokes only when both let go", async () => {
    const [first, second] = await Promise.all([
      media.acquire("images/a/b.webp"),
      media.acquire("images/a/b.webp")
    ]);
    expect(first).toBe(second);
    expect(created).toHaveLength(1);
    expect(fetch).toHaveBeenCalledTimes(1);

    media.release("images/a/b.webp");
    expect(revoked).toEqual([]);
    media.release("images/a/b.webp");
    expect(revoked).toEqual([first]);
  });

  it("never leaves an entry at zero holders for a concurrent caller to find", async () => {
    // The window this guards: one caller releasing between another's await and its increment would
    // hand back a URL that had just been revoked.
    const pending = media.acquire("images/a/b.webp");
    const url = await pending;
    media.release("images/a/b.webp");
    expect(revoked).toEqual([url]);

    // A later acquire makes a fresh URL rather than reusing the revoked one.
    const again = await media.acquire("images/a/b.webp");
    expect(again).not.toBe(url);
    expect(created).toHaveLength(2);
  });

  it("serves a picture already on the device without asking the server", async () => {
    await media.acquire("images/a/b.webp");
    media.release("images/a/b.webp");
    await media.acquire("images/a/b.webp");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("serves a redrawn picture without being told anything, the name having changed with it", async () => {
    // The whole of why there is no invalidation here: a reference carries a digest of its bytes, so
    // the redrawn picture is asked for under a name the cache has never held.
    await media.acquire("images/a/b-1111.webp");
    await media.acquire("images/a/b-2222.webp");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("says what went wrong rather than showing an empty frame", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    await expect(media.acquire("images/a/gone.webp")).rejects.toThrow("not on the server");
  });
});
