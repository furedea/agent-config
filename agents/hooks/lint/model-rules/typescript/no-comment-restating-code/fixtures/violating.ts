/** Violating cases for the no-comment-restating-code eval; labels are in ../expect.yml. Never imported or run. */

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

export function register(form: { readonly email: string; readonly name: string }, users: Map<string, string>): void {
  // validate
  if (!form.email.includes("@")) {
    return;
  }
  // save
  users.set(form.email, form.name);
}

export const isEmpty = (count: number): boolean => {
  // return true when count is zero
  return count === 0;
};

export class Counter {
  private value = 0;

  increment(): void {
    // increase the value by one
    this.value += 1;
  }
}
