import { noStoreJson } from "@/lib/http";
import { addQueueCall, QueueInputError } from "@/lib/queue-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const station = String(body?.station ?? "");
  const number = String(body?.number ?? "");

  try {
    const state = addQueueCall(station, number);
    return noStoreJson({ ok: true, state });
  } catch (error) {
    if (error instanceof QueueInputError) {
      return noStoreJson({ ok: false, error: error.message }, { status: 400 });
    }

    throw error;
  }
}
