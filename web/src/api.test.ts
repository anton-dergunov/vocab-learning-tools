import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession } from "./api";
import { sessionStore } from "./session";

const jsonResponse = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" }
});

describe("authenticated API sessions", () => {
  afterEach(async () => {
    await backendSession.logout();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("persists login and refreshed tokens without persisting the password", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(200, { data: {
        token: "first-token", user: { id: "owner0000000001", email: "learner@account.example.com" }
      } }))
      .mockResolvedValueOnce(jsonResponse(200, { data: {
        token: "refreshed-token", user: { id: "owner0000000001", email: "learner@account.example.com" }
      } }));
    vi.stubGlobal("fetch", fetch);

    await backendSession.login("https://acervo.example.com", "learner@account.example.com", "secret-password");
    expect((await backendSession.refresh())?.token).toBe("refreshed-token");
    expect(await sessionStore.load()).toMatchObject({ token: "refreshed-token", userId: "owner0000000001" });
    expect(localStorage.getItem("acervo.backend.session.v1")).not.toContain("secret-password");
  });

  it("clears an expired session after refresh is rejected", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(jsonResponse(200, { data: {
        token: "first-token", user: { id: "owner0000000001", email: "learner@account.example.com" }
      } }))
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "unauthenticated", message: "Sign in to continue." } })));

    await backendSession.login("https://acervo.example.com", "learner@account.example.com", "secret-password");
    expect(await backendSession.refresh()).toBeNull();
    expect(await sessionStore.load()).toBeNull();
    expect(backendSession.current()).toBeNull();
  });
});
