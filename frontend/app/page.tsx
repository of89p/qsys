import { QueueDisplay } from "@/components/queue-display";
import { getDisplayConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

export default function Home() {
  return <QueueDisplay {...getDisplayConfig()} />;
}
