import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { formatPrice, relativeTime } from "./format";

// Fake translator: returns the key with {n} filled in, so the tests can check which text was chosen.
const t = (key: string) => key;

describe("relativeTime", () => {
  const NOW = new Date("2026-11-22T12:00:00Z").getTime();
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(NOW);
  });
  afterEach(() => {
    jest.useRealTimers();
  });
  const ago = (ms: number) => new Date(NOW - ms).toISOString();

  it("says 'now' under one minute", () => {
    expect(relativeTime(ago(30_000), t)).toBe("time_now");
  });

  it("uses minutes under one hour", () => {
    expect(relativeTime(ago(5 * 60_000), t)).toBe("time_minutes_ago");
  });

  it("uses hours under one day", () => {
    expect(relativeTime(ago(3 * 3_600_000), t)).toBe("time_hours_ago");
  });

  it("uses days from 24 hours on", () => {
    expect(relativeTime(ago(2 * 86_400_000), t)).toBe("time_days_ago");
  });

  it("puts the number in the text", () => {
    const withN = (key: string) => (key === "time_minutes_ago" ? "{n} min" : key);
    expect(relativeTime(ago(7 * 60_000), withN)).toBe("7 min");
  });

  it("treats a date in the future (clock skew) as 'now'", () => {
    expect(relativeTime(new Date(NOW + 60_000).toISOString(), t)).toBe("time_now");
  });
});

describe("formatPrice", () => {
  // Intl may use a narrow no-break space before the euro sign: compare without spaces.
  const plain = (s: string) => s.replace(/\s/g, "");

  it("formats euros in Italian", () => {
    expect(plain(formatPrice(1234.5, "it"))).toBe("1234,50€");
  });

  it("formats euros in Spanish", () => {
    expect(plain(formatPrice(80, "es"))).toBe("80,00€");
  });

  it("falls back to Spanish format for English", () => {
    expect(formatPrice(80, "en")).toBe(formatPrice(80, "es"));
  });
});
