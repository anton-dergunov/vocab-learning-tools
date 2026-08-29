/* Stands in for the write route in repository tests: numbers every record it is handed, exactly
   as the server's save hook does, and hands back what it stored. */

import type { VocabularyGraph } from "./domain";
import type { RemoteGraph, RemoteWrite } from "./repository";

export interface FakeRemote extends RemoteGraph {
  calls: number;
  /** Set to make the next push fail, the way an unreachable or refusing server would. */
  fail: Error | null;
  sent: Partial<VocabularyGraph>[];
}

export function fakeRemote(datasetId = "dataset00000001"): FakeRemote {
  let sequence = 0;
  const remote: FakeRemote = {
    calls: 0,
    fail: null,
    sent: [],
    async push(changes) {
      remote.calls += 1;
      remote.sent.push(structuredClone(changes));
      if (remote.fail) throw remote.fail;
      const records: Partial<VocabularyGraph> = {};
      (Object.keys(changes) as (keyof VocabularyGraph)[]).forEach((kind) => {
        const incoming = changes[kind] as { revision: number }[] | undefined;
        if (!incoming) return;
        records[kind] = incoming.map((record) => ({ ...record, revision: ++sequence })) as never;
      });
      // The cursor is deliberately not advanced by a write: the engine leaves it alone so the
      // next pull re-delivers these rows rather than skipping anything written in between.
      return { records, cursor: 0, datasetId } satisfies RemoteWrite;
    }
  };
  return remote;
}
