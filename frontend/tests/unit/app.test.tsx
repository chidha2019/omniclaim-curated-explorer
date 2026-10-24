import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../../src/App";
import { signOut } from "../../src/auth";
vi.mock("../../src/telemetry", () => ({
  initTelemetry: vi.fn(),
  requestSpan: vi.fn(),
}));
const fetchMock = vi.fn();
const customer = {
  customer_sk: "customer-1",
  full_name: "Avery Morgan",
  client_category_cd: "HNW",
  primary_territory: "New York",
  currency: "USD",
  total_settled_receipts_amt: "12000.50",
};
let mode = "ok";
beforeEach(async () => {
  await signOut();
  mode = "ok";
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockImplementation(async (input: string) => {
    if (input === "/api/v1/config")
      return new Response(
        JSON.stringify({
          demo: true,
          version: "test",
          telemetry_sample_ratio: 0,
        }),
      );
    if (input === "/api/v1/me")
      return new Response(
        JSON.stringify({
          tenant: "demo",
          capabilities: ["customers", "policies", "claims", "health"],
        }),
      );
    if (mode === "error")
      return new Response(
        JSON.stringify({
          code: "publication_changed",
          message: "A new data release is available.",
        }),
        { status: 409 },
      );
    const rows = String(input).includes("q=missing") ? [] : [customer];
    return new Response(
      JSON.stringify({
        items: rows,
        next_cursor: null,
        release_id: "r1",
        as_of: "2026-10-24T12:00:00Z",
        stale: mode === "stale",
      }),
    );
  });
});
async function enter() {
  render(<App />);
  const btn = await screen.findByRole("button", { name: /Explore demo/ });
  fireEvent.click(btn);
  await screen.findByText("Avery Morgan");
}
it("browses data and opens record detail", async () => {
  await enter();
  expect(screen.getByText("USD 12,000.50")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /View details for/ }));
  expect(screen.getByRole("dialog")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Close details" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
it("submits literal filters and handles empty results", async () => {
  await enter();
  fireEvent.change(screen.getByRole("textbox", { name: "Search records" }), {
    target: { value: "missing" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await screen.findByText("No matching records");
  expect(
    fetchMock.mock.calls.some(([u]) => String(u).includes("q=missing")),
  ).toBe(true);
});
it("shows publication changes with refresh action", async () => {
  await enter();
  mode = "error";
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByRole("alert");
  expect(screen.getByText("A new release is ready")).toBeVisible();
  mode = "ok";
  fireEvent.click(screen.getByRole("button", { name: "Refresh view" }));
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
});
it("labels stale publications", async () => {
  mode = "stale";
  await enter();
  expect(screen.getByText("Data may be out of date")).toBeVisible();
});
