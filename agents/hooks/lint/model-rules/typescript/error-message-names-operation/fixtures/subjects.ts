// Subjects for the error-message-names-operation eval; labels are in ../expect.yml. Never imported or run.

function secretPathReason(value: string, rule: Rule): string {
  return `secret path policy matched.\n\nPath: ${value}\nPattern: ${rule.pattern}\n\nWhy:\n  ${rule.reason}`;
}

// Clean: the message is built by another function that names the operation and subject.
export function rejectSecretPath(value: string, rules: Rule[]): void {
  for (const rule of rules) {
    if (rule.matches(value)) {
      throw new Error(secretPathReason(value, rule));
    }
  }
}

// Clean: names the operation and the subject.
export function readPort(path: string): number {
  const text = readFileSync(path, "utf8");
  if (!/^\d+$/.test(text.trim())) {
    throw new Error(
      `cannot read the port from ${path}: expected digits, got ${JSON.stringify(text)}`,
    );
  }
  return Number(text);
}

// Clean: wraps a cause and names the operation and the subject.
export function loadSettings(path: string): string {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    throw new Error(`cannot load settings from ${path}`, { cause: error });
  }
}

// Clean: rethrows a caught error unchanged.
export function runStep(step: () => number): number {
  try {
    return step();
  } catch (error) {
    throw error;
  }
}

// Bad: a generic message.
export function parseCount(text: string): number {
  if (!/^\d+$/.test(text)) {
    throw new Error("invalid");
  }
  return Number(text);
}

// Bad: no message at all.
export function openSession(name: string, sessions: Map<string, Session>): Session {
  const session = sessions.get(name);
  if (!session) {
    throw new Error();
  }
  return session;
}

// Bad: names only the subject.
export function deleteRecord(recordId: string, records: Map<string, Record>): void {
  if (!records.has(recordId)) {
    throw new Error(`${recordId}`);
  }
  records.delete(recordId);
}

// Bad: names only the operation.
export function sendReport(report: Report, outbox: Outbox): void {
  if (!outbox.isOpen) {
    throw new Error("send failed");
  }
  outbox.put(report);
}
