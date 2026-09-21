import { afterEach, describe, expect, it } from "vitest";
import { describeStartup, markReplicaRead, markSession, markStartup, resetStartup, startupTimings } from "./startup";

describe("the launch timing", () => {
  afterEach(() => resetStartup());

  it("splits a launch into reading, checking and showing", () => {
    markSession(true);
    markStartup("readStart", 100);
    markReplicaRead(10812);
    markStartup("checked", performance.now() + 60);
    markStartup("shown", performance.now() + 210);
    const timings = startupTimings()!;
    expect(timings.records).toBe(10812);
    expect(timings.check).toBeGreaterThanOrEqual(59);
    expect(timings.show).toBeGreaterThanOrEqual(140);
    expect(describeStartup({ session: 40, read: 820, records: 10812, check: 60, show: 150, total: 1100 }))
      .toBe("Opened in 1.1 s — reading 10,812 records 820 ms · checking 60 ms · first list 150 ms");
  });

  it("keeps the first launch rather than a later load", () => {
    markSession(true);
    markStartup("readStart", 10);
    markStartup("readStart", 500);
    markReplicaRead(5);
    markReplicaRead(9);
    markStartup("checked");
    markStartup("shown");
    expect(startupTimings()?.records).toBe(5);
  });

  it("says nothing about a launch that stopped to ask for a password", () => {
    markSession(false);
    markStartup("readStart");
    markReplicaRead(1);
    markStartup("checked");
    markStartup("shown");
    expect(startupTimings()).toBeNull();
  });
});
