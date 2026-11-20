import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue';
import { parseSnapshot, type Snapshot } from './contracts';

export function useStatus() {
  const snapshot = shallowRef<Snapshot | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const bridgeReady = ref(false);
  const readAt = ref<number | null>(null);
  const fresh = computed(() => snapshot.value !== null && error.value === null);
  let disposed = false;
  let pollingTimer: ReturnType<typeof setTimeout> | undefined;
  let timeoutTimer: ReturnType<typeof setTimeout> | undefined;

  async function refresh(): Promise<void> {
    if (disposed || loading.value) return;
    clearTimeout(pollingTimer);
    const api = window.pywebview?.api;
    if (!api || typeof api.get_status !== 'function') {
      bridgeReady.value = false;
      error.value = '请从本机执行端打开此窗口，当前尚未建立本机状态连接。';
      return;
    }
    bridgeReady.value = true;
    loading.value = true;
    timeoutTimer = setTimeout(() => {
      if (!disposed) error.value = '本机状态读取超时。请重新打开窗口，执行程序不会因此停止。';
    }, 12000);
    try {
      const response = await api.get_status();
      if (disposed) return;
      snapshot.value = parseSnapshot(response);
      readAt.value = Date.now() / 1000;
      error.value = null;
    } catch {
      if (!disposed) error.value = '暂时无法读取本机状态，请稍后重试。已有信息不是最新状态。';
    } finally {
      clearTimeout(timeoutTimer);
      if (!disposed) {
        loading.value = false;
        pollingTimer = setTimeout(() => { void refresh(); }, 2000);
      }
    }
  }

  const ready = () => { void refresh(); };
  onMounted(() => {
    window.addEventListener('pywebviewready', ready);
    void refresh();
  });
  onUnmounted(() => {
    disposed = true;
    clearTimeout(pollingTimer);
    clearTimeout(timeoutTimer);
    window.removeEventListener('pywebviewready', ready);
  });
  return { snapshot, loading, error, fresh, bridgeReady, readAt, refresh };
}
