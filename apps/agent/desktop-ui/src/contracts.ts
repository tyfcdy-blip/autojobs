export const runStates = [
  'queued', 'starting', 'running', 'stopping', 'reconciling', 'succeeded',
  'failed', 'queue_expired', 'cancelled', 'stopped', 'timed_out',
] as const;

export type RunState = typeof runStates[number];

export interface Run {
  run_id: string;
  task_id: string;
  state: RunState;
  stop_requested: boolean;
  enqueued_at: number;
  deadline: number;
  started_at: number | null;
  finished_at: number | null;
  pid: number | null;
  exit_code: number | null;
  error_code: string | null;
  message: string;
  result: unknown;
}

export interface Snapshot {
  mode: 'local_validation';
  worker: { online: boolean; last_seen_at: number | null; pid: number | null };
  active_run: Run | null;
  runs: Run[];
  pending_event_count: number;
}

declare global {
  interface Window {
    pywebview?: { api: { get_status: () => Promise<unknown> } };
  }
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);
const nullableNumber = (value: unknown) => value === null || finite(value);
const nullableText = (value: unknown) => value === null || typeof value === 'string';

function validRun(value: unknown): value is Run {
  if (!record(value)) return false;
  return typeof value.run_id === 'string' && value.run_id.length > 0
    && typeof value.task_id === 'string' && value.task_id.length > 0
    && runStates.includes(value.state as RunState)
    && typeof value.stop_requested === 'boolean'
    && finite(value.enqueued_at) && finite(value.deadline)
    && nullableNumber(value.started_at) && nullableNumber(value.finished_at)
    && nullableNumber(value.pid) && nullableNumber(value.exit_code)
    && nullableText(value.error_code) && typeof value.message === 'string'
    && Object.hasOwn(value, 'result');
}

export function parseSnapshot(value: unknown): Snapshot {
  if (!record(value) || value.mode !== 'local_validation' || !record(value.worker)
      || typeof value.worker.online !== 'boolean'
      || !nullableNumber(value.worker.last_seen_at) || !nullableNumber(value.worker.pid)
      || (value.active_run !== null && !validRun(value.active_run))
      || !Array.isArray(value.runs) || value.runs.length > 100 || !value.runs.every(validRun)
      || !finite(value.pending_event_count) || !Number.isInteger(value.pending_event_count)
      || value.pending_event_count < 0) {
    throw new Error('INVALID_SNAPSHOT');
  }
  return value as unknown as Snapshot;
}
