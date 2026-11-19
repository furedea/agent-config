/** Conforming cases for the states-modeled-as-discriminated-union eval; labels are in ../expect.yml. Never imported or run. */

export type FetchOptions = {
  readonly timeoutMs?: number;
  readonly retries?: number;
  readonly verbose?: boolean;
};

export interface Account {
  readonly name: string;
  readonly admin: boolean;
  readonly verified: boolean;
}

export type Fetch =
  | { readonly kind: "loading" }
  | { readonly kind: "done"; readonly data: User }
  | { readonly kind: "failed"; readonly error: string; readonly retryable: boolean };

export class Logger {
  verbose = false;
  prefix?: string;

  log(line: string): void {
    console.log(this.prefix ? `${this.prefix} ${line}` : line);
  }
}
