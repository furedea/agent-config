/** Conforming cases for the construction-separate-from-execution eval; labels are in ../expect.yml. Never imported or run. */

export function createApp(env: Readonly<Record<string, string>>): App {
  const billing = new BillingClient({ apiKey: env.BILLING_KEY ?? "", timeoutMs: 5000, retries: 3 });
  const invoices = new InvoiceRepository(new Pool({ connectionString: env.DATABASE_URL }));
  return new App(billing, invoices);
}

export function buildServer(routes: readonly Route[]): HttpServer {
  const server = new HttpServer({ keepAliveMs: 5000 });
  for (const route of routes) {
    server.route(route.path, route.handle);
  }
  return server;
}

export class Api {
  constructor(private readonly client: HttpClient) {}

  static fromEnv(env: Readonly<Record<string, string>>): Api {
    return new Api(new HttpClient({ baseUrl: env.API_URL ?? "http://localhost" }));
  }
}

export function countRows(text: string): number {
  const reader = new LineReader(text);
  let rows = 0;
  while (reader.next() !== undefined) {
    rows += 1;
  }
  return rows;
}
