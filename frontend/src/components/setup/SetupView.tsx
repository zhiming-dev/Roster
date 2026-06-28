import { useEffect, useState, type ReactNode } from "react";
import { configApi, type AgentCfg, type SearchCfg, type TeamConfig } from "../../api/config";
import styles from "./setup.module.css";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className={styles.field}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function KeyBadge({ status }: { status: AgentCfg["key_status"] }) {
  if (status === "env") return <span className={`${styles.badge} ${styles.badgeOk}`}>key ●</span>;
  if (status === "inline")
    return <span className={`${styles.badge} ${styles.badgeWarn}`}>key inline ⚠</span>;
  return <span className={`${styles.badge} ${styles.badgeNone}`}>no key</span>;
}

function SearchEditor({
  search,
  providers,
  onSaved,
}: {
  search: SearchCfg;
  providers: string[];
  onSaved: () => void | Promise<void>;
}) {
  const [provider, setProvider] = useState(search.provider);
  const [apiKey, setApiKey] = useState("");
  const save = async () => {
    await configApi.updateSearch({ provider, ...(apiKey ? { api_key: apiKey } : {}) });
    setApiKey("");
    await onSaved();
  };
  return (
    <div className={styles.searchRow}>
      <Field label="Provider">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Tavily API key">
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={search.key_status === "env" ? "configured ● (blank = keep)" : "paste Tavily key"}
        />
      </Field>
      <button className={styles.primary} onClick={() => void save()}>
        Save
      </button>
    </div>
  );
}

