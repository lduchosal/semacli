// @ts-check
// Pure task presentation: running/finished split, labels, durations and the
// text of the task detail document. No `vscode` import.

/** Semaphore states after which a task never changes again. */
const FINAL_STATES = new Set(['success', 'error', 'stopped', 'rejected']);

/** Codicon per status (https://code.visualstudio.com/api/references/icons-in-labels). */
const STATUS_ICONS = {
  waiting: 'clock',
  starting: 'loading~spin',
  waiting_confirmation: 'question',
  confirmed: 'clock',
  running: 'sync~spin',
  stopping: 'loading~spin',
  success: 'pass',
  error: 'error',
  stopped: 'circle-slash',
  rejected: 'circle-slash',
};

/** Theme colour per status, for the icons that carry a verdict. */
const STATUS_COLORS = {
  success: 'testing.iconPassed',
  error: 'testing.iconFailed',
  stopped: 'disabledForeground',
  rejected: 'disabledForeground',
};

// CSI escape sequences (colours, cursor moves) as emitted by ansible.
const ESC = String.fromCharCode(27);
const ANSI_PATTERN = new RegExp(`${ESC}\\[[0-?]*[ -/]*[@-~]`, 'g');

/**
 * @param {string} status
 * @returns {boolean}
 */
function isFinal(status) {
  return FINAL_STATES.has(status);
}

/**
 * Split the task list: active tasks (oldest first, the order they were
 * queued) and the `finishedLimit` most recent finished ones.
 * @param {import('./api').Task[]} tasks
 * @param {number} finishedLimit
 * @returns {{ running: import('./api').Task[], finished: import('./api').Task[] }}
 */
function splitTasks(tasks, finishedLimit) {
  const newestFirst = [...tasks].sort((a, b) => b.id - a.id);
  return {
    running: newestFirst.filter((t) => !isFinal(t.status)).reverse(),
    finished: newestFirst.filter((t) => isFinal(t.status)).slice(0, finishedLimit),
  };
}

/**
 * @param {import('./api').Task} task
 * @returns {string}
 */
function templateName(task) {
  return task.tpl_alias || task.tpl_playbook || `template ${task.template_id}`;
}

/**
 * @param {import('./api').Task} task
 * @returns {string}
 */
function taskLabel(task) {
  return `#${task.id} ${templateName(task)}`;
}

/**
 * Seconds -> "45s", "3m05s", "2h04m", "15d10h".
 * @param {number} seconds
 * @returns {string}
 */
function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`;
  if (s < 86400) {
    return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`;
  }
  return `${Math.floor(s / 86400)}d${String(Math.floor((s % 86400) / 3600)).padStart(2, '0')}h`;
}

/**
 * Parse a Semaphore timestamp; null for absent / zero dates ("0001-01-01…").
 * @param {string | null | undefined} value
 * @returns {Date | null}
 */
function parseTime(value) {
  if (!value || value.startsWith('0001-')) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Run time: start -> end, or start -> now while running.
 * @param {import('./api').Task} task
 * @param {Date} now
 * @returns {string | null}
 */
function taskDuration(task, now) {
  const start = parseTime(task.start);
  if (!start) return null;
  const end = parseTime(task.end) ?? (isFinal(task.status) ? null : now);
  return end ? formatDuration((end.getTime() - start.getTime()) / 1000) : null;
}

/**
 * "3m ago" style age of a date.
 * @param {Date} date
 * @param {Date} now
 * @returns {string}
 */
function formatAge(date, now) {
  const s = Math.max(0, Math.round((now.getTime() - date.getTime()) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/**
 * Tree item description: status, run time and, once finished, its age.
 * @param {import('./api').Task} task
 * @param {Date} now
 * @returns {string}
 */
function taskDescription(task, now) {
  const parts = [task.status];
  const duration = taskDuration(task, now);
  if (duration) parts.push(duration);
  const ended = parseTime(task.end);
  if (ended && isFinal(task.status)) parts.push(formatAge(ended, now));
  return parts.join(' · ');
}

/**
 * The limit a task ran with: params.limit (list or string) or the legacy
 * top-level `limit`.
 * @param {import('./api').Task} task
 * @returns {string}
 */
function taskLimit(task) {
  const limit = task.params?.limit ?? task.limit ?? '';
  return Array.isArray(limit) ? limit.join(',') : limit;
}

/**
 * @param {string} text
 * @returns {string}
 */
function stripAnsi(text) {
  return text.replace(ANSI_PATTERN, '');
}

/**
 * Who / what started the task.
 * @param {import('./api').Task} task
 * @returns {string | null}
 */
function taskOrigin(task) {
  if (task.schedule_id) return `schedule #${task.schedule_id}`;
  if (task.user_id) return `user #${task.user_id}`;
  return null;
}

/**
 * Plain-text task detail: a metadata header, then the raw output.
 * @param {import('./api').Task} task
 * @param {string} output raw output (ANSI codes are stripped)
 * @param {string} url web UI URL of the task
 * @param {Date} now
 * @returns {string}
 */
function detailText(task, output, url, now) {
  /** @type {[string, string | null | undefined][]} */
  const rows = [
    ['Status', task.status],
    [
      'Template',
      task.tpl_playbook ? `${templateName(task)} (${task.tpl_playbook})` : templateName(task),
    ],
    ['Limit', taskLimit(task)],
    ['Message', task.message],
    ['Commit', [task.commit_hash?.slice(0, 10), task.commit_message].filter(Boolean).join(' ')],
    ['Origin', taskOrigin(task)],
    ['Created', parseTime(task.created)?.toISOString()],
    ['Started', parseTime(task.start)?.toISOString()],
    ['Ended', parseTime(task.end)?.toISOString()],
    ['Duration', taskDuration(task, now)],
    ['URL', url],
  ];
  const header = rows
    .filter(([, value]) => value)
    .map(([key, value]) => `${`${key}:`.padEnd(10)}${value}`);
  const body = stripAnsi(output).replace(/\s+$/, '');
  return [
    `Task #${task.id} ${templateName(task)}`,
    ...header,
    '-'.repeat(72),
    body || '(no output yet)',
    '',
  ].join('\n');
}

module.exports = {
  STATUS_COLORS,
  STATUS_ICONS,
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
};
