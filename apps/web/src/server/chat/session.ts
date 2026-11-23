import { cache } from "@/server/cache";
import { env } from "@/server/env";
import type { RecentTurn } from "@/server/metrics/resolver";
import { hashIdentifier } from "@/server/rate-limit";

const SESSION_TTL_SECONDS = 30 * 60;
const MAX_TURNS = 8;

function sessionKey(sessionId: string): string {
  const salt = env.IP_HASH_SALT ? `${env.IP_HASH_SALT}:session` : undefined;
  return `session:${hashIdentifier(sessionId, salt)}`;
}

export async function getRecentTurns(sessionId: string): Promise<RecentTurn[]> {
  const turns = await cache.get<RecentTurn[]>(sessionKey(sessionId));
  return Array.isArray(turns) ? turns.slice(0, MAX_TURNS) : [];
}

export async function recordTurn(sessionId: string, turn: RecentTurn): Promise<void> {
  const turns = await getRecentTurns(sessionId);
  const next = [
    {
      metric_id: turn.metric_id,
      filters: turn.filters,
      interpretation: turn.interpretation.slice(0, 160),
    },
    ...turns.filter((item) => item.interpretation !== turn.interpretation).slice(0, MAX_TURNS - 1),
  ];
  await cache.set(sessionKey(sessionId), next, SESSION_TTL_SECONDS);
}
