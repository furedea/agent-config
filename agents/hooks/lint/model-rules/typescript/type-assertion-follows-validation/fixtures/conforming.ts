/** Conforming cases for the type-assertion-follows-validation eval; labels are in ../expect.yml. Never imported or run. */

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

export function parseEmail(value: string): Email | undefined {
  if (!value.includes("@")) {
    return undefined;
  }
  return value as Email;
}

export function parsePort(text: string): Port | undefined {
  const port = Number(text);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return undefined;
  }
  return port as Port;
}

export function toUser(value: unknown): User | undefined {
  if (!isUser(value)) {
    return undefined;
  }
  return value as User;
}

export function erase(order: Order): unknown {
  return order as unknown;
}
