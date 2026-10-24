import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, get } from "./api";
import { callback, setupAuth, signIn, signOut, token } from "./auth";
import { human, money, timestamp } from "./format";
import { initTelemetry } from "./telemetry";
import type {
  Customer,
  Policy,
  Claim,
  Health,
  Page,
  RuntimeConfig,
  User,
  Workspace,
} from "./types";

const meta = {
  customers: {
    title: "Customer explorer",
    subtitle: "A clearer view of your customers and their settled receipts.",
    icon: "◉",
    eyebrow: "RELATIONSHIPS",
    grain: "One row per customer and currency",
    sorts: [
      ["default", "Customer ID"],
      ["full_name", "Customer name"],
      ["total_settled_receipts_amt", "Settled receipts"],
    ],
  },
  policies: {
    title: "Policy overview",
    subtitle: "Published portfolio metrics, with every currency kept distinct.",
    icon: "▤",
    eyebrow: "PORTFOLIO",
    grain: "One row per snapshot, product group and currency",
    sorts: [
      ["default", "Snapshot and product"],
      ["product_name", "Product name"],
      ["active_policy_count", "Active policies"],
      ["active_current_term_amt", "Current-term amount"],
    ],
  },
  claims: {
    title: "Claims explorer",
    subtitle: "Understand claim status, paid amounts and reporting timelines.",
    icon: "◇",
    eyebrow: "CLAIMS",
    grain: "One row per claim · selected performance fields",
    sorts: [
      ["default", "Claim reference"],
      ["settled_amount", "Settled amount"],
      ["days_to_report", "Days to report"],
      ["claim_status_cd", "Claim status"],
    ],
  },
  health: {
    title: "Data health",
    subtitle: "Know when your data was published and how it was checked.",
    icon: "⌁",
    eyebrow: "TRUST & QUALITY",
    grain: "Publication status and latest pipeline attempt",
    sorts: [],
  },
};
const columns: {
  customers: [keyof Customer, string][];
  policies: [keyof Policy, string][];
  claims: [keyof Claim, string][];
} = {
  customers: [
    ["full_name", "Customer"],
    ["client_category_cd", "Segment"],
    ["primary_territory", "Territory"],
    ["total_settled_receipts_amt", "Settled receipts"],
  ],
  policies: [
    ["product_name", "Product group"],
    ["lob_cd", "Line of business"],
    ["active_policy_count", "Active policies"],
    ["active_current_term_amt", "Current-term amount"],
    ["new_active_policies", "New active"],
  ],
  claims: [
    ["loss_event_sk", "Claim reference"],
    ["lob_cd", "Line of business"],
    ["claim_status_cd", "Status"],
    ["days_to_report", "Days to report"],
    ["settled_amount", "Settled amount"],
  ],
};
function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      O<span />
    </span>
  );
}
function ErrorBox({
  error,
  retry,
  login,
}: {
  error: Error;
  retry: () => void;
  login: () => void;
}) {
  const e = error instanceof ApiError ? error : undefined;
  return (
    <div role="alert" className="error-box">
      <div>
        <strong>
          {e?.code === "publication_changed"
            ? "A new release is ready"
            : "We couldn’t load this view"}
        </strong>
        <p>{error.message}</p>
        {e?.requestId && <small>Support reference: {e.requestId}</small>}
      </div>
      <button
        className="button secondary"
        onClick={e?.status === 401 ? login : retry}
      >
        {e?.status === 401 ? "Sign in again" : "Refresh view"}
      </button>
    </div>
  );
}
function DataHealth({ data }: { data: Health }) {
  return (
    <>
      <div className="stats">
        <article>
          <span>Publication</span>
          <strong className={data.stale ? "amber" : "green"}>
            {data.stale ? "Needs attention" : "Up to date"}
          </strong>
          <small>Based on the source cutoff</small>
        </article>
        <article>
          <span>Latest attempt</span>
          <strong>{human(data.last_attempt_status)}</strong>
          <small>{timestamp(data.last_attempt_at)}</small>
        </article>
        <article>
          <span>Failed checks</span>
          <strong>{data.checks.reduce((n, c) => n + c.failures, 0)}</strong>
          <small>Latest pipeline run</small>
        </article>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Publication details</h2>
            <p>
              The last successful release remains available during a failed
              refresh.
            </p>
          </div>
          <span className="pill">Read only</span>
        </div>
        <dl className="publication">
          <div>
            <dt>Data as of</dt>
            <dd>{timestamp(data.active_as_of)}</dd>
          </div>
          <div>
            <dt>Published</dt>
            <dd>{timestamp(data.published_at)}</dd>
          </div>
          <div>
            <dt>Release</dt>
            <dd>{data.active_release_id || "Not published"}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>{data.run_id || "No run yet"}</dd>
          </div>
        </dl>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Quality checks</h2>
            <p>Results from the latest attempted run.</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Layer</th>
                <th>Check</th>
                <th>Failures</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {data.checks.map((c) => (
                <tr key={c.layer + c.check_name}>
                  <td>
                    <span className="pill">{c.layer}</span>
                  </td>
                  <td>{human(c.check_name)}</td>
                  <td>{c.failures}</td>
                  <td>
                    <span
                      className={
                        "status " + (c.failures ? "warning" : "success")
                      }
                    >
                      {c.failures ? "Attention" : "Passed"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.checks.length && (
            <p className="empty">
              No check results were recorded for this run.
            </p>
          )}
        </div>
      </section>
    </>
  );
}
function Explorer({
  workspace,
  user,
  login,
}: {
  workspace: Workspace;
  user: User;
  login: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [currency, setCurrency] = useState("");
  const [sort, setSort] = useState("default");
  const [direction, setDirection] = useState("asc");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [index, setIndex] = useState(0);
  const [reload, setReload] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(
    null,
  );
  const dialog = useRef<HTMLDialogElement>(null);
  const config = meta[workspace];
  function reset() {
    setCursors([null]);
    setIndex(0);
    setReload((n) => n + 1);
  }
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setPage(null);
    setHealth(null);
    const params = new URLSearchParams({ q, sort, direction, limit: "25" });
    if (currency) params.set("currency", currency);
    if (cursors[index]) params.set("cursor", cursors[index]!);
    const load =
      workspace === "health"
        ? get<Health>(
            "/api/v1/data-health",
            new URLSearchParams(),
            controller.signal,
          ).then(setHealth)
        : get<Page>(`/api/v1/${workspace}`, params, controller.signal).then(
            setPage,
          );
    void load
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e : new Error("Unable to load data."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [workspace, q, currency, sort, direction, index, cursors, reload]);
  useEffect(() => {
    if (selected) dialog.current?.showModal();
  }, [selected]);
  function filter(e: FormEvent) {
    e.preventDefault();
    setQ(draft.trim());
    reset();
  }
  function cell(key: string, row: Record<string, unknown>) {
    const value = row[key];
    if (
      [
        "total_settled_receipts_amt",
        "active_current_term_amt",
        "settled_amount",
      ].includes(key)
    )
      return <span className="money">{money(value, row.currency)}</span>;
    if (key === "claim_status_cd")
      return (
        <span
          className={"status " + (value === "PAID" ? "success" : "neutral")}
        >
          {human(value)}
        </span>
      );
    return human(value);
  }
  return (
    <>
      <header className="page-title">
        <div>
          <p className="eyebrow">{config.eyebrow}</p>
          <h1>{config.title}</h1>
          <p>{config.subtitle}</p>
        </div>
        <button className="button secondary" onClick={reset} disabled={loading}>
          <span aria-hidden="true">↻</span> Refresh
        </button>
      </header>
      {error && <ErrorBox error={error} retry={reset} login={login} />}
      {workspace !== "health" && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Published records</h2>
              <p>{config.grain}</p>
            </div>
            <span className="pill">
              <span className="dot" /> Read only
            </span>
          </div>
          <form className="filters" onSubmit={filter}>
            <label className="search">
              <span aria-hidden="true">⌕</span>
              <input
                aria-label="Search records"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={
                  workspace === "customers"
                    ? "Search customers or territories…"
                    : workspace === "policies"
                      ? "Search product groups…"
                      : "Search claims, status or business line…"
                }
                maxLength={100}
              />
            </label>
            <button className="button primary" type="submit">
              Search
            </button>
            <label className="filter-label">
              Currency
              <select
                aria-label="Currency"
                value={currency}
                onChange={(e) => {
                  setCurrency(e.target.value);
                  reset();
                }}
              >
                <option value="">All currencies</option>
                <option>USD</option>
                <option>EUR</option>
                <option>GBP</option>
                <option>PLN</option>
              </select>
            </label>
            <label className="filter-label">
              Sort by
              <select
                aria-label="Sort by"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value);
                  reset();
                }}
              >
                {config.sorts.map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="direction"
              aria-label={
                direction === "asc" ? "Sort descending" : "Sort ascending"
              }
              onClick={() => {
                setDirection(direction === "asc" ? "desc" : "asc");
                reset();
              }}
              disabled={sort === "default"}
            >
              {direction === "asc" ? "↑" : "↓"}
            </button>
          </form>
          {loading ? (
            <div className="loading" role="status">
              <span className="spinner" /> Loading curated records…
            </div>
          ) : (
            page && (
              <>
                <div className="release-strip">
                  <span>
                    <span
                      className={"dot " + (page.stale ? "amber-dot" : "")}
                    />{" "}
                    {page.stale ? "Data may be out of date" : "Published data"}{" "}
                    <span className="muted">
                      · As of {timestamp(page.as_of)}
                    </span>
                  </span>
                  <span>{page.items.length} rows on this page</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {columns[workspace].map(([k, v]) => (
                          <th key={k}>{v}</th>
                        ))}
                        <th>
                          <span className="sr-only">Details</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((item, i) => {
                        const row = item as unknown as Record<string, unknown>;
                        return (
                          <tr key={i}>
                            {columns[workspace].map(([k], j) => (
                              <td key={k}>
                                {j === 0 ? (
                                  <div className="primary-cell">
                                    {workspace === "customers" && (
                                      <span className="avatar">
                                        {String(row.full_name || "?").slice(
                                          0,
                                          1,
                                        )}
                                      </span>
                                    )}
                                    <span>
                                      <strong>{cell(k, row)}</strong>
                                      {workspace === "customers" && (
                                        <small>{String(row.customer_sk)}</small>
                                      )}
                                    </span>
                                  </div>
                                ) : (
                                  cell(k, row)
                                )}
                              </td>
                            ))}
                            <td>
                              <button
                                className="text-button"
                                aria-label={`View details for ${String(row[columns[workspace][0][0]])}`}
                                onClick={() => setSelected(row)}
                              >
                                Details <span aria-hidden="true">↗</span>
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {!page.items.length && (
                    <div className="empty">
                      <span aria-hidden="true">⌕</span>
                      <h3>No matching records</h3>
                      <p>Try another search or currency.</p>
                      <button
                        className="button secondary"
                        onClick={() => {
                          setDraft("");
                          setQ("");
                          setCurrency("");
                          reset();
                        }}
                      >
                        Clear filters
                      </button>
                    </div>
                  )}
                </div>
                <footer className="pagination">
                  <span>
                    Page {index + 1}{" "}
                    <span className="muted">· {user.tenant}</span>
                  </span>
                  <div>
                    <button
                      className="button secondary"
                      disabled={!index}
                      onClick={() => setIndex((n) => n - 1)}
                    >
                      ← Previous
                    </button>
                    <button
                      className="button secondary"
                      disabled={!page.next_cursor}
                      onClick={() => {
                        setCursors((c) => [
                          ...c.slice(0, index + 1),
                          page.next_cursor,
                        ]);
                        setIndex((n) => n + 1);
                      }}
                    >
                      Next →
                    </button>
                  </div>
                </footer>
              </>
            )
          )}
        </section>
      )}
      {workspace === "health" &&
        (loading ? (
          <div className="loading" role="status">
            <span className="spinner" /> Checking publication status…
          </div>
        ) : (
          health && <DataHealth data={health} />
        ))}
      <p className="footnote">
        {workspace === "policies"
          ? "Portfolio totals are grouped by product and currency. These rows are not individual policies."
          : workspace === "claims"
            ? "Payment timing measures days to the last payment; it does not indicate claim closure."
            : workspace === "customers"
              ? "A customer with receipts in multiple currencies appears once for each currency."
              : "Freshness measures source age, including ingestion and transformation time."}
      </p>
      {selected && (
        <dialog
          className="detail-dialog"
          ref={dialog}
          onCancel={() => setSelected(null)}
          onClick={(e) => {
            if (e.target === dialog.current) {
              dialog.current.close();
              setSelected(null);
            }
          }}
        >
          <div className="dialog-heading">
            <div>
              <p className="eyebrow">PUBLISHED RECORD</p>
              <h2>Record details</h2>
            </div>
            <button
              className="icon-button"
              aria-label="Close details"
              onClick={() => {
                dialog.current?.close();
                setSelected(null);
              }}
            >
              ×
            </button>
          </div>
          <dl>
            {Object.entries(selected).map(([key, val]) => (
              <div key={key}>
                <dt>{human(key)}</dt>
                <dd>{human(val)}</dd>
              </div>
            ))}
          </dl>
          <p className="footnote">
            Values reflect the selected publication. This view is read only.
          </p>
        </dialog>
      )}
    </>
  );
}
export default function App() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>("customers");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void (async () => {
      try {
        const response = await fetch("/api/v1/config", {
          signal: AbortSignal.timeout(10000),
        });
        if (!response.ok)
          throw new Error("Application configuration is unavailable.");
        const c = (await response.json()) as RuntimeConfig;
        setConfig(c);
        setupAuth(c);
        initTelemetry(c.telemetry_sample_ratio);
        await callback();
        if (await token()) {
          const u = await get<User>("/api/v1/me");
          setUser(u);
          setWorkspace(u.capabilities[0]);
        }
      } catch (e) {
        setError(
          e instanceof Error
            ? e
            : new Error("Unable to initialize the application."),
        );
      }
    })();
  }, []);
  async function login() {
    if (!config) return;
    setError(null);
    setBusy(true);
    try {
      await signIn(config.demo);
      if (config.demo) {
        const u = await get<User>("/api/v1/me");
        setUser(u);
        setWorkspace(
          u.capabilities.includes("customers")
            ? "customers"
            : u.capabilities[0],
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Sign-in failed."));
    } finally {
      setBusy(false);
    }
  }
  if (!user)
    return (
      <main className="login">
        <section className="login-story">
          <div className="brand">
            <Mark />
            <span>omniclaim</span>
          </div>
          <p className="eyebrow">CURATED EXPLORER</p>
          <h1>
            Insurance data.
            <br />A clearer perspective.
          </h1>
          <p>
            Explore your published customer, policy and claims data in one
            trusted workspace.
          </p>
          <div className="login-grid">
            <div>
              <span>01</span>
              <strong>Understand relationships</strong>
            </div>
            <div>
              <span>02</span>
              <strong>Explore your portfolio</strong>
            </div>
            <div>
              <span>03</span>
              <strong>See the data behind it</strong>
            </div>
          </div>
          <small>CONTROLLED ACCESS · PUBLISHED DATA · READ ONLY</small>
        </section>
        <section className="login-action">
          <div className="login-card">
            <span className="pill">OmniClaim workspace</span>
            <h2>Welcome back.</h2>
            <p>Sign in to access the views assigned to your role.</p>
            {config?.demo && (
              <div className="demo-note">
                <strong>Local demonstration</strong>
                <p>
                  This workspace uses synthetic records. No customer system is
                  connected.
                </p>
              </div>
            )}
            {error && (
              <p role="alert" className="login-error">
                {error.message}
              </p>
            )}
            <button
              className="button primary"
              onClick={() => void login()}
              disabled={!config || busy}
            >
              {busy
                ? "Connecting…"
                : config?.demo
                  ? "Explore demo workspace →"
                  : "Sign in with your organization →"}
            </button>
            <small>
              Your organization controls access to each data workspace.
            </small>
          </div>
        </section>
      </main>
    );
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Mark />
          <span>
            omniclaim<small>CURATED EXPLORER</small>
          </span>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {(Object.keys(meta) as Workspace[])
            .filter((w) => user.capabilities.includes(w))
            .map((w) => (
              <button
                key={w}
                className={workspace === w ? "active" : ""}
                onClick={() => setWorkspace(w)}
                aria-current={workspace === w ? "page" : undefined}
              >
                <span aria-hidden="true">{meta[w].icon}</span>
                {meta[w].title}
              </button>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="sidebar-emblem">◈</span>
          <strong>Built on published data</strong>
          <p>Every view reflects a curated, successful release.</p>
          <div className="profile">
            <span className="avatar">{user.tenant[0].toUpperCase()}</span>
            <div>
              <strong>{user.tenant}</strong>
              <small>Authorized workspace</small>
            </div>
            <button
              aria-label="Sign out"
              title="Sign out"
              onClick={() => void signOut().then(() => setUser(null))}
            >
              ↪
            </button>
          </div>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <span>
            Workspace <span className="breadcrumb">/</span>{" "}
            <strong>{meta[workspace].title}</strong>
          </span>
          <div>
            <span className="secure-label">
              <span className="dot" /> Controlled access
            </span>
            <span className="top-avatar">
              {user.tenant.slice(0, 2).toUpperCase()}
            </span>
          </div>
        </header>
        {config?.demo && (
          <div className="demo-banner">
            <strong>DEMO WORKSPACE</strong>
            <span>Synthetic records · for local exploration</span>
          </div>
        )}
        <main className="main-content">
          <Explorer
            key={workspace}
            workspace={workspace}
            user={user}
            login={() => void login()}
          />
        </main>
        <footer className="app-footer">
          <span>OmniClaim · Curated Explorer</span>
          <span>Published data. Clear context.</span>
        </footer>
      </div>
    </div>
  );
}
