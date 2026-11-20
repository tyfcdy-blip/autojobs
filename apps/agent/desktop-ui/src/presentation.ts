import type { RunState } from './contracts';

export const states: Record<RunState, { label: string; tone: string }> = {
  queued: { label: '排队中', tone: 'neutral' },
  starting: { label: '启动中', tone: 'active' },
  running: { label: '运行中', tone: 'active' },
  stopping: { label: '停止中', tone: 'warning' },
  reconciling: { label: '待核实', tone: 'warning' },
  succeeded: { label: '成功', tone: 'success' },
  failed: { label: '失败', tone: 'danger' },
  queue_expired: { label: '排队超时', tone: 'warning' },
  cancelled: { label: '已取消', tone: 'neutral' },
  stopped: { label: '已停止', tone: 'neutral' },
  timed_out: { label: '运行超时', tone: 'danger' },
};

const dateTime = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
});

export function formatTime(timestamp: number | null | undefined): string {
  if (timestamp == null) return '—';
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.getTime()) ? '时间不可用' : dateTime.format(date);
}

export function formatResult(result: unknown): { text: string; truncated: boolean } {
  if (result === undefined) return { text: '暂无结果', truncated: false };
  const text = JSON.stringify(result, null, 2) ?? '暂无结果';
  return { text: text.slice(0, 20000), truncated: text.length > 20000 };
}
