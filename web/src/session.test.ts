import { afterEach, describe, expect, it } from "vitest";
import { normalizeServerURL, sessionStore } from "./session";

describe("Acervo sessions", () => {
  afterEach(() => localStorage.clear());

  it("normalizes secure server addresses", () => {
    expect(normalizeServerURL(" https://acervo.example.com/api/acervo/v1/ ")).toBe("https://acervo.example.com");
    expect(normalizeServerURL("http://localhost:27702/")).toBe("http://localhost:27702");
    expect(() => normalizeServerURL("http://acervo.example.com")).toThrow("HTTPS");
  });

  it("persists no password and restores the account identity", async () => {
    const session = { baseUrl: "https://acervo.example.com", email: "learner@account.example.com", token: "token", userId: "owner0000000001" };
    await sessionStore.save(session);
    expect(await sessionStore.load()).toEqual(session);
    expect(JSON.stringify(localStorage)).not.toContain("password");
  });
});
