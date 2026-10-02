const test = require('node:test');
const assert = require('node:assert/strict');
const {
  detailText,
  formatAge,
  formatDuration,
  isFinal,
  parseTime,
  splitTasks,
  stripAnsi,
  taskDescription,
  taskDuration,
  taskLabel,
  taskLimit,
  templateName,
} = require('../src/tasks');

const NOW = new Date('2026-10-02T12:00:00Z');
const t = (id, status, extra = {}) => ({
  id,
  status,
  template_id: 3,
  tpl_alias: `tpl${id}`,
  ...extra,
});

test('isFinal', () => {
  for (const s of ['success', 'error', 'stopped', 'rejected']) assert.ok(isFinal(s), s);
  for (const s of ['waiting', 'starting', 'running', 'stopping', 'waiting_confirmation']) {
    assert.ok(!isFinal(s), s);
  }
});

test('splitTasks: active oldest first, finished newest first and capped', () => {
  const { running, finished } = splitTasks(
    [t(5, 'success'), t(9, 'running'), t(7, 'waiting'), t(8, 'error'), t(6, 'stopped')],
    2,
  );
  assert.deepEqual(
    running.map((x) => x.id),
    [7, 9],
  );
  assert.deepEqual(
    finished.map((x) => x.id),
    [8, 6],
  );
});

test('templateName / taskLabel fall back to playbook, then template id', () => {
  assert.equal(taskLabel(t(1, 'success')), '#1 tpl1');
  assert.equal(
    templateName({ id: 1, status: 'x', template_id: 3, tpl_playbook: 'a.yml' }),
    'a.yml',
  );
  assert.equal(templateName({ id: 1, status: 'x', template_id: 3 }), 'template 3');
});

test('formatDuration', () => {
  assert.equal(formatDuration(-3), '0s');
  assert.equal(formatDuration(45), '45s');
  assert.equal(formatDuration(185), '3m05s');
  assert.equal(formatDuration(7440), '2h04m');
  assert.equal(formatDuration(15 * 86400 + 10 * 3600 + 59), '15d10h');
});

test('parseTime: absent, zero and invalid dates are null', () => {
  assert.equal(parseTime(undefined), null);
  assert.equal(parseTime(null), null);
  assert.equal(parseTime('0001-01-01T00:00:00Z'), null);
  assert.equal(parseTime('garbage'), null);
  assert.equal(parseTime('2026-10-02T11:00:00Z')?.toISOString(), '2026-10-02T11:00:00.000Z');
});

test('taskDuration: finished, running (until now), never started', () => {
  const start = '2026-10-02T11:58:00Z';
  assert.equal(taskDuration(t(1, 'success', { start, end: '2026-10-02T11:59:40Z' }), NOW), '1m40s');
  assert.equal(taskDuration(t(1, 'running', { start }), NOW), '2m00s');
  assert.equal(taskDuration(t(1, 'error', { start, end: '0001-01-01T00:00:00Z' }), NOW), null);
  assert.equal(taskDuration(t(1, 'waiting'), NOW), null);
});

test('formatAge', () => {
  const ago = (s) => formatAge(new Date(NOW.getTime() - s * 1000), NOW);
  assert.equal(ago(10), 'just now');
  assert.equal(ago(300), '5m ago');
  assert.equal(ago(7200), '2h ago');
  assert.equal(ago(3 * 86400), '3d ago');
});

test('taskDescription: status, duration, age once finished', () => {
  const done = t(1, 'success', { start: '2026-10-02T11:00:00Z', end: '2026-10-02T11:00:30Z' });
  assert.equal(taskDescription(done, NOW), 'success · 30s · 59m ago');
  assert.equal(
    taskDescription(t(2, 'running', { start: '2026-10-02T11:59:00Z' }), NOW),
    'running · 1m00s',
  );
  assert.equal(taskDescription(t(3, 'waiting'), NOW), 'waiting');
});

test('taskLimit: params list, params string, legacy field, none', () => {
  assert.equal(taskLimit(t(1, 'x', { params: { limit: ['a', 'b'] } })), 'a,b');
  assert.equal(taskLimit(t(1, 'x', { params: { limit: 'h1' } })), 'h1');
  assert.equal(taskLimit(t(1, 'x', { limit: 'old' })), 'old');
  assert.equal(taskLimit(t(1, 'x')), '');
});

test('stripAnsi', () => {
  assert.equal(stripAnsi('\x1b[0;32mok\x1b[0m: [h1]\x1b[K'), 'ok: [h1]');
});

test('detailText: header rows present only when set, ANSI-free output', () => {
  const task = t(42, 'success', {
    tpl_playbook: 'book.yml',
    params: { limit: ['h1'] },
    message: 'manual run',
    commit_hash: '0123456789abcdef',
    commit_message: 'fix',
    schedule_id: 4,
    created: '2026-10-02T11:00:00Z',
    start: '2026-10-02T11:00:01Z',
    end: '2026-10-02T11:01:41Z',
  });
  const text = detailText(task, '\x1b[32mPLAY RECAP\x1b[0m\n\n', 'https://s/h?t=42', NOW);
  assert.equal(
    text,
    [
      'Task #42 tpl42',
      'Status:   success',
      'Template: tpl42 (book.yml)',
      'Limit:    h1',
      'Message:  manual run',
      'Commit:   0123456789 fix',
      'Origin:   schedule #4',
      'Created:  2026-10-02T11:00:00.000Z',
      'Started:  2026-10-02T11:00:01.000Z',
      'Ended:    2026-10-02T11:01:41.000Z',
      'Duration: 1m40s',
      'URL:      https://s/h?t=42',
      '-'.repeat(72),
      'PLAY RECAP',
      '',
    ].join('\n'),
  );
});

test('detailText: minimal task, user origin, no output yet', () => {
  const text = detailText(t(7, 'waiting', { user_id: 2 }), '  \n', 'u', NOW);
  assert.match(
    text,
    /^Task #7 tpl7\nStatus: {3}waiting\nTemplate: tpl7\nOrigin: {3}user #2\nURL: {6}u\n-+\n\(no output yet\)\n$/,
  );
});
