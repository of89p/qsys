function readIntegerEnv(name: string, fallback: number, minimum = 0): number {
  const rawValue = process.env[name];
  if (rawValue === undefined || rawValue.trim() === "") {
    return fallback;
  }

  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed) || parsed < minimum) {
    return fallback;
  }

  return parsed;
}

export function getServerConfig() {
  return {
    maxVisibleOrders: readIntegerEnv("QSYS_MAX_VISIBLE_ORDERS", 3, 1),
    sseHeartbeatMs: readIntegerEnv("QSYS_SSE_HEARTBEAT_MS", 15000, 1000),
  };
}

export function getDisplayConfig() {
  return {
    flashDurationMs: readIntegerEnv("QSYS_FLASH_DURATION_MS", 10000, 0),
    autoReloadIntervalMs: readIntegerEnv(
      "QSYS_AUTO_RELOAD_INTERVAL_MS",
      300000,
      0,
    ),
  };
}