function AgentEditor({
  agent,
  available,
  onClose,
  onSaved,
}: {
  agent: AgentCfg | null;
  available: TeamConfig["available"];
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [name, setName] = useState(agent?.name ?? "");
  const [role, setRole] = useState(agent?.role ?? "");
  const [persona, setPersona] = useState(agent?.persona ?? "");
  const [provider, setProvider] = useState(agent?.provider ?? "openai_compatible");
  const [endpoint, setEndpoint] = useState(agent?.endpoint ?? "");
  const [model, setModel] = useState(agent?.model ?? "");
  const [temperature, setTemperature] = useState(agent?.options.temperature ?? 0.2);
  const [maxTokens, setMaxTokens] = useState(agent?.options.max_tokens ?? 1500);
  const [search, setSearch] = useState(agent?.tools.includes("search") ?? false);
  const [emoji, setEmoji] = useState(agent?.emoji ?? "");
  const [color, setColor] = useState(agent?.color ?? "");
  const [apiKey, setApiKey] = useState("");
  const [err, setErr] = useState("");

  const save = async () => {
    try {
      const tools = search ? ["search"] : [];
      const options = { temperature: Number(temperature), max_tokens: Number(maxTokens) };
      const key = apiKey ? { api_key: apiKey } : {};
      const ident = { emoji, color };
      if (agent === null) {
        await configApi.addAgent({ name, role: role || name, persona, provider, endpoint, model, tools, options, ...ident, ...key });
      } else {
        await configApi.updateAgent(agent.name, { role, persona, provider, endpoint, model, tools, options, ...ident, ...key });
      }
      await onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>{agent === null ? "Add agent" : `Edit ${agent.name}`}</h3>
        {err && <div className={styles.err}>{err}</div>}
        {agent === null && (
          <Field label="Name (identifier)">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. analyst" />
          </Field>
        )}
        <Field label="Role">
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder={name || "role"} />
        </Field>
        <div className={styles.fieldRow}>
          <Field label="Avatar (emoji)">
            <input value={emoji} onChange={(e) => setEmoji(e.target.value)} placeholder="🤖" maxLength={4} />
          </Field>
          <Field label="Color (hex · blank = role default)">
            <input value={color} onChange={(e) => setColor(e.target.value)} placeholder="#7c5cff" />
          </Field>
        </div>
        <Field label="Persona (system prompt / soul)">
          <textarea value={persona} onChange={(e) => setPersona(e.target.value)} rows={7} />
        </Field>
        <div className={styles.fieldRow}>
          <Field label="Provider">
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {available.providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Model">
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="model id" />
          </Field>
        </div>
        <Field label="Endpoint">
          <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://…" />
        </Field>
        <div className={styles.fieldRow}>
          <Field label="Temperature">
            <input type="number" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
          </Field>
          <Field label="Max tokens">
            <input type="number" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} />
          </Field>
        </div>
        <Field label="API key (stored in .env, write-only)">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              agent?.key_status === "env"
                ? "configured ● (blank = keep)"
                : agent?.key_status === "inline"
                  ? "inline ⚠ — enter to move to .env"
                  : "paste key"
            }
          />
        </Field>
        <label className={styles.check}>
          <input type="checkbox" checked={search} onChange={(e) => setSearch(e.target.checked)} /> web
          search tool
        </label>
        <div className={styles.modalActions}>
          <button onClick={onClose}>Cancel</button>
          <button className={styles.primary} onClick={() => void save()}>
            {agent === null ? "Add agent" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function SetupView({ onClose }: { onClose: () => void }) {
  const [cfg, setCfg] = useState<TeamConfig | null>(null);
  const [editing, setEditing] = useState<AgentCfg | "new" | null>(null);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      setCfg(await configApi.get());
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const apply = async () => {
    await configApi.reset();
    setMsg("Applied — a new chat now uses the updated team.");
  };
  const migrate = async () => {
    const r = await configApi.migrateKeys();
    await load();
    setMsg(`Moved ${r.moved ?? 0} inline key(s) into .env.`);
  };
  const remove = async (name: string) => {
    if (!confirm(`Remove agent “${name}”?`)) return;
    await configApi.deleteAgent(name);
    await load();
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h2>Team setup</h2>
        <span className={styles.spacer} />
        <button className={styles.ghost} onClick={() => void apply()}>
          Apply to new chat
        </button>
        <button className={styles.primary} onClick={onClose}>
          Done
        </button>
      </div>

      {msg && <div className={styles.note}>{msg}</div>}

      {!cfg ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          {cfg.inline_keys > 0 && (
            <div className={styles.warn}>
              ⚠ {cfg.inline_keys} API key(s) are stored inline (plaintext) in your config.
              <button onClick={() => void migrate()}>Move to .env</button>
            </div>
          )}

          <section className={styles.section}>
            <h3>Web search</h3>
            <SearchEditor
              search={cfg.search}
              providers={cfg.available.search_providers}
              onSaved={load}
            />
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHead}>
              <h3>Agents</h3>
              <button className={styles.ghost} onClick={() => setEditing("new")}>
                + Add agent
              </button>
            </div>
            <div className={styles.grid}>
              {cfg.agents.map((a) => (
                <div key={a.name} className={styles.card}>
                  <div className={styles.cardTop}>
                    <span
                      className={styles.avatar}
                      style={{ borderColor: a.color ?? `var(--r-${a.role})` }}
                    >
                      {a.emoji}
                    </span>
                    <b>{a.name}</b>
                    <span className={styles.role}>{a.role}</span>
                    <KeyBadge status={a.key_status} />
                  </div>
                  <div className={styles.cardModel}>
                    {a.provider ?? "—"} · {a.model ?? "—"}
                  </div>
                  <div className={styles.cardTools}>{a.tools.length ? a.tools.join(", ") : "no tools"}</div>
                  <div className={styles.cardActions}>
                    <button onClick={() => setEditing(a)}>Edit</button>
                    {!a.is_planner && (
                      <button className={styles.danger} onClick={() => void remove(a.name)}>
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {editing && (
            <AgentEditor
              agent={editing === "new" ? null : editing}
              available={cfg.available}
              onClose={() => setEditing(null)}
              onSaved={async () => {
                setEditing(null);
                await load();
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
