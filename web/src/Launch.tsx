/**
 * What Acervo shows while it opens: the wordmark, and nothing that could be read as a fact.
 *
 * A cold start on a tablet — iOS having evicted the app — reads the whole replica back from
 * IndexedDB before there is anything to show, which takes about a second. The interface used to be
 * drawn during that second with no data in it, so it said "All 0 · Loops 0 · Stories 0": a claim
 * about your vocabulary, and a false one. This says only that Acervo is opening. The note fades in
 * late, so an open that is quick never flashes a word of it.
 *
 * `index.html` carries the same markup, so the frame before any script runs is this one too.
 */
export function Launch() {
  return <div className="launch" role="status">
    <p className="launch-mark">Acervo</p>
    <p className="launch-note">Opening your vocabulary…</p>
  </div>;
}
