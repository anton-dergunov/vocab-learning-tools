const ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";
const ID_LENGTH = 15;
const UNBIASED_LIMIT = Math.floor(256 / ALPHABET.length) * ALPHABET.length;

export function newId(): string {
  let id = "";
  const bytes = new Uint8Array(ID_LENGTH);
  while (id.length < ID_LENGTH) {
    crypto.getRandomValues(bytes);
    for (let index = 0; index < bytes.length && id.length < ID_LENGTH; index += 1) {
      if (bytes[index] < UNBIASED_LIMIT) id += ALPHABET[bytes[index] % ALPHABET.length];
    }
  }
  return id;
}

export const newDeviceId = newId;
export const nowInstant = () => new Date().toISOString();

/* ── derived ids ────────────────────────────────────────────────────────
   Two ids in Acervo are not random. An image prompt's is a function of the sense it belongs to, and
   a clip example's is a function of the sense *and* the corpus segment it quotes.

   That is load-bearing rather than tidy. It is what lets a saved document and the server's own
   enrichment both work on a sense with no coordination at all — they compute the same id, so the second to arrive
   finds the work done or is refused as stale — and it is why a picture's `suppressed` is a field
   rather than a tombstone, since a tombstoned row would be re-created at the same id.

   A removed clip is an ordinary tombstone instead, and that is safe only because the clip search is
   one-shot at save: nothing re-searches, so nothing can write at the tombstone's id and resurrect
   it. A rescan must add a suppression field before it ships, exactly as the image pipeline had to.

   This function used to exist only in Python (`acervo.images.ids.image_prompt_id`), and
   `saveArticle` minted a random id instead. Importing a bundle then produced *two* rows for one
   sense: one from the document, one from the picture being put back. **The two halves of the check
   that these agree are `tests/unit/jobs/test_sense_images.py` and `ids.test.ts`.** */

const DERIVED_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz";
const IMAGE_PROMPT_NAMESPACE = "acervo/imagePrompt/v1";
const CLIP_EXAMPLE_NAMESPACE = "acervo/clipExample/v1";
const PRONUNCIATION_NAMESPACE = "acervo/pronunciation/v1";

/**
 * SHA-256, synchronously.
 *
 * `crypto.subtle.digest` is async and this is called from inside the synchronous change builder in
 * `saveArticle`, which assembles a whole write before any of it is sent. Small enough to read, and
 * pinned against known vectors in `ids.test.ts`.
 */
function sha256(text: string): Uint8Array {
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];
  const hash = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ];

  const message = new TextEncoder().encode(text);
  // Padded to a multiple of 64 bytes: a 0x80 byte, zeroes, then the bit length as 64 bits.
  const blocks = Math.ceil((message.length + 9) / 64);
  const padded = new Uint8Array(blocks * 64);
  padded.set(message);
  padded[message.length] = 0x80;
  new DataView(padded.buffer).setUint32(padded.length - 4, message.length * 8, false);

  const rotate = (value: number, by: number) => (value >>> by) | (value << (32 - by));
  const words = new Uint32Array(64);
  const view = new DataView(padded.buffer);

  for (let block = 0; block < blocks; block += 1) {
    for (let index = 0; index < 16; index += 1) words[index] = view.getUint32(block * 64 + index * 4, false);
    for (let index = 16; index < 64; index += 1) {
      const a = words[index - 15];
      const b = words[index - 2];
      const s0 = rotate(a, 7) ^ rotate(a, 18) ^ (a >>> 3);
      const s1 = rotate(b, 17) ^ rotate(b, 19) ^ (b >>> 10);
      words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const S1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
      const choose = (e & f) ^ (~e & g);
      const temp1 = (h + S1 + choose + K[index] + words[index]) >>> 0;
      const S0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (S0 + majority) >>> 0;
      h = g; g = f; f = e; e = (d + temp1) >>> 0;
      d = c; c = b; b = a; a = (temp1 + temp2) >>> 0;
    }
    const round = [a, b, c, d, e, f, g, h];
    for (let index = 0; index < 8; index += 1) hash[index] = (hash[index] + round[index]) >>> 0;
  }

  const digest = new Uint8Array(32);
  const out = new DataView(digest.buffer);
  hash.forEach((word, index) => out.setUint32(index * 4, word, false));
  return digest;
}

/** The id an image prompt for this sense must have, wherever it is created. */
export function imagePromptId(senseId: string): string {
  return derivedId(`${IMAGE_PROMPT_NAMESPACE}:${senseId}`);
}

/**
 * The id a clip example quoting this segment under this sense must have, wherever it is created.
 *
 * The pair is the identity rather than the sense alone, so a sense may hold clips from several
 * segments while two writers that chose the same segment converge on one row. Twinned with
 * `acervo.clips.ids.clip_example_id`.
 */
export function clipExampleId(senseId: string, clipRef: string): string {
  return derivedId(`${CLIP_EXAMPLE_NAMESPACE}:${senseId}:${clipRef}`);
}

/**
 * The id the clip reading this field must have, wherever it is recorded.
 *
 * Keyed on what is read, so a field has one clip and "Record again" rewrites it. Twinned with
 * `acervo.pronunciation.ids.pronunciation_id`.
 */
export function pronunciationId(targetKind: string, targetId: string): string {
  return derivedId(`${PRONUNCIATION_NAMESPACE}:${targetKind}:${targetId}`);
}

/**
 * Base-36 of the digest, least significant digit first, which is what `divmod` in a loop produces
 * on the Python side. Done with BigInt because the digest is 256 bits.
 */
function derivedId(input: string): string {
  let value = 0n;
  for (const byte of sha256(input)) value = (value << 8n) | BigInt(byte);
  const base = BigInt(DERIVED_ALPHABET.length);
  let id = "";
  for (let index = 0; index < ID_LENGTH; index += 1) {
    id += DERIVED_ALPHABET[Number(value % base)];
    value /= base;
  }
  return id;
}
