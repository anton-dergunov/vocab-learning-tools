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
