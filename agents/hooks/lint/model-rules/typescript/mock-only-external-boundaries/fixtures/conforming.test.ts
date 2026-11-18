/** Conforming cases for the mock-only-external-boundaries eval; labels are in ../expect.yml. Never imported or run. */

vi.mock("node:fs/promises");

vi.mock("@aws-sdk/client-s3", () => ({ S3Client: vi.fn(() => ({ send: vi.fn() })) }));

it("reads the status", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok"));
  await expect(status("https://example.com")).resolves.toBe("ok");
});

it("reports a bad line", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  readLines("a\n\u0000");
  expect(error).toHaveBeenCalledOnce();
});
