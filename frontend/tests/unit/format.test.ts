import { describe, it, expect } from "vitest";
import { money, human } from "../../src/format";
describe("financial formatting", () => {
  it("keeps decimal precision above the JS safe integer limit", () =>
    expect(money("9007199254740993.17", "USD")).toBe(
      "USD 9,007,199,254,740,993.17",
    ));
  it("preserves signed refunds", () =>
    expect(money("-1234.50", "EUR")).toBe("EUR -1,234.50"));
  it("does not invent a currency", () =>
    expect(money("0", null)).toBe("Unassigned currency 0.00"));
  it("handles absent values", () => expect(money(null, "USD")).toBe("—"));
  it("renders domain status", () =>
    expect(human("UNDER_REVIEW")).toBe("UNDER REVIEW"));
});
