/** Violating cases for the expected-failure-returned-as-value eval; labels are in ../expect.yml. Never imported or run. */

export function findUser(users: ReadonlyMap<string, User>, id: string): User {
  const user = users.get(id);
  if (user === undefined) {
    throw new Error(`find user ${id}: not found`);
  }
  return user;
}

export function parseAge(text: string): number {
  const age = Number.parseInt(text, 10);
  if (Number.isNaN(age) || age < 0 || age > 150) {
    throw new RangeError(`parse age: "${text}" is not an age`);
  }
  return age;
}

export const lookupPrice = (catalog: ReadonlyMap<string, number>, sku: string): Promise<number> => {
  const price = catalog.get(sku);
  return price === undefined ? Promise.reject(new Error(`look up price ${sku}: unknown SKU`)) : Promise.resolve(price);
};

export class Inventory {
  private readonly stock = new Map<string, number>();

  reserve(sku: string, quantity: number): void {
    const available = this.stock.get(sku) ?? 0;
    if (available < quantity) {
      throw new Error(`reserve ${sku}: only ${available} left`);
    }
    this.stock.set(sku, available - quantity);
  }
}
