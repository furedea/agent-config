/** Violating cases for the no-reaching-through-collaborators eval; labels are in ../expect.yml. Never imported or run. */

export function cityOf(order: Order): string {
  return order.customer.address.city.toUpperCase();
}

export async function remindOwner(invoice: Invoice): Promise<void> {
  await invoice.account.owner.notify(`invoice ${invoice.id} is overdue`);
}

export const shippingCost = (cart: Cart): number => cart.store.warehouse.rates.lookup(cart.weightGrams);

export class SignupHandler {
  async handle(context: Context, email: string): Promise<void> {
    await context.app.services.mailer.send(email, "welcome");
  }
}

export function canRetry(worker: Worker): boolean {
  return worker.client.transport.policy.maxRetries > 0;
}
