/** Conforming cases for the repeated-cases-use-it-each eval; labels are in ../expect.yml. Never imported or run. */

it("starts empty", () => {
  expect(new Cart().items()).toEqual([]);
});
it("rejects a negative quantity", () => {
  expect(() => new Cart().add("a", -1)).toThrow(RangeError);
});

describe("Cart", () => {
  it("adds an item", () => {
    const cart = new Cart();
    cart.add("a", 1);
    expect(cart.items()).toEqual([{ sku: "a", quantity: 1 }]);
  });
  it("merges the same item", () => {
    const cart = new Cart();
    cart.add("a", 1);
    cart.add("a", 2);
    expect(cart.items()).toEqual([{ sku: "a", quantity: 3 }]);
  });
  it("totals with the price list", () => {
    const cart = new Cart();
    cart.add("a", 2);
    expect(cart.total(new Map([["a", 150]]))).toBe(300);
  });
});

describe("slugify", () => {
  it.each([
    ["Hello", "hello"],
    ["hello world", "hello-world"],
    ["hello, world!", "hello-world"],
  ])("slugifies %s", (input, expected) => {
    expect(slugify(input)).toBe(expected);
  });
});

suite("retry", () => {
  test("returns the first success", async () => {
    const work = vi.fn().mockRejectedValueOnce(new Error("busy")).mockResolvedValue("ok");
    await expect(retry(work, 3)).resolves.toBe("ok");
  });
  test("gives up after the last attempt", async () => {
    const work = vi.fn().mockRejectedValue(new Error("busy"));
    await expect(retry(work, 2)).rejects.toThrow("busy");
    expect(work).toHaveBeenCalledTimes(2);
  });
});
