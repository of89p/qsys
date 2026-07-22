"use client";

import { useEffect, useRef, useState } from "react";

import type { QueueCall, QueueState, Station } from "@/lib/queue-types";

const DING_SOUND_URL = "/static/freesound_community-ding-dong-81717.mp3";

const EMPTY_STATE: QueueState = {
  version: 1,
  queues: {
    drinks: [],
    chicken: [],
    food: [],
  },
  latestCall: null,
};

type QueueDisplayProps = {
  flashDurationMs: number;
  autoReloadIntervalMs: number;
};

type StationView = {
  station: Station;
  title: string;
};

const STATION_VIEWS: StationView[] = [
  { station: "drinks", title: "Drinks/ Snacks" },
  { station: "chicken", title: "Chicken Rice" },
  { station: "food", title: "Other Food" },
];

function numberClass(index: number, isFlashing: boolean) {
  const baseClass =
    index === 0
      ? "text-[200px] leading-none font-extrabold text-yellow-400"
      : "text-[200px] leading-[1.1] font-bold text-white opacity-80";

  return isFlashing ? `${baseClass} queue-call-flash` : baseClass;
}

function playDing(audio: HTMLAudioElement) {
  audio.pause();
  try {
    audio.currentTime = 0;
  } catch {
    return;
  }

  void audio.play().catch(() => {});
}

function QueueNumber({
  call,
  index,
  isFlashing,
}: {
  call: QueueCall;
  index: number;
  isFlashing: boolean;
}) {
  return <div className={numberClass(index, isFlashing)}>{call.number}</div>;
}

export function QueueDisplay({
  flashDurationMs,
  autoReloadIntervalMs,
}: QueueDisplayProps) {
  const [queueState, setQueueState] = useState<QueueState>(EMPTY_STATE);
  const [flashingCallIds, setFlashingCallIds] = useState<Set<number>>(
    () => new Set(),
  );
  const latestCallIdRef = useRef<number | null>(null);

  useEffect(() => {
    const audio = new Audio(DING_SOUND_URL);
    const flashTimers = new Map<number, number>();
    audio.preload = "auto";

    function markFlashing(callId: number) {
      if (flashDurationMs <= 0) {
        return;
      }

      const existingTimer = flashTimers.get(callId);
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer);
      }

      setFlashingCallIds((current) => new Set(current).add(callId));
      const timer = window.setTimeout(() => {
        flashTimers.delete(callId);
        setFlashingCallIds((current) => {
          const next = new Set(current);
          next.delete(callId);
          return next;
        });
      }, flashDurationMs);
      flashTimers.set(callId, timer);
    }

    const events = new EventSource("/api/v1/events");
    events.addEventListener("state", (event) => {
      const message = event as MessageEvent<string>;
      const nextState = JSON.parse(message.data) as QueueState;
      const nextLatestCallId = nextState.latestCall?.callId ?? null;

      if (
        latestCallIdRef.current !== null &&
        nextLatestCallId !== null &&
        nextLatestCallId !== latestCallIdRef.current
      ) {
        playDing(audio);
        markFlashing(nextLatestCallId);
      }

      latestCallIdRef.current = nextLatestCallId;
      setQueueState(nextState);
    });

    return () => {
      events.close();
      for (const timer of flashTimers.values()) {
        window.clearTimeout(timer);
      }
      flashTimers.clear();
    };
  }, [flashDurationMs]);

  useEffect(() => {
    if (autoReloadIntervalMs <= 0) {
      return;
    }

    const reloadTimer = window.setInterval(() => {
      window.location.reload();
    }, autoReloadIntervalMs);

    return () => {
      window.clearInterval(reloadTimer);
    };
  }, [autoReloadIntervalMs]);

  return (
    <main className="flex h-screen w-full flex-col overflow-hidden bg-black font-sans text-white">
      <div className="flex min-h-0 flex-1 flex-row gap-4 pt-8">
        {STATION_VIEWS.map(({ station, title }, stationIndex) => (
          <div className="contents" key={station}>
            {stationIndex > 0 ? (
              <div className="m-0 my-10 w-1 shrink-0 bg-white" />
            ) : null}
            <section className="flex min-w-0 flex-1 flex-col items-center">
              <div className="mb-8 text-center">
                <div className="border-b-4">
                  <h2 className="pb-2 text-8xl font-black uppercase tracking-normal text-yellow-400">
                    {title}
                  </h2>
                </div>
              </div>
              <div className="flex w-full flex-col items-center justify-start gap-8">
                {queueState.queues[station].map((call, index) => (
                  <QueueNumber
                    call={call}
                    index={index}
                    isFlashing={flashingCallIds.has(call.callId)}
                    key={call.callId}
                  />
                ))}
              </div>
            </section>
          </div>
        ))}
      </div>

      <footer className="w-full shrink-0 py-4 text-center text-3xl text-white">
        <p>Brought to you by QSys &bull; Contact us at 9660 4222</p>
      </footer>
    </main>
  );
}
