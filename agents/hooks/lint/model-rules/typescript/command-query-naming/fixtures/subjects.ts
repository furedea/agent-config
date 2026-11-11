// Subjects for the command-query-naming eval; labels are in ../expect.yml. Never imported or run.

const callLog: string[] = [];
const ports = new Map<string, number>();

// Clean: "check" promises neither a pure read nor an effect, and the body does both.
export function checkPaths(
  mode: string,
  payload: Payload,
  rules: Rule[],
  auditLog: AuditLog,
): number {
  const context = normalized(payload);
  for (const value of candidatesOf(mode, context)) {
    const rule = blockedRule(value, rules);
    if (rule) {
      auditLog.blocked(refusal(mode, value, context));
      throw new Error(reasonFor(value, rule));
    }
  }
  return 0;
}

// Clean: "judge" promises neither a pure read nor an effect.
export class Review {
  constructor(private readonly cache: string) {}

  judge(plan: Plan, deadline: Deadline): Judgement {
    const output = withLock(this.cache, () => runChild(plan.args, deadline.remaining(60)));
    return parseJudgement(output, plan);
  }
}

// Clean: a command that returns the result of its own effect.
export function saveReport(path: string, report: Report): number {
  const text = JSON.stringify(report);
  writeFileSync(path, text);
  return text.length;
}

// Clean: a memoizing query writes only its own cache.
export function getPort(name: string): number {
  if (!ports.has(name)) {
    ports.set(name, Number(process.env[`${name.toUpperCase()}_PORT`]));
  }
  return ports.get(name) as number;
}

// Clean: a pure lookup named as one.
export function findOwner(repositories: Repository[], name: string): string | undefined {
  return repositories.find((repository) => repository.name === name)?.owner;
}

// Clean: a conventional terse name that the body fits.
export function toSlug(title: string): string {
  return title.toLowerCase().split(/\s+/).join("-");
}

// Bad: a query name whose body appends to a module-level log.
export function getUserCount(users: User[]): number {
  callLog.push("getUserCount");
  return users.length;
}

// Bad: a command name whose body only computes a value the caller needs.
export function saveTotal(prices: number[]): number {
  return prices.reduce((sum, price) => sum + price, 0);
}

// Bad: a predicate name whose body deletes a file.
export function isStale(path: string, limit: number): boolean {
  if (statSync(path).mtimeMs < limit) {
    unlinkSync(path);
    return true;
  }
  return false;
}

// Bad: a command name whose body only builds a string and performs no update.
export function updateLabel(item: Item): string {
  return `${item.name} (${item.count})`;
}

// Bad: a query name whose body empties the argument it counted.
export function countItems(items: Item[]): number {
  const total = items.length;
  items.length = 0;
  return total;
}

// Bad: a query name whose body sends a request.
export async function findUser(users: Map<string, User>, name: string): Promise<User | undefined> {
  await fetch("https://audit.example.com/lookups", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  return users.get(name);
}

// Bad: a command name whose body returns the surviving entries and deletes nothing.
export function deleteExpired(entries: Entry[], now: number): Entry[] {
  return entries.filter((entry) => entry.expiresAt > now);
}

// Bad: a command name whose body returns a converted number and sets nothing.
export function setTimeoutMs(config: Config, seconds: number): number {
  return seconds * 1000;
}

// Clean: a command that returns the results of the effects it performs.
export function runAll(tasks: Task[]): unknown[] {
  return tasks.map((task) => task.run());
}

// Clean: a pure conversion named as one.
export function toDict(user: User): Record<string, unknown> {
  return { name: user.name, count: user.count };
}
