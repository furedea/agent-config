/** Violating cases for the mock-only-external-boundaries eval; labels are in ../expect.yml. Never imported or run. */

vi.mock("./pricing");

it("charges the cart total", async () => {
  const cart = new Cart([{ sku: "a", cents: 500 }]);
  vi.spyOn(cart, "total").mockReturnValue(700);
  await checkout(cart, payments);
  expect(payments.charged).toEqual([700]);
});

vi.mock("../src/repository", () => ({ findUser: vi.fn(async () => ({ id: "u1" })) }));

it("renders the label", async () => {
  vi.doMock("./format", () => ({ formatMoney: () => "$7.00" }));
  const { label } = await import("./label");
  expect(label(700)).toBe("Total: $7.00");
});
