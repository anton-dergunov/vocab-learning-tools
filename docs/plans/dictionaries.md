# Dictionaries · what is still to do

**Status:** open, none of it urgent. The design as built is
[`../features/dictionaries.md`](../features/dictionaries.md).

- **Mapper quality, continuously.** Reading real entries is what finds faults — a survey rendering six
  headwords from every compiled artifact found faults a six-entry check could not. Repeat it when a
  converter or `externalHtml.ts` changes, and choose which dictionaries are worth carrying separately
  from rendering them well.
- **Building a dictionary from the interface.** `build.build` already takes a progress callback and
  raises rather than printing, so this is a job kind plus the Settings row, with no change to the
  artifact, catalogue, client or reader.
- **A catalogue health check.** A monthly job that asks every source URL whether it still answers and
  reports what moved. The FreeDict and GitHub resolvers already remove the most common cause of rot.
- **Discard downloaded sources by default** once the conversions are trusted. They are cached in
  `data/dictionaries/src/` so changing a converter is a re-run rather than another 1.19 GB fetch, and
  they are 2–25× the artifact; `--discard-source` already drops them.
