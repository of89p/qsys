import { getServerConfig } from "@/lib/config";
import { STATIONS } from "@/lib/queue-types";
import type { QueueState, Station } from "@/lib/queue-types";

type QueueSubscriber = (state: QueueState) => void;

export class QueueInputError extends Error {}

const queues: QueueState["queues"] = {
  drinks: [],
  chicken: [],
  food: [],
};

let latestCall: QueueState["latestCall"] = null;
let nextCallId = 1;
const subscribers = new Set<QueueSubscriber>();

function cloneState(): QueueState {
  return {
    version: 1,
    queues: {
      drinks: [...queues.drinks],
      chicken: [...queues.chicken],
      food: [...queues.food],
    },
    latestCall,
  };
}

function isStation(value: string): value is Station {
  return STATIONS.includes(value as Station);
}

function emitState(state: QueueState) {
  for (const subscriber of subscribers) {
    subscriber(state);
  }
}

export function getQueueState(): QueueState {
  return cloneState();
}

export function subscribeToQueueState(subscriber: QueueSubscriber) {
  subscribers.add(subscriber);

  return () => {
    subscribers.delete(subscriber);
  };
}

export function addQueueCall(stationInput: string, numberInput: string): QueueState {
  const station = stationInput.toLowerCase();
  const number = numberInput.trim();

  if (!isStation(station)) {
    throw new QueueInputError("station must be drinks, chicken or food");
  }
  if (!number) {
    throw new QueueInputError("number must contain digits only");
  }
  if (!/^\d+$/.test(number)) {
    throw new QueueInputError("number must contain digits only");
  }
  if (number.length > 3) {
    throw new QueueInputError("number must be at most 3 digits");
  }

  const maxVisibleOrders = getServerConfig().maxVisibleOrders;
  const calledAt = new Date().toISOString();
  const call = {
    callId: nextCallId,
    number: number.padStart(3, "0"),
    calledAt,
  };
  nextCallId += 1;

  const dedupedQueue = queues[station].filter(
    (existingCall) => existingCall.number !== call.number,
  );
  queues[station] = [call, ...dedupedQueue].slice(0, maxVisibleOrders);
  latestCall = {
    ...call,
    station,
  };

  const state = cloneState();
  emitState(state);
  return state;
}
