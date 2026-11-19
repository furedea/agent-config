/** Violating cases for the angle-bracket-assertion-follows-validation eval; labels are in ../expect.yml. Never imported or run. */

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
  return <Order>JSON.parse(text);
}

export function userOf(payload: any): User {
  const user = <User>payload;
  return user;
}

export function ordersOf(body: unknown): readonly Order[] {
  return <Order[]>body;
}

export function asUser(value: unknown): User {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("read user: the value is not an object");
  }
  return <User>value;
}
