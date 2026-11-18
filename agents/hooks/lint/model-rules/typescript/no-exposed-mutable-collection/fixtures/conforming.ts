/** Conforming cases for the no-exposed-mutable-collection eval; labels are in ../expect.yml. Never imported or run. */

export class Roster {
  private readonly memberNames: string[] = [];

  members(): readonly string[] {
    return this.memberNames;
  }
}

export class Tally {
  private readonly table = new Map<string, number>();

  counts(): ReadonlyMap<string, number> {
    return this.table;
  }
}

export class Request {
  constructor(private readonly headerMap: Record<string, string>) {}

  headers(): Readonly<Record<string, string>> {
    return this.headerMap;
  }
}

export class CsvRow {
  constructor(public readonly cells: string[]) {}

  values(): string[] {
    return this.cells;
  }
}
