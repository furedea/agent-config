/** Conforming cases for the function-single-purpose eval; labels are in ../expect.yml. Never imported or run. */

export async function checkout(cart: Cart, payment: Payment, mailer: Mailer): Promise<Receipt> {
  const order = priceOrder(cart);
  const charge = await payment.charge(order.total);
  const receipt = issueReceipt(order, charge);
  await mailer.sendReceipt(receipt);
  return receipt;
}

export function formatMoney(cents: number, currency: string): string {
  const sign = cents < 0 ? "-" : "";
  const whole = Math.floor(Math.abs(cents) / 100);
  const fraction = String(Math.abs(cents) % 100).padStart(2, "0");
  return `${sign}${currency} ${whole.toLocaleString("en-US")}.${fraction}`;
}

export function normalizeAddress(address: Address): Address {
  const street = address.street.trim().replace(/\s+/g, " ");
  const city = address.city.trim().toUpperCase();
  const postalCode = address.postalCode.replace(/\s/g, "").toUpperCase();
  const country = address.country.trim().toUpperCase();
  return { street, city, postalCode, country };
}

export const readJson = (path: string): unknown => parseJson(readText(path));
