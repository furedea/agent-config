/** Violating cases for the comment-explains-why eval; labels are in ../expect.yml. Never imported or run. */

export function total(prices: readonly number[]): number {
  // start at zero
  let sum = 0;
  // loop over the prices
  for (const price of prices) {
    // add the price
    sum += price;
  }
  return sum;
}

export function shippable(order: { readonly weightGrams: number; readonly country: string }): boolean {
  // check that the order is light enough and goes to a country we ship to
  return order.weightGrams <= 30000 && ["JP", "US", "DE"].includes(order.country);
}

// the default page size is 50
export const DEFAULT_PAGE_SIZE = 50;

export const names = (users: readonly { readonly name: string }[]): string[] =>
  users.map((user) => {
    // return the name of the user
    return user.name;
  });
