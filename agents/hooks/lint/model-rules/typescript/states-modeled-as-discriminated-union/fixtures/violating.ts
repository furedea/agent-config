/** Violating cases for the states-modeled-as-discriminated-union eval; labels are in ../expect.yml. Never imported or run. */

export type RequestState = {
  isLoading: boolean;
  data?: User;
  error?: string;
};

export interface Payment {
  method: "card" | "cash";
  last4?: string;
  expiry?: string;
}

export class Upload {
  isDone = false;
  isFailed = false;
  url?: string;
  reason?: string;
}

export type Connection = {
  readonly connected: boolean;
  readonly socket?: WebSocket;
  readonly retryAtMs?: number;
};
