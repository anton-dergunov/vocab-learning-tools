# Meaning space · a map of the vocabulary

**Status:** an idea, lightly documented and not yet planned. A later session specifies it. This page
records what it is for, the shape it is expected to take, and the questions a plan has to answer.
It is the first of the [vocabulary views](vocabulary-views.md) to be worked out.

## Outcome

The learner opens a map of their own vocabulary. Words that mean related things sit together, in
every language at once. Zoomed out, the map shows labelled regions — the learner's interests, as
their words reveal them. Zoomed in, it shows the words, and then their separate senses. Tapping a
word opens its article. Tapping a region offers words that would extend it, and each one is a tap
away from capture.

It is two things on one surface: a way to **explore** what is held, and a way to **discover** what to
add next. The second is the discovery prototype in the sibling research repository
`interest-aligned-vocabulary-recommendation` (its `docs/discovery-v0.md`). This map is where that
prototype's cluster picker would live inside Acervo.

## Shape

- **One point per sense, not per word.** Polysemy is exactly what collapses in a word-level map; the
  schema already separates senses, so a word with two meanings appears in two places.
- **Embed the sense, not the surface form.** The text embedded is the headword with its part of
  speech, definition and glosses. A bare word's embedding is dominated by spelling and frequency.
- **One multilingual space.** Spanish, English and Chinese go into the same space, so an interest
  held in one language shows up next to the same interest in another with no extra mechanism.
- **Clusters, hierarchically.** Agglomerative clustering rather than HDBSCAN, which would mark much
  of a thousand-word vocabulary as noise, and that noise is the long tail of minor interests worth
  keeping. The hierarchy is what supplies labels at each zoom level.
- **Labels without a model call first.** The words nearest a cluster's centre, plus terms distinctive
  to the cluster (c-TF-IDF). A model-written label only if those read poorly.
- **Layers over the same map**, added one at a time: language (tint), recall strength and exposure
  once the learning loop is wired, recency of adding, and **ghosts** — proposed words, dashed, where
  a region is thin.
- **Tablet first.** Pinch to zoom and tap to open. No filters or sliders on the first version.

## Questions for the plan

- **Where are embeddings computed?** The server, with a local encoder in the image (small model,
  larger image), or through a provider as a new kind in the model catalogue, which has no embedding
  kind today. And what the standalone macOS application does, with no server at all.
- **Where do they live?** Embeddings and coordinates are derived from the graph. They probably should
  not be a replicated collection; a derived file served like a dictionary artifact is the obvious
  alternative. Either way, cached on the sense id and its revision so only changed senses are
  recomputed.
- **Does the map stay put?** A layout recomputed from scratch after every new word reshuffles the
  whole map, and a map that moves cannot be learned. New points need placing into an existing
  layout, with a full relayout only occasionally and deliberately.
- **Is it stable when small?** Clusters churn below roughly 150 entries per language. A young
  vocabulary, or a new language, may need a plain map with no regions.
- **Which encoder?** A small multilingual sentence encoder to start, compared against a stronger
  one once there is a measurement. The discovery prototype's held-out recall gives one.
- **How does a ghost become a word?** Through capture, like every other word, so the article is
  reviewed before it is saved. The map decides *which* word and never builds the entry itself.
- **What counts as success?** Whether the regions are recognisable as the learner's own topics, and
  whether ghosts proposed from a region are added more often than suggestions made without one.
