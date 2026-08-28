import { backendSession } from "./api";
import { validateGraph, type VocabularyGraph } from "./domain";
import { repository } from "./repository";

/**
 * Pulls the signed-in owner's complete graph and applies it to the local replica.
 *
 * This is a one-way display pull: the replica is the only thing the interface reads, and pending
 * local writes survive it. Push, merge and conflict resolution are a separate concern (§04) and
 * are not implemented here. Every caller must tolerate a rejection — the whole application keeps
 * working from the replica when the server cannot be reached.
 */
export async function pullGraph(): Promise<string> {
  const { syncedAt, ...response } = await backendSession.fetchGraph();
  const graph: VocabularyGraph = {
    topics: response.topics,
    lexemes: response.lexemes,
    senses: response.senses,
    attestations: response.attestations,
    examples: response.examples,
    imagePrompts: response.imagePrompts,
    studyStates: response.studyStates
  };
  validateGraph(graph);
  await repository.applyRemote(graph);
  return syncedAt;
}
