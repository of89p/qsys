import { getServerConfig } from "@/lib/config";
import { SSE_HEADERS } from "@/lib/http";
import { getQueueState, subscribeToQueueState } from "@/lib/queue-store";
import type { QueueState } from "@/lib/queue-types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function sseEvent(eventName: string, data: QueueState) {
  return `event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`;
}

export async function GET() {
  const encoder = new TextEncoder();
  const heartbeatMs = getServerConfig().sseHeartbeatMs;
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let unsubscribe = () => {};
  let closed = false;

  const stream = new ReadableStream({
    start(controller) {
      const enqueue = (text: string) => {
        if (closed) {
          return;
        }

        try {
          controller.enqueue(encoder.encode(text));
        } catch {
          closed = true;
          unsubscribe();
          if (heartbeat) {
            clearInterval(heartbeat);
          }
        }
      };

      enqueue(sseEvent("state", getQueueState()));
      unsubscribe = subscribeToQueueState((state) => {
        enqueue(sseEvent("state", state));
      });
      heartbeat = setInterval(() => {
        enqueue(": heartbeat\n\n");
      }, heartbeatMs);
    },
    cancel() {
      closed = true;
      unsubscribe();
      if (heartbeat) {
        clearInterval(heartbeat);
      }
    },
  });

  return new Response(stream, {
    headers: SSE_HEADERS,
  });
}
