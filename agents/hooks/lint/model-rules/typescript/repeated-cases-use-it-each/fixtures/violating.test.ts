/** Violating cases for the repeated-cases-use-it-each eval; labels are in ../expect.yml. Never imported or run. */

describe("slugify", () => {
  it("lowercases words", () => {
    expect(slugify("Hello")).toBe("hello");
  });
  it("joins words with a dash", () => {
    expect(slugify("hello world")).toBe("hello-world");
  });
  it("drops punctuation", () => {
    expect(slugify("hello, world!")).toBe("hello-world");
  });
  it("trims spaces", () => {
    expect(slugify("  hello  ")).toBe("hello");
  });
});

describe("parsePort", () => {
  it("rejects zero", () => {
    expect(parsePort("0")).toBeUndefined();
  });
  it("rejects a port above 65535", () => {
    expect(parsePort("65536")).toBeUndefined();
  });
  it("rejects text", () => {
    expect(parsePort("http")).toBeUndefined();
  });
});

suite("formatMoney", () => {
  test("formats whole amounts", () => {
    expect(formatMoney(500, "USD")).toBe("USD 5.00");
  });
  test("formats cents", () => {
    expect(formatMoney(507, "USD")).toBe("USD 5.07");
  });
  test("formats negative amounts", () => {
    expect(formatMoney(-507, "USD")).toBe("-USD 5.07");
  });
});

describe("isWeekend", () => {
  it("is true on Saturday", () => {
    expect(isWeekend(new Date("2026-11-21"))).toBe(true);
  });
  it("is true on Sunday", () => {
    expect(isWeekend(new Date("2026-11-22"))).toBe(true);
  });
  it("rejects an invalid date", () => {
    expect(() => isWeekend(new Date("nope"))).toThrow(RangeError);
  });
});
