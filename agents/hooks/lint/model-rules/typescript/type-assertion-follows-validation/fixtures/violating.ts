/** Violating cases for the type-assertion-follows-validation eval; labels are in ../expect.yml. Never imported or run. */

interface User {
  readonly id: string;
  readonly name: string;
}

interface Order {
  readonly id: string;
  readonly total: number;
}

type Email = string & { readonly __brand: "Email" };
type Port = number & { readonly __brand: "Port" };

function isUser(value: unknown): value is User {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "name" in value &&
    typeof value.name === "string"
  );
}

export function loadOrder(text: string): Order {
  return JSON.parse(text) as Order;
}

export function userOf(payload: any): User {
  const user = payload as User;
  return user;
}

export async function fetchOrders(url: string): Promise<readonly Order[]> {
  const response = await fetch(url);
  return (await response.json()) as Order[];
}

export function asUser(value: unknown): User {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("read user: the value is not an object");
  }
  return value as User;
}
