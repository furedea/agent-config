/** Violating cases for the known-defect-marker-names-removal eval; labels are in ../expect.yml. Never imported or run. */

test.fails("parses an empty document", () => {
  expect(parse("")).toEqual([]);
});

// broken
it.fails("keeps the order of duplicate keys", () => {
  expect(merge({ a: 1 }, { a: 2 })).toEqual({ a: 2 });
});

// TODO: fix later
test.fails("rounds half to even", () => {
  expect(round(2.5)).toBe(2);
});

// Flaky on CI.
it.fails("retries after a timeout", async () => {
  await expect(fetchWithRetry("http://localhost:1")).resolves.toBeDefined();
});
