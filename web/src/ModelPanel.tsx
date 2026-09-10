import { useCallback, useEffect, useState } from "react";
import {
  backendSession,
  type ModelCatalogue,
  type ModelChain,
  type ModelPair,
  type ModelProvider
} from "./api";

/**
 * The Models pane: which provider and model build an entry, in what order.
 *
 * The unit is a **(provider, model) pair**, not a provider. A free tier is metered per model, so
 * Gemini's two 500-a-day models are a thousand a day and the second is reached by the first one's
 * 429 — choosing between them is a real choice, not a detail.
 *
 * This is server state, not a device preference like the dictionary switches next door: it decides
 * what the vocabulary is made of, so an entry captured on a phone should be built by the same model
 * as one captured on a laptop. Saving is an ordinary online-only write that fails loudly.
 *
 * A pair whose provider this server has no credential for stays in the list, keeps its place and is
 * simply skipped when the chain is walked. That is deliberate: a chain is a preference and a
 * credential is a deployment fact, and a rotated key must not destroy an order or lock the owner
 * out of changing it.
 */

const KINDS: { id: string; label: string; help: string }[] = [
  {
    id: "text",
    /* Not "Entries": the same models write the briefs the picture generator works from, and will
       write whatever else needs words. What they have in common is that they produce text. */
    label: "Text",
    help: "Writes definitions, glosses, examples and usage notes when you capture a word — and the "
      + "briefs the picture models draw from. The first that answers wins; a rate-limited one hands "
      + "on to the next."
  },
  {
    id: "image",
    label: "Pictures",
    help: "For the sense pictures. Nothing reads this order yet — the job that draws them is still "
      + "to come — but what you choose here is kept."
  },
  {
    id: "audio",
    label: "Pronunciation",
    help: "For hearing a word said. Nothing reads this order yet either, and the free allowance is "
      + "a handful of clips a day rather than a batch."
  }
];

const same = (one: ModelPair, other: ModelPair) =>
  one.provider === other.provider && one.model === other.model;

/** Every pair a kind can offer, in catalogue order, with the chosen ones lifted to the front. */
function orderedPairs(providers: ModelProvider[], chosen: ModelPair[], kind: string): ModelPair[] {
  const offered = providers.flatMap((provider) =>
    (provider.models[kind] ?? []).map((model) => ({ provider: provider.id, model })));
  const picked = chosen.filter((pair) => offered.some((one) => same(one, pair)));
  return [...picked, ...offered.filter((one) => !picked.some((pair) => same(pair, one)))];
}

function ModelRow({ pair, provider, on, first, last, onToggle, onMove }: {
  pair: ModelPair;
  provider: ModelProvider | undefined;
  on: boolean;
  first: boolean;
  last: boolean;
  onToggle(next: boolean): void;
  onMove(direction: -1 | 1): void;
}) {
  const label = provider?.label ?? pair.provider;
  const missing = provider?.available === false;
  return <div className={`config-row model-row${missing ? " unavailable" : ""}`}>
    <label className="model-switch">
      <input type="checkbox" checked={on} onChange={(event) => onToggle(event.target.checked)} />
      <span className="config-main">
        <strong>
          {label}
          {/* Dimmed text alone was too quiet to notice while scrolling a long list. */}
          {missing && <span className="model-badge" title="Not available on this server">
            <span aria-hidden="true">{"⚠"}</span> unavailable
          </span>}
        </strong>
        <span className="model-id">{pair.model}</span>
        {missing && <span className="model-warning">
          {provider?.reason}. It keeps its place in the order and is passed over.
        </span>}
      </span>
    </label>
    <button
      className="icon-btn" aria-label={`Move ${label} ${pair.model} up`}
      disabled={!on || first} onClick={() => onMove(-1)}
    >{"↑"}</button>
    <button
      className="icon-btn" aria-label={`Move ${label} ${pair.model} down`}
      disabled={!on || last} onClick={() => onMove(1)}
    >{"↓"}</button>
  </div>;
}

