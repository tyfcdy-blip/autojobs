<script setup lang="ts">
import { computed } from 'vue';
import type { Run } from '../contracts';
import { formatResult, formatTime } from '../presentation';
import StateBadge from './StateBadge.vue';
const props = defineProps<{ run: Run | null }>();
const formattedResult = computed(() => formatResult(props.run?.result));
</script>

<template>
  <section class="panel detail" aria-labelledby="detail-title">
    <div class="section-title"><h2 id="detail-title">运行详情</h2><span class="muted">只读</span></div>
    <div v-if="!run" class="empty-state compact">
      <p>选择一条运行记录</p><span>查看本轮时间、结束原因与业务结果。</span>
    </div>
    <template v-else>
      <div class="detail-heading"><h3>{{ run.task_id }}</h3><StateBadge :state="run.state" /></div>
      <dl class="details-grid">
        <dt>运行编号</dt><dd class="mono">{{ run.run_id }}</dd>
        <dt>入队时间</dt><dd>{{ formatTime(run.enqueued_at) }}</dd>
        <dt>开始时间</dt><dd>{{ formatTime(run.started_at) }}</dd>
        <dt>结束时间</dt><dd>{{ formatTime(run.finished_at) }}</dd>
        <dt>进程 / 退出码</dt><dd>{{ run.pid ?? '—' }} / {{ run.exit_code ?? '—' }}</dd>
      </dl>
      <p v-if="run.stop_requested" class="inline-notice">已收到停止请求，以执行程序确认的最终状态为准。</p>
      <div v-if="run.message || run.error_code" class="outcome-message">
        <span v-if="run.error_code" class="mono muted">{{ run.error_code }}</span>
        <p>{{ run.message || '暂无进一步说明' }}</p>
      </div>
      <h3 class="result-title">业务结果</h3>
      <p v-if="run.result === null" class="muted result-note">尚无已保存的业务结果，是否完成以运行状态为准。</p>
      <pre class="result-content" tabindex="0" aria-label="业务结果内容">{{ formattedResult.text }}</pre>
      <p v-if="formattedResult.truncated" class="muted result-note">窗口仅展示前 20,000 个字符，完整结果保留在本机记录中。</p>
    </template>
  </section>
</template>
