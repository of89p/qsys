import { noStoreJson } from "@/lib/http";
import { getQueueState } from "@/lib/queue-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return noStoreJson({ ok: true, state: getQueueState() });
}
