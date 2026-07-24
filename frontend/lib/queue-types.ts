export const STATIONS = ["drinks", "chicken", "food"] as const;

export type Station = (typeof STATIONS)[number];

export type QueueCall = {
  callId: number;
  number: string;
  calledAt: string;
};

export type LatestCall = QueueCall & {
  station: Station;
};

export type QueueState = {
  version: 1;
  queues: Record<Station, QueueCall[]>;
  latestCall: LatestCall | null;
};

export type QueueSuccessResponse = {
  ok: true;
  state: QueueState;
};

export type QueueErrorResponse = {
  ok: false;
  error: string;
};

export type QueueResponse = QueueSuccessResponse | QueueErrorResponse;
