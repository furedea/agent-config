/** Conforming cases for the known-defect-marker-names-removal eval; labels are in ../expect.yml. Never imported or run. */

// Remove when the parser accepts an empty document (#123).
test.fails("parses an empty document", () => {
  expect(parse("")).toEqual([]);
});

// Passes once vitest ships the fake-timer fix (vitest-dev/vitest#7001); remove the marker then.
it.fails("advances timers inside a microtask", async () => {
  await expect(tick()).resolves.toBe(1);
});

// Expected to fail until the CSV importer supports quoted newlines; delete the marker in that change.
test.fails("imports a quoted newline", () => {
  expect(importCsv('"a\nb"')).toEqual([["a\nb"]]);
});

it.fails("sorts by locale", () => { // remove when #45 (locale-aware sort) is fixed
  expect(sortNames(["b", "a"])).toEqual(["a", "b"]);
});