function KindSection({ kind, label, help, catalogue, onChange }: {
  kind: string;
  label: string;
  help: string;
  catalogue: ModelCatalogue;
  onChange(kind: string, pairs: ModelPair[] | null): void;
}) {
  const chain: ModelChain | undefined = catalogue.chains[kind];
  if (!chain) return null;
  const providers = new Map(catalogue.providers.map((provider) => [provider.id, provider]));
  /* What is switched on is what will actually be asked — under an owner's chain *and* under the
     server's own order, which the server resolves and sends here as `pairs`.

     Showing every box unchecked under the deployment default was a lie with consequences: unticking
     the last model looked like turning capture off, and the server carried on building entries with
     the model at the head of its own order. The pane must show what will happen, so an inherited
     order arrives ticked and says whose it is. Changing anything makes the order yours. */
  const live = chain.pairs;
  const inherited = chain.source === "deployment";
  const pairs = orderedPairs(catalogue.providers, live, kind);

  /* Three states, and unticking the last box reaches the third rather than bouncing off it:
     an order of your own, nothing at all, or "whatever the server does". Switching everything off
     is a real answer — most of Acervo works without a model, and reading, editing and writing YAML
     by hand all still do — so it is stored rather than refused. `null` is the way back, and it has
     its own button, because no arrangement of tick boxes could mean "stop deciding". */
  const change = (next: ModelPair[]) => onChange(kind, next);
  const followServer = () => onChange(kind, null);

  return <div className="model-kind">
    <h4>{label}</h4>
    <p className="config-help">{help}</p>
    {inherited && <p className="config-help">
      {live.length
        ? "You have not chosen, so this server’s own order is in force — shown ticked below. "
          + "Change anything and the order becomes yours."
        : "You have not chosen, and this server has nothing it can use."}
      {chain.reason ? ` Right now it cannot build: ${chain.reason}.` : ""}
    </p>}
    {!inherited && live.length === 0 && <p className="config-help model-warning">
      Switched off. Nothing here will be generated, and the rest of Acervo works as usual.
    </p>}
    {!inherited && live.length > 0 && chain.reason && <p className="config-help model-warning">
      Nothing you have chosen can be asked right now — {chain.reason}.
    </p>}
    {!inherited && <p className="config-help">
      <button className="link-btn" onClick={followServer}>Use this server’s order instead</button>
    </p>}
    <div className="config-list">
      {pairs.map((pair) => {
        const at = live.findIndex((one) => same(one, pair));
        return <ModelRow
          key={`${pair.provider} ${pair.model}`}
          pair={pair}
          provider={providers.get(pair.provider)}
          on={at >= 0}
          first={at <= 0}
          last={at < 0 || at === live.length - 1}
          onToggle={(next) => change(
            next ? [...live, pair] : live.filter((one) => !same(one, pair))
          )}
          onMove={(direction) => {
            const next = [...live];
            const other = next[at + direction];
            if (!other) return;
            next[at + direction] = next[at];
            next[at] = other;
            change(next);
          }}
        />;
      })}
    </div>
  </div>;
}

export default function ModelPanel({ onNotify }: { onNotify(message: string): void }) {
  const [catalogue, setCatalogue] = useState<ModelCatalogue | null>(null);
  const [failed, setFailed] = useState(false);
  const [working, setWorking] = useState(false);

  const refresh = useCallback(async () => {
    try { setCatalogue(await backendSession.fetchModels()); }
    catch { setFailed(true); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  /** One write, and the server's answer replaces what is shown — never this client's optimism. */
  async function save(kind: string, pairs: ModelPair[] | null) {
    setWorking(true);
    try {
      setCatalogue(await backendSession.saveModelSelection({ [kind]: pairs }));
      if (pairs === null) onNotify("This server’s own order is back in force.");
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "That choice could not be saved.");
    } finally { setWorking(false); }
  }

  if (failed) return <section className="config-section">
    <h3>Providers</h3>
    <p className="config-help">
      Your server could not be reached, so what it builds entries with is unknown right now.
    </p>
  </section>;

  if (!catalogue) return <section className="config-section">
    <h3>Providers</h3>
    <p className="config-help">Asking your server which models it can use…</p>
  </section>;

  return <section className="config-section">
    <h3>Providers</h3>
    <p className="config-help">
      Which model builds what, and in what order. Switch one on to use it, and use the arrows to say
      which is asked first; when one is rate limited or down the next answers, and the entry records
      which one actually did. This is an account setting, so it follows you to every device.
    </p>

    {KINDS.map((entry) => <KindSection
      key={entry.id} {...entry} kind={entry.id} catalogue={catalogue}
      onChange={(kind, pairs) => void save(kind, pairs)}
    />)}

    <div className="model-usage">
      {catalogue.providers.filter((provider) => provider.usageUrl).map((provider) => <a
        key={provider.id} className="tb-btn"
        href={provider.usageUrl ?? undefined} target="_blank" rel="noreferrer noopener"
      >{provider.label} usage</a>)}
    </div>
    <p className="config-help">
      No provider will tell Acervo how much of an allowance is left, so these open the provider{"’"}s
      own page.
    </p>

    {working && <p className="config-help" role="status">Saving…</p>}
  </section>;
}
