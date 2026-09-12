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
import { languageOf } from "./languages";

type Channel = Awaited<ReturnType<typeof channels>>[number];

/**
 * By language, then by the catalogue's own sections.
 *
 * The sections are the retrieval repository's curation — "Long-form conversation and contemporary
 * informal speech" is a judgement somebody made about what a learner gets from those channels, and
 * it is more use here than any grouping Acervo could invent. Language is the outer level because it
 * is the one that will actually multiply: the corpus indexes Spanish today and will not forever.
 */
function grouped(rows: Channel[]): { language: string; sections: { name: string; rows: Channel[] }[] }[] {
  const byLanguage = new Map<string, Map<string, Channel[]>>();
  for (const row of rows) {
    const sections = byLanguage.get(row.source_language) ?? new Map<string, Channel[]>();
    const name = row.section_name || "Other";
    sections.set(name, [...(sections.get(name) ?? []), row]);
    byLanguage.set(row.source_language, sections);
  }
  return [...byLanguage].map(([language, sections]) => ({
    language,
    sections: [...sections].map(([name, rows]) => ({ name, rows }))
  }));
}

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

  const apply = async (changes: Partial<Pick<ClipSettings, "searchEnabled" | "selfContainedOnly">>) => {
    const before = settings;
    if (!before) return;
    setSettings({ ...before, ...changes, chosen: true });
    try {
      setSettings(await backendSession.saveClipSettings(changes));
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
        onChange={(event) => void apply({ searchEnabled: event.target.checked })}
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

    <label className="config-switch">
      <input
        type="checkbox" checked={settings.selfContainedOnly}
        onChange={(event) => void apply({ selfContainedOnly: event.target.checked })}
      />
      <span>
        <strong>Only passages that stand on their own</strong>
        <span>
          Off, a clip may begin mid-thought — which is how you meet a language in the first place,
          walking into a room where somebody is already talking, and it is much of what makes these
          worth watching. On, a passage whose subject you would have to guess at is rejected, which
          is steadier to read and finds fewer clips.
        </span>
      </span>
    </label>

    <h4 className="config-subhead">Channels</h4>
    <p className="config-help">
      The channel list belongs to the corpus service, not to Acervo, and is shared by everything
      that reads it. Switching one on changes nothing by itself: its videos arrive the next time a
      harvest runs, and a harvest is a command somebody runs —
      <code>run-worker.sh index-clips</code>, from a shell or a scheduled task. Words you already
      have are never re-searched either way.
    </p>

    {channelError && <p className="config-help warn">{channelError}</p>}
    {!channelError && rows === null && corpus.reachable
      && <p className="config-help" role="status">Reading the channel list…</p>}

    {rows && grouped(rows).map(({ language, sections }) => {
      const all = sections.flatMap((section) => section.rows);
      const on = all.filter((channel) => channel.enabled).length;
      return <details key={language} className="channel-group">
        {/* Shut by default: this is a long list that is read rarely and changed more rarely still,
            and the count in the summary answers the question most visits are actually asking. */}
        <summary>
          <span className="channel-group-name">
            {`${languageOf(language).flag} ${languageOf(language).name}`}
          </span>
          <span className="channel-group-count">{`${on} of ${all.length} on`}</span>
        </summary>
        {sections.map((section) => <div key={section.name} className="channel-section">
          <h5>{section.name}</h5>
          {section.rows.map((channel) => <div key={channel.id} className="channel-row">
            <input
              id={`channel-${language}-${channel.id}`}
              type="checkbox" checked={channel.enabled}
              onChange={(event) => void toggle(channel, event.target.checked)}
            />
            <div className="channel-text">
              {/* The name is the link, because the useful thing to do with a channel you are
                  deciding about is watch some of it. The checkbox is the switch. */}
              <a href={channel.url} target="_blank" rel="noreferrer noopener">{channel.name}</a>
              {/* No language here: it is the group heading. */}
              <span>{[...(channel.varieties ?? []), ...(channel.speech_style ?? [])].join(" · ")}</span>
            </div>
          </div>)}
        </div>)}
      </details>;
    })}
  </section>;
}
