export function money(value: unknown, currency: unknown): string {
  if (value === null || value === undefined) return "—";
  const text = String(value);
  // Keep Snowflake DECIMAL values as strings, including values above JS's safe integer range.
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(text);
  if (!m) return "—";
  const number =
    m[1] +
    m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    "." +
    (m[3] ?? "").padEnd(2, "0");
  return `${currency || "Unassigned currency"} ${number}`;
}
export function timestamp(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Not published";
}
export function human(value: unknown): string {
  return value === null || value === undefined
    ? "—"
    : String(value).replaceAll("_", " ");
}
