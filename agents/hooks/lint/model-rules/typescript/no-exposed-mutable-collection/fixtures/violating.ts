/** Violating cases for the no-exposed-mutable-collection eval; labels are in ../expect.yml. Never imported or run. */

export class Team {
  private readonly memberNames: string[] = [];

  add(name: string): void {
    if (!this.memberNames.includes(name)) {
      this.memberNames.push(name);
    }
  }

  members(): string[] {
    return this.memberNames;
  }
}

export class Post {
  private readonly tagSet = new Set<string>();

  get tags(): Set<string> {
    return this.tagSet;
  }
}

export class WordCounter {
  private readonly table = new Map<string, number>();
  private total = 0;

  record(word: string): void {
    this.table.set(word, (this.table.get(word) ?? 0) + 1);
    this.total += 1;
  }

  counts(): Map<string, number> {
    return this.table;
  }
}

export class Scheduler {
  private readonly queue: Job[] = [];

  pending(): Array<Job> {
    return this.queue;
  }
}
