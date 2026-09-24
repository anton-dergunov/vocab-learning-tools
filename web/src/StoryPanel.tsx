/**
 * Settings ▸ Stories: which voice reads a story, whether it is recorded when the story is made, and
 * whether its later pictures are drawn from its earlier ones.
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
 *
 * The picture choice is stored with the other picture settings (`/images/settings`), because the
 * server reads it when it draws; it is shown here because it is a question about stories.
 */

import { useEffect, useState } from "react";
import {
  AcervoApiError, backendSession, type ImageSettings, type PronunciationOrder,
  type PronunciationSettings, type StoryContinuity
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

/* Measured rather than felt (experiments/story-picture-reference): drawn from its earlier pictures,
   a story was preferred 17 times in 29 and lost 4, all four in the first run's photoreal style;
   with the picture-first prompt that shipped, it did not lose in any style. */
const CONTINUITY: { id: StoryContinuity; title: string; help(photographic: string): string }[] = [
  {
    id: "all", title: "In every style",
    help: () => "A later picture is drawn from the earlier pictures of the people and places it "
      + "shows again, so they stay recognisable."
  },
  {
    id: "artwork", title: "In drawn and painted styles only",
    help: (photographic) => "The same, with the photographic styles left out"
      + `${photographic ? `: ${photographic}` : ""}.`
  },
  {
    id: "off", title: "Off",
    help: () => "Every picture is drawn from its own description alone."
  }
];

export default function StoryPanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<PronunciationSettings | null>(null);
  const [pictures, setPictures] = useState<ImageSettings | null>(null);

  useEffect(() => {
    const failed = (error: unknown) =>
      onNotify(error instanceof AcervoApiError ? error.message : "Settings could not be read.");
    void backendSession.pronunciationSettings().then(setSettings).catch(failed);
    void backendSession.imageSettings().then(setPictures).catch(failed);
  }, []);

  const choosePictures = async (storyContinuity: StoryContinuity) => {
    const before = pictures;
    if (!before) return;
    setPictures({ ...before, storyContinuity, chosen: true });
    try {
      setPictures(await backendSession.saveImageSettings({ storyContinuity }));
    } catch (error) {
      setPictures(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That could not be saved.");
    }
  };
  const photographic = (pictures?.styles ?? []).filter((style) => style.photographic)
    .map((style) => style.label).join(", ");

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

    <h4 className="provider-heading">Keep characters and places consistent across pictures</h4>
    <p className="config-help">
      Each picture comes first; the earlier ones are only a guide to who is who. A person or place
      that does not appear again is never carried over, and a model that cannot take earlier
      pictures draws every part from its description, as before.
    </p>
    {pictures && <div className="config-choices" role="radiogroup"
      aria-label="Keep characters and places consistent across pictures">
      {CONTINUITY.map((choice) => <label key={choice.id} className="config-switch">
        <input
          type="radio" name="story-continuity" value={choice.id}
          checked={pictures.storyContinuity === choice.id}
          onChange={() => void choosePictures(choice.id)}
        />
        <span><strong>{choice.title}</strong><span>{choice.help(photographic)}</span></span>
      </label>)}
    </div>}
  </section>;
}
