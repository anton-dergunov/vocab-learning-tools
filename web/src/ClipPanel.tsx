/**
 * Settings ▸ Clips: whether the corpus is consulted unattended, what it holds, and which channels
 * it harvests.
 *
 * Shaped like Settings ▸ Dictionaries rather than Settings ▸ Pictures, because the interesting
 * part is not a set of switches Acervo owns — it is a **separate service** with its own catalogue,
 * reached through Acervo's proxy. Acervo ships no channel list (§2.10): copying one here would
 * create a second thing to keep in step and a second place to curate.
 *
 * The corpus reading is deliberately not a health dashboard. It answers the two questions someone
 * actually has in front of this screen — does the service answer, and does it hold anything for the
 * language I am learning — and stops there.
 */

import { useCallback, useEffect, useState } from "react";
import { AcervoApiError, backendSession, type ClipSettings } from "./api";
import { channels, setChannelEnabled, SpeechRetrievalApiError } from "./clips";

type Channel = Awaited<ReturnType<typeof channels>>[number];

function reason(error: unknown, fallback: string): string {
  if (error instanceof AcervoApiError) return error.message;
  if (error instanceof SpeechRetrievalApiError) return error.message;
  return fallback;
}

export default function ClipPanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<ClipSettings | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [rows, setRows] = useState<Channel[] | null>(null);
  const [channelError, setChannelError] = useState<string | null>(null);

  const load = useCallback(() => {
    void backendSession.clipSettings()
      .then(setSettings)
      .catch((error: unknown) => setFailed(reason(
        error, "These settings live on the server, which could not be reached."
      )));
  }, []);

  useEffect(load, [load]);

  /* The catalogue is fetched separately from the settings, and a failure in it is shown in place
     rather than taking the pane down: the switch above is still meaningful when the corpus is
     unreachable, and it is the thing someone came here to change. */
  useEffect(() => {
    if (!settings?.corpus.reachable) return;
    let live = true;
    void channels()
      .then((found) => { if (live) setRows(found); })
      .catch((error: unknown) => {
        if (live) setChannelError(reason(error, "The channel list could not be read."));
      });
    return () => { live = false; };
  }, [settings?.corpus.reachable]);

  const apply = async (searchEnabled: boolean) => {
    const before = settings;
    if (!before) return;
    setSettings({ ...before, searchEnabled, chosen: true });
    try {
      setSettings(await backendSession.saveClipSettings({ searchEnabled }));
    } catch (error) {
      setSettings(before);
      onNotify(reason(error, "That change was not saved."));
    }
  };

  const toggle = async (channel: Channel, enabled: boolean) => {
    const before = rows ?? [];
    setRows(before.map((row) => row.id === channel.id ? { ...row, enabled } : row));
    try {
      await setChannelEnabled(channel.source_language, channel.id, enabled);
    } catch (error) {
      setRows(before);
      onNotify(reason(error, "That channel could not be changed."));
    }
  };

  if (failed) return <section className="config-section">
    <h3>Clips</h3>
    <p className="config-help warn">{failed}</p>
  </section>;

  if (!settings) return <section className="config-section">
    <h3>Clips</h3>
    <p className="config-help" role="status">Reading your settings…</p>
  </section>;

  const { corpus } = settings;

  return <section className="config-section">
    <h3>Clips</h3>
    <p className="config-help">
      A clip is a real person saying your word on video, chosen from a corpus of captions by a model
      that reads your senses first. Most words get none, and that is the intended answer — a clip
      earns its place by showing something a written example cannot.
    </p>

    {!corpus.configured && <p className="config-help warn">
      This server has no spoken-usage corpus configured, so no clips can be found.
    </p>}

    {corpus.configured && !corpus.reachable && <p className="config-help warn">
      The corpus is configured but did not answer{corpus.error ? ` (${corpus.error})` : ""}. Clips
      already saved still read and play; nothing new will be found until it is back.
    </p>}

    {corpus.reachable && <div className="corpus-readout">
      {corpus.ready
        ? <p className="config-help">
            {corpus.videos?.toLocaleString()} videos, {corpus.segments?.toLocaleString()} segments,
            in {(corpus.indexedLanguages ?? []).join(", ") || "no language yet"}.
            {corpus.builtAt && ` Indexed ${new Date(corpus.builtAt).toLocaleDateString()}.`}
          </p>
        : <p className="config-help warn">
            The corpus is running but has not built an index yet, which is the normal state on a
            fresh deployment. Nothing can be searched until it has.
          </p>}
    </div>}

    <label className="config-switch">
      <input
        type="checkbox" checked={settings.searchEnabled}
        onChange={(event) => void apply(event.target.checked)}
      />
      <span>
        <strong>Look for clips</strong>
        <span>
          A word you save is searched once, behind the article, and the server works through
          anything never searched. Off, nothing is searched on its own. A word is only ever searched
          once either way — adding a channel does not go back over words you already have.
        </span>
      </span>
    </label>

    <h4 className="config-subhead">Channels</h4>
    <p className="config-help">
      The channel list belongs to the corpus service, not to Acervo, and is shared by everything
      that reads it. Switching one on adds its videos at the next harvest; it does not change words
      you already have.
    </p>

    {channelError && <p className="config-help warn">{channelError}</p>}
    {!channelError && rows === null && corpus.reachable
      && <p className="config-help" role="status">Reading the channel list…</p>}

    {rows && <div className="channel-list">
      {rows.map((channel) => <label key={`${channel.source_language}/${channel.id}`} className="style-switch">
        <input
          type="checkbox" checked={channel.enabled}
          onChange={(event) => void toggle(channel, event.target.checked)}
        />
        <span>
          <strong>{channel.name}</strong>
          <span>{[channel.source_language, ...(channel.varieties ?? []), ...(channel.speech_style ?? [])].join(" · ")}</span>
        </span>
      </label>)}
    </div>}
  </section>;
}
