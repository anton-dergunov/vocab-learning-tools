/**
 * Settings ▸ Stories: which voice reads a story, and whether it is recorded when the story is made.
 *
 * Both are **owner** state, stored beside the other pronunciation choices and read by the server
 * when it records — a phone that has never opened this screen still gets the story recorded the way
 * it was chosen here. The panel is `LoopPanel`'s shape for the same reason: a story is one more use
 * of the pronunciation orders, chosen on the page of the thing that uses it rather than on the
 * Pronunciation page, which is for the words.
 *
 * Nothing here is a device fact. Whether a recording is *kept on this device* is Settings ▸
 * Pronunciation's switch, because a part's recording is kept with the clips: the same kind of
 * thing, about the same size.
 */

import { useEffect, useState } from "react";
import {
  AcervoApiError, backendSession, type PronunciationOrder, type PronunciationSettings
} from "./api";

/* The same two orders as everywhere else, said in terms of what each does to a story. The costs are
   measured, not felt: a directed voice is one call to a text model to decide where a part breaks and
   then one call to the voice per passage, and a clear one is a single call for the whole part. */
const ORDERS: { id: PronunciationOrder; title: string; help: string }[] = [
  {
    id: "expressive", title: "A voice that takes a direction",
    help: "A part is cut into passages, each with its own direction — hushed here, amused there — and "
      + "read one at a time. You can touch a passage to hear just that. It takes a few calls a part."
  },
  {
    id: "plain", title: "A clear, even voice",
    help: "A part is read in one go, in one manner. One call a part, and no passages to touch."
  }
];

export default function StoryPanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<PronunciationSettings | null>(null);

  useEffect(() => {
    void backendSession.pronunciationSettings().then(setSettings)
      .catch((error: unknown) => onNotify(error instanceof AcervoApiError ? error.message : "Settings could not be read."));
  }, []);

  /* Optimistic, then reconciled, then rolled back if the server refused — the shape `LoopPanel` and
     `PronunciationPanel` use, because it is the same record being written. */
  const apply = async (
    changes: Parameters<typeof backendSession.savePronunciationSettings>[0],
    optimistic: PronunciationSettings
  ) => {
    const before = settings;
    if (!before) return;
    setSettings(optimistic);
    try {
      setSettings(await backendSession.savePronunciationSettings(changes));
    } catch (error) {
      setSettings(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That could not be saved.");
    }
  };

  return <section className="config-section">
    <h3>Stories</h3>
    <p className="config-help">
      A story can be read aloud, a part at a time, by the button beside its heading. The whole story is
      read in one voice: whichever of your models answers first for its first part reads the rest.
    </p>

    <h4 className="provider-heading">The voice</h4>
    <p className="config-help">
      Which of the two pronunciation orders reads a story. It is the same choice Settings ▸
      Pronunciation makes for words and example sentences and Settings ▸ Loops makes for loops, and a
      part already recorded keeps the voice it was recorded with.
    </p>
    {settings && ORDERS.map((order) => <label key={order.id} className="config-switch">
      <input
        type="radio" name="story-delivery" checked={settings.delivery.stories === order.id}
        onChange={() => void apply(
          { delivery: { stories: order.id } },
          { ...settings, delivery: { ...settings.delivery, stories: order.id }, chosen: true }
        )}
      />
      <span><strong>{order.title}</strong><span>{order.help}</span></span>
    </label>)}

    <h4 className="provider-heading">When it is recorded</h4>
    {settings && <label className="config-switch">
      <input
        type="checkbox" checked={settings.pregenerate.stories}
        onChange={(event) => void apply(
          { pregenerate: { stories: event.target.checked } },
          { ...settings, pregenerate: { ...settings.pregenerate, stories: event.target.checked }, chosen: true }
        )}
      />
      <span>
        <strong>Record a story’s narration when it is made</strong>
        <span>
          Every part is recorded as the story is made, so the audio is there when you open it.
          Nothing is played — this only decides when the recording happens. Off, a part is recorded
          the first time you press its play button, which takes a few seconds, longer with a voice
          that takes a direction because it records a passage at a time.
        </span>
      </span>
    </label>}
  </section>;
}
