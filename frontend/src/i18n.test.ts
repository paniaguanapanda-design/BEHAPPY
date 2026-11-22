import { describe, expect, it } from "@jest/globals";
import { CATEGORIES, SUBTRADES, dict } from "./i18n";

const LANGS = ["es", "it", "en"] as const;
const placeholders = (text: string) => (text.match(/\{[a-z_]+\}/g) ?? []).sort();

describe("translations", () => {
  it("use the same {placeholders} in every language", () => {
    const wrong: string[] = [];
    for (const key of Object.keys(dict.es) as (keyof typeof dict.es)[]) {
      const expected = placeholders(String(dict.es[key]));
      for (const lang of LANGS) {
        const got = placeholders(String(dict[lang][key]));
        if (got.join() !== expected.join()) wrong.push(`${lang}.${key}: ${got.join()} (es: ${expected.join()})`);
      }
    }
    expect(wrong).toEqual([]);
  });

  it("have no empty texts", () => {
    const empty = LANGS.flatMap((lang) =>
      Object.entries(dict[lang]).filter(([, v]) => String(v).trim() === "").map(([k]) => `${lang}.${k}`),
    );
    expect(empty).toEqual([]);
  });

  // Keys built at runtime, like t(`cat_${category}`): TypeScript cannot check these.
  const dynamicKeys = [
    ...CATEGORIES.map((c) => `cat_${c}`),
    ...Object.values(SUBTRADES).flat().map((s) => `sub_${s}`),
    ...["reposition", "repair", "replace", "inspect"].map((a) => `act_${a}`), // backend: ACTIONS in diagnosis.py
    ...["open", "accepted", "completed", "cancelled"].map((s) => `request_status_${s}`),
    ...["pending", "accepted", "rejected"].map((s) => `qs_${s}`),
    "time_now",
    "time_minutes_ago",
    "time_hours_ago",
    "time_days_ago",
  ];

  it.each(LANGS)("include every key built at runtime (%s)", (lang) => {
    const missing = dynamicKeys.filter((k) => !(k in dict[lang]));
    expect(missing).toEqual([]);
  });
});
