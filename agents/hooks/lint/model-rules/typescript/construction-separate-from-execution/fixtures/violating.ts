/** Violating cases for the construction-separate-from-execution eval; labels are in ../expect.yml. Never imported or run. */

export async function syncInvoices(accountId: string): Promise<number> {
  const client = new BillingClient({ apiKey: process.env.BILLING_KEY ?? "", timeoutMs: 5000, retries: 3 });
  const invoices = await client.listInvoices(accountId);
  let overdue = 0;
  for (const invoice of invoices) {
    if (invoice.dueAt < invoice.checkedAt && !invoice.paid) {
      await client.remind(invoice.id);
      overdue += 1;
    }
  }
  return overdue;
}

export class ReportJob {
  async run(month: string): Promise<string> {
    const connection = new PostgresConnection({ host: "db.internal", port: 5432, user: "report" });
    await connection.open();
    const rows = await connection.query("select region, sum(total) from sales where month = $1 group by region", [month]);
    return rows.map((row) => `${row.region}: ${row.sum}`).join("\n");
  }
}

export const importUsers = async (csv: string): Promise<number> => {
  const repository = new UserRepository(new Pool({ connectionString: process.env.DATABASE_URL, max: 4 }));
  let imported = 0;
  for (const line of csv.split("\n").slice(1)) {
    const [email, name] = line.split(",");
    if (email && name) {
      await repository.save({ email, name });
      imported += 1;
    }
  }
  return imported;
};

export async function sendWelcome(user: { readonly email: string; readonly plan: string }): Promise<void> {
  const mail = new SmtpClient({ host: "smtp.example.com", port: 587, auth: { user: "app", pass: process.env.SMTP_PASS ?? "" } });
  const subject = user.plan === "pro" ? "Welcome to Pro" : "Welcome";
  await mail.send({ to: user.email, subject, body: `Your plan: ${user.plan}` });
}
