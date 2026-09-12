import "@testing-library/jest-dom/vitest";

/**
 * jsdom's `Blob` predates `Blob.prototype.arrayBuffer` and `Blob.prototype.text`, both of which
 * every browser Acervo targets has had for years and both of which the dictionary code uses to read
 * a stored artifact.
 *
 * This fills the gap in the test environment only. It is not compatibility code for a browser: if
 * production ever needed it, that would be a reason to change the reader rather than to ship this.
 */
function readBlob<T extends ArrayBuffer | string>(blob: Blob, as: "buffer" | "text"): Promise<T> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as T);
    reader.onerror = () => reject(reader.error);
    if (as === "buffer") reader.readAsArrayBuffer(blob); else reader.readAsText(blob);
  });
}

if (typeof Blob !== "undefined" && typeof Blob.prototype.arrayBuffer !== "function") {
  Blob.prototype.arrayBuffer = function arrayBuffer(this: Blob) {
    return readBlob<ArrayBuffer>(this, "buffer");
  };
}

if (typeof Blob !== "undefined" && typeof Blob.prototype.text !== "function") {
  Blob.prototype.text = function text(this: Blob) {
    return readBlob<string>(this, "text");
  };
}

/**
 * jsdom does no layout, so it implements no scrolling at all — `Element.prototype.scrollIntoView`
 * simply is not there.
 *
 * The review bar brings the first change into view on every proposal, so without this every test
 * that reviews one throws. A no-op rather than a spy by default: a test that cares about *where* it
 * scrolled spies on this itself. Same standing as the `Blob` fills above — the test environment is
 * missing something every browser has, and production calls it unguarded.
 */
if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = function scrollIntoView() { /* jsdom has no layout */ };
}
