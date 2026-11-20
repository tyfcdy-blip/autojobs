import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import App from '../src/App.vue';
import { parseSnapshot, type Run, type Snapshot } from '../src/contracts';

// 仅替换桌面宿主桥，页面状态与刷新逻辑使用真实组件。
const makeRun = (overrides: Partial<Run> = {}): Run => ({
  run_id: 'test-run-001', task_id: '测试任务', state: 'running', stop_requested: false,
  enqueued_at: 1795064400, deadline: 1795064700, started_at: 1795064401,
  finished_at: null, pid: 100, exit_code: null, error_code: null, message: '', result: null,
  ...overrides,
});
const makeSnapshot = (overrides: Partial<Snapshot> = {}): Snapshot => ({
  mode: 'local_validation', worker: { online: true, last_seen_at: 1795064400, pid: 50 },
  active_run: null, runs: [], pending_event_count: 0, ...overrides,
});
let wrapper: VueWrapper | undefined;
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined;
  delete window.pywebview;
  vi.useRealTimers();
});
function start(getStatus = vi.fn().mockResolvedValue(makeSnapshot())) {
  window.pywebview = { api: { get_status: getStatus } };
  wrapper = mount(App);
  return getStatus;
}

describe('本机只读窗口', () => {
  it('UI-01 桥未建立时不显示正常连接或假任务', async () => {
    wrapper = mount(App);
    await flushPromises();
    expect(wrapper.text()).toContain('请从本机执行端打开此窗口');
    expect(wrapper.text()).toContain('尚未连接中台');
    expect(wrapper.text()).toContain('状态待确认');
  });
  it('UI-01 桥就绪事件可以恢复首次未连接状态', async () => {
    wrapper = mount(App);
    const getStatus = vi.fn().mockResolvedValue(makeSnapshot());
    window.pywebview = { api: { get_status: getStatus } };
    window.dispatchEvent(new Event('pywebviewready'));
    await flushPromises();
    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
  it('UI-02 无记录时显示空状态且分开在线/空闲', async () => {
    start(); await flushPromises();
    expect(wrapper!.text()).toContain('在线');
    expect(wrapper!.text()).toContain('空闲');
    expect(wrapper!.text()).toContain('还没有运行记录');
    expect(wrapper!.findAll('tbody tr')).toHaveLength(0);
  });
  it('UI-02 离线无占用时显示未就绪而非空闲', async () => {
    start(vi.fn().mockResolvedValue(makeSnapshot({ worker: { online: false, last_seen_at: null, pid: null } })));
    await flushPromises();
    expect(wrapper!.text()).toContain('离线');
    expect(wrapper!.text()).toContain('未就绪');
    expect(wrapper!.text()).not.toContain('空闲');
  });
  it.each(['running', 'reconciling'] as const)('UI-03 %s 保留占用与任务信息', async (state) => {
    const run = makeRun({ state });
    start(vi.fn().mockResolvedValue(makeSnapshot({ active_run: run, runs: [run], pending_event_count: 3 })));
    await flushPromises();
    expect(wrapper!.text()).toContain(state === 'running' ? '忙碌' : '占用待核实');
    expect(wrapper!.text()).toContain('test-run-001');
    expect(wrapper!.text()).toContain('本地保存，尚未上报中台');
    expect(wrapper!.findAll('tbody tr')).toHaveLength(1);
  });
  it('UI-04 失败后保留快照并撤销实时在线表述，不暴露异常原文', async () => {
    const getStatus = start(); await flushPromises();
    getStatus.mockRejectedValueOnce(new Error('private exception token'));
    await wrapper!.get('button.primary-button').trigger('click'); await flushPromises();
    expect(wrapper!.get('[role="alert"]').text()).toContain('不是最新状态');
    expect(wrapper!.text()).toContain('状态待确认');
    expect(wrapper!.text()).not.toContain('private exception token');
    expect(wrapper!.text()).not.toContain('在线');
  });
  it('UI-04 非法快照不替代最后合法记录', async () => {
    const getStatus = start(); await flushPromises();
    getStatus.mockResolvedValueOnce({ mode: 'local_validation', runs: 'not-array' });
    await wrapper!.get('button.primary-button').trigger('click'); await flushPromises();
    expect(wrapper!.find('[role="alert"]').exists()).toBe(true);
  });
  it('UI-05 长请求和重复ready不会造成并发读取，超时明确提示', async () => {
    let resolve: (value: Snapshot) => void = () => { throw new Error('未初始化请求'); };
    const promise = new Promise<Snapshot>(done => { resolve = done; });
    const getStatus = start(vi.fn().mockReturnValue(promise));
    window.dispatchEvent(new Event('pywebviewready'));
    await vi.advanceTimersByTimeAsync(14000);
    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(wrapper!.text()).toContain('读取超时');
    resolve(makeSnapshot()); await flushPromises();
    expect(wrapper!.find('[role="alert"]').exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(1999);
    expect(getStatus).toHaveBeenCalledTimes(1);
  });
  it('UI-05 销毁后不读取，迟到响应不安排新轮询', async () => {
    let resolve: (value: Snapshot) => void = () => { throw new Error('未初始化请求'); };
    const promise = new Promise<Snapshot>(done => { resolve = done; });
    const getStatus = start(vi.fn().mockReturnValue(promise));
    wrapper!.unmount(); wrapper = undefined;
    resolve(makeSnapshot()); await flushPromises();
    window.dispatchEvent(new Event('pywebviewready'));
    await vi.advanceTimersByTimeAsync(20000);
    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('UI-06 HTML结果作为文本显示，可选择其他运行，null不推断成功', async () => {
    const first = makeRun({ state: 'failed', message: '<img src=x onerror=alert(1)>', result: '<script>bad()</script>' });
    const second = makeRun({ run_id: 'test-run-002', task_id: '已结束测试', state: 'stopped' });
    start(vi.fn().mockResolvedValue(makeSnapshot({ runs: [first, second] })));
    await flushPromises();
    expect(wrapper!.findAll('img, script')).toHaveLength(0);
    expect(wrapper!.get('.result-content').text()).toContain('<script>bad()</script>');
    await wrapper!.findAll('.run-button')[1]!.trigger('click');
    expect(wrapper!.get('.detail').text()).toContain('已停止');
    expect(wrapper!.get('.result-content').text()).toBe('null');
  });
  it('UI-06 超长结果有可见截断提示', async () => {
    start(vi.fn().mockResolvedValue(makeSnapshot({ runs: [makeRun({ result: 'x'.repeat(25000) })] })));
    await flushPromises();
    expect(wrapper!.get('.result-content').text()).toHaveLength(20000);
    expect(wrapper!.text()).toContain('完整结果保留在本机记录中');
  });
});

describe('宿主快照边界', () => {
  it.each([
    { pending_event_count: -1 }, { pending_event_count: 1.5 },
    { active_run: makeRun({ state: 'unknown' as Run['state'] }) },
    { runs: Array.from({ length: 101 }, () => makeRun()) },
  ])('拒绝不符合契约的快照 %j', (overrides) => {
    expect(() => parseSnapshot(makeSnapshot(overrides))).toThrow('INVALID_SNAPSHOT');
  });
});
