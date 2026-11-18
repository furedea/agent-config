/** Conforming cases for the no-reaching-through-collaborators eval; labels are in ../expect.yml. Never imported or run. */

export function nodeMajor(): number {
  return Number(process.versions.node.split(".")[0]);
}

export function itemIds(event: { readonly detail: { readonly payload: { readonly items: readonly Item[] } } }): string[] {
  return event.detail.payload.items.map((item) => item.id);
}

export class Basket {
  private readonly state = { items: [] as Item[] };

  add(item: Item): void {
    this.state.items.push(item);
  }
}

export async function digest(bytes: Uint8Array): Promise<ArrayBuffer> {
  return globalThis.crypto.subtle.digest("SHA-256", bytes);
}
