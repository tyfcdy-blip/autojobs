<script setup lang="ts">
import { computed, ref } from 'vue';
import { useStatus } from './useStatus';
import { formatTime } from './presentation';
import RunDetail from './components/RunDetail.vue';
import StateBadge from './components/StateBadge.vue';

const { snapshot, loading, error, fresh, readAt, refresh } = useStatus();
const selectedRunId = ref<string | null>(null);
const selectedRun = computed(() => snapshot.value?.runs.find(run => run.run_id === selectedRunId.value)
  ?? snapshot.value?.active_run ?? snapshot.value?.runs[0] ?? null);
const slotLabel = computed(() => {
  if (!fresh.value) return '状态待确认';
  if (snapshot.value?.active_run?.state === 'reconciling') return '占用待核实';
  if (snapshot.value?.active_run) return '忙碌';
  return snapshot.value?.worker.online ? '空闲' : '未就绪';
});
const workerLabel = computed(() => !fresh.value ? '待确认' : snapshot.value?.worker.online ? '在线' : '离线');
</script>

<template>
  <div class="desktop-shell">
    <header class="app-header">
      <div><div class="eyebrow">AUTOJOBS · 本机执行端</div><h1>执行状态</h1>
        <p class="subtitle">本地验证模式 <span class="separator">/</span> 尚未连接中台</p>
      </div>
      <div class="header-actions">
        <span class="refresh-time">最近读取：{{ formatTime(readAt) }}</span>
        <button class="primary-button" :disabled="loading" @click="refresh">
          {{ loading ? '正在读取…' : '刷新状态' }}
        </button>
      </div>
    </header>

    <div v-if="error" class="error-banner" role="alert">{{ error }}</div>
    <div v-else-if="!snapshot" class="connection-notice" role="status">正在读取执行程序状态…</div>

    <section class="status-strip" aria-label="本机状态">
      <div class="status-cell"><span class="field-label">后台执行程序</span>
        <strong :class="{ 'text-success': fresh && snapshot?.worker.online }"><span class="status-dot" />{{ workerLabel }}</strong>
        <span class="muted">{{ snapshot?.worker.pid != null ? `进程 ${snapshot.worker.pid}` : '尚无进程信息' }}</span>
      </div>
      <div class="status-cell"><span class="field-label">执行位置</span><strong>{{ slotLabel }}</strong><span class="muted">本机同时执行一个任务</span></div>
      <div class="status-cell"><span class="field-label">本地待回传事件</span><strong>{{ snapshot?.pending_event_count ?? '—' }}</strong><span class="muted">本地保存，尚未上报中台</span></div>
    </section>

    <main>
      <section class="panel current-task" aria-labelledby="current-title">
        <div class="section-title"><h2 id="current-title">当前任务</h2><span v-if="!fresh && snapshot" class="badge warning">上次观测</span></div>
        <div v-if="snapshot?.active_run" class="current-content">
          <div class="current-heading"><h3>{{ snapshot.active_run.task_id }}</h3><StateBadge :state="snapshot.active_run.state" /></div>
          <dl class="current-metadata">
            <div><dt>运行编号</dt><dd class="mono">{{ snapshot.active_run.run_id }}</dd></div>
            <div><dt>开始时间</dt><dd>{{ formatTime(snapshot.active_run.started_at) }}</dd></div>
            <div><dt>最近心跳</dt><dd>{{ formatTime(snapshot.worker.last_seen_at) }}</dd></div>
          </dl>
          <p v-if="snapshot.active_run.state === 'reconciling'" class="inline-notice">上轮运行需要核实。执行位置保持占用，后续任务不会自动启动。</p>
          <p v-else class="current-explanation">进程结束且结果核对完成后，才会释放本机执行位置。</p>
        </div>
        <div v-else class="empty-state"><p>{{ snapshot ? '当前没有运行中的任务' : '等待本机状态' }}</p>
          <span>{{ snapshot?.worker.online ? '执行程序已启动，等待本地队列中的任务。' : '请先启动本机执行程序，窗口会自动更新状态。' }}</span>
        </div>
      </section>

      <div class="history-layout">
        <section class="panel history" aria-labelledby="history-title">
          <div class="section-title"><h2 id="history-title">最近运行</h2><span class="muted">显示 {{ snapshot?.runs.length ?? 0 }} 条</span></div>
          <div v-if="!snapshot?.runs.length" class="empty-state history-empty"><p>还没有运行记录</p><span>真实任务运行后，记录会显示在这里。</span></div>
          <div v-else class="table-wrap">
            <table><thead><tr><th scope="col">任务 / 运行编号</th><th scope="col">状态</th><th scope="col">入队时间</th></tr></thead>
              <tbody><tr v-for="run in snapshot.runs" :key="run.run_id" :class="{ selected: selectedRun?.run_id === run.run_id }">
                <td><button class="run-button" :aria-pressed="selectedRun?.run_id === run.run_id" @click="selectedRunId = run.run_id"><span>{{ run.task_id }}</span><small class="mono">{{ run.run_id }}</small></button></td>
                <td><StateBadge :state="run.state" /></td><td class="time-cell">{{ formatTime(run.enqueued_at) }}</td>
              </tr></tbody>
            </table>
          </div>
        </section>
        <RunDetail :run="selectedRun" />
      </div>
    </main>
    <footer class="window-note"><strong>关闭窗口不会停止执行程序</strong><span>本窗口仅查看状态，任务执行与窗口独立。</span></footer>
  </div>
</template>
