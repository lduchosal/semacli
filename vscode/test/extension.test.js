const test = require('node:test');
const assert = require('node:assert/strict');
const vscode = require('./vscode-stub');
const { activate, deactivate, taskIdOf } = require('../src/extension');

const { stub } = vscode;
const NOW = new Date('2026-10-02T12:00:00Z');
const cfg = {
  configFile: 'f',
  url: 'https://s',
  token: 't',
  project: 1,
  timeout: 30,
  verifySsl: true,
};

/** Fake SemaphoreApi recording what the extension asks for. */
function fakeApi(tasks) {
  const api = {
    cfg,
    tasks,
    stopped: [],
    failList: null,
    failStop: null,
    failTask: null,
    async listTasks() {
      if (api.failList) throw api.failList;
      return api.tasks;
    },
    async getTask(id) {
      if (api.failTask) throw api.failTask;
      // Like Semaphore: the single-task GET has no tpl_* fields.
      const { tpl_alias, ...task } = api.tasks.find((x) => x.id === id) ?? { id };
      return task;
    },
    async getRawOutput(id) {
      return `output of ${id}`;
    },
    async stopTask(id, force) {
      if (api.failStop) throw api.failStop;
      api.stopped.push([id, force]);
    },
    webUrl(id) {
      return id === undefined
        ? 'https://s/project/1/history'
        : `https://s/project/1/history?t=${id}`;
    },
  };
  return api;
}

const TASKS = [
  {
    id: 3,
    status: 'success',
    template_id: 1,
    tpl_alias: 'mtree',
    start: '2026-10-02T11:00:00Z',
    end: '2026-10-02T11:00:30Z',
  },
  {
    id: 4,
    status: 'running',
    template_id: 1,
    tpl_alias: 'pkg',
    start: '2026-10-02T11:59:00Z',
    params: { limit: ['h1'] },
  },
  { id: 5, status: 'stopping', template_id: 1, tpl_alias: 'dns' },
  { id: 6, status: 'mystery', template_id: 1, tpl_alias: 'odd' },
];

/** Activate against a fresh stub; returns the controller and the fake API. */
async function setup({ tasks = TASKS, loadConfig = () => cfg, folders = true } = {}) {
  stub.reset();
  stub.folders = folders ? [{ uri: vscode.Uri.file('/ws') }] : undefined;
  const api = fakeApi(tasks);
  const context = { subscriptions: [] };
  const controller = activate(context, { loadConfig, makeApi: () => api, now: () => NOW });
  await controller.refresh();
  return { controller, api, context };
}

function roots(controller) {
  return controller.tree.getChildren();
}

test('tree: Running / Finished groups with counts, badge and description', async (t) => {
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  const [running, finished] = roots(controller);
  assert.equal(running.key, 'running');
  assert.deepEqual(
    running.tasks.map((x) => x.id),
    [4, 5, 6],
  );
  assert.deepEqual(
    finished.tasks.map((x) => x.id),
    [3],
  );
  const group = controller.tree.getTreeItem(running);
  assert.equal(group.label, 'Running');
  assert.equal(group.description, '3');
  assert.equal(controller.tree.getTreeItem(finished).label, 'Finished');
  assert.deepEqual(controller.view.badge, { value: 3, tooltip: '3 running tasks' });
  assert.equal(controller.view.description, 'project 1');
  controller.tree.api.cfg = { ...cfg, verifySsl: false };
  const { api } = controller.tree;
  controller.tree.deps.makeApi = () => api;
  controller.tree.deps.loadConfig = () => api.cfg;
  await controller.refresh();
  assert.equal(controller.view.description, 'project 1 · TLS NOT VERIFIED');
});

test('tree: task items carry label, icon, colour, context value and command', async (t) => {
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  const [running, finished] = roots(controller);
  const [runningNode] = controller.tree.getChildren(running);
  const item = controller.tree.getTreeItem(runningNode);
  assert.equal(item.label, '#4 pkg');
  assert.equal(item.description, 'running · 1m00s');
  assert.equal(item.iconPath.id, 'sync~spin');
  assert.equal(item.iconPath.color, undefined);
  assert.equal(item.contextValue, 'task.active');
  assert.match(item.tooltip.value, /limit: `h1`/);
  assert.deepEqual(item.command.arguments, [runningNode]);

  const done = controller.tree.getTreeItem(controller.tree.getChildren(finished)[0]);
  assert.equal(done.contextValue, 'task.final');
  assert.equal(done.iconPath.color.id, 'testing.iconPassed');
  assert.doesNotMatch(done.tooltip.value, /limit/);

  const odd = controller.tree.getTreeItem({ kind: 'task', task: TASKS[3] });
  assert.equal(odd.iconPath.id, 'circle-outline');
  assert.deepEqual(controller.tree.getChildren(runningNode), []);
});

test('tree: one running task, singular badge; none, no badge', async (t) => {
  const one = await setup({ tasks: [TASKS[1]] });
  t.after(() => one.controller.timer && clearInterval(one.controller.timer));
  assert.deepEqual(one.controller.view.badge, { value: 1, tooltip: '1 running task' });
  const none = await setup({ tasks: [TASKS[0]] });
  t.after(() => none.controller.timer && clearInterval(none.controller.timer));
  assert.equal(none.controller.view.badge, undefined);
});

test('tree: config and API problems are shown as a message node', async (t) => {
  const bad = await setup({
    loadConfig: () => {
      throw new Error('No semacli.ini found');
    },
  });
  t.after(() => bad.controller.timer && clearInterval(bad.controller.timer));
  const [msg] = roots(bad.controller);
  assert.deepEqual(msg, { kind: 'message', text: 'No semacli.ini found' });
  assert.equal(bad.controller.tree.getTreeItem(msg).iconPath.id, 'warning');
  assert.equal(bad.controller.view.description, undefined);

  const noFolder = await setup({ folders: false });
  t.after(() => noFolder.controller.timer && clearInterval(noFolder.controller.timer));
  assert.match(roots(noFolder.controller)[0].text, /Open a folder/);

  const { controller, api } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  api.failList = 'unreachable';
  await controller.refresh();
  assert.deepEqual(roots(controller), [{ kind: 'message', text: 'unreachable' }]);
});

test('tree: nothing loaded yet means no children', async (t) => {
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  controller.tree.groups = null;
  controller.tree.error = null;
  assert.deepEqual(roots(controller), []);
});

test('showTask: opens a read-only log document rendered from the API', async (t) => {
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  await stub.commands.get('semacli.showTask')({ kind: 'task', task: TASKS[1] });
  const [[doc, options]] = stub.callsOf('showTextDocument');
  assert.equal(doc.uri.scheme, 'semacli-task');
  assert.equal(doc.uri.path, '/4/#4 pkg.log');
  assert.deepEqual(options, { preview: true });
  assert.equal(stub.callsOf('setTextDocumentLanguage')[0][1], 'log');

  const provider = stub.docProviders.get('semacli-task');
  const text = await provider.provideTextDocumentContent(doc.uri);
  assert.match(text, /^Task #4 pkg\nStatus: {3}running/);
  assert.match(text, /URL: {6}https:\/\/s\/project\/1\/history\?t=4/);
  assert.match(text, /output of 4\n$/);

  await stub.commands.get('semacli.showTask')({ kind: 'message', text: 'x' });
  assert.equal(stub.callsOf('showTextDocument').length, 1);
});

test('documents: errors and unknown URIs render a message, never throw', async (t) => {
  const { controller, api } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  const provider = stub.docProviders.get('semacli-task');
  const bogus = vscode.Uri.from({ scheme: 'semacli-task', path: '/abc/x.log' });
  assert.match(await provider.provideTextDocumentContent(bogus), /no task to show/);
  api.failTask = new Error('HTTP 404');
  const uri = vscode.Uri.from({ scheme: 'semacli-task', path: '/4/x.log' });
  assert.equal(
    await provider.provideTextDocumentContent(uri),
    'semacli: cannot load task #4: HTTP 404\n',
  );
  controller.tree.api = null;
  assert.match(await provider.provideTextDocumentContent(uri), /no task to show/);
});

test('refresh: re-renders open documents of active tasks only', async (t) => {
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  const provider = stub.docProviders.get('semacli-task');
  const uri = (id) => vscode.Uri.from({ scheme: 'semacli-task', path: `/${id}/x.log` });
  stub.documents.push(
    { uri: uri(3) },
    { uri: uri(4) },
    { uri: uri(99) },
    { uri: vscode.Uri.file('/a') },
  );
  await provider.provideTextDocumentContent(uri(3));
  await provider.provideTextDocumentContent(uri(4));
  provider.emitter.fired = [];
  await controller.refresh();
  // #3 is final (rendered once, never changes); #4 runs; #99 never rendered.
  assert.deepEqual(
    provider.emitter.fired.map((u) => u.path),
    ['/4/x.log', '/99/x.log'],
  );
});

test('stopTask: confirmed stop, then refresh', async (t) => {
  const { controller, api } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  stub.answers.push('Stop');
  await stub.commands.get('semacli.stopTask')({ kind: 'task', task: TASKS[1] });
  const [[message, options, items]] = stub.callsOf('showWarningMessage');
  assert.equal(message, 'Stop task #4 pkg (running)?');
  assert.deepEqual(options, { modal: true });
  assert.deepEqual(items, ['Stop']);
  assert.deepEqual(api.stopped, [[4, false]]);
  assert.equal(stub.callsOf('setStatusBarMessage')[0][0], 'semacli: stop #4 requested');
});

test('stopTask: a stopping task is offered a force stop', async (t) => {
  const { controller, api } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  stub.answers.push('Force stop');
  await stub.commands.get('semacli.stopTask')({ kind: 'task', task: TASKS[2] });
  assert.deepEqual(api.stopped, [[5, true]]);
});

test('stopTask: cancelled, failing, or not a task', async (t) => {
  const { controller, api } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  stub.answers.push(undefined);
  await stub.commands.get('semacli.stopTask')({ kind: 'task', task: TASKS[1] });
  assert.deepEqual(api.stopped, []);

  api.failStop = new Error('HTTP 403');
  stub.answers.push('Stop');
  await stub.commands.get('semacli.stopTask')({ kind: 'task', task: TASKS[1] });
  assert.deepEqual(stub.callsOf('showErrorMessage'), [['semacli: HTTP 403']]);

  await stub.commands.get('semacli.stopTask')(undefined);
  controller.tree.api = null;
  await stub.commands.get('semacli.stopTask')({ kind: 'task', task: TASKS[1] });
  assert.equal(stub.callsOf('showWarningMessage').length, 2);
});

test('open in browser: project history or one task', async (t) => {
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  await stub.commands.get('semacli.openSemaphore')();
  await stub.commands.get('semacli.openTask')({ kind: 'task', task: TASKS[0] });
  assert.deepEqual(stub.callsOf('openExternal'), [
    ['https:https://s/project/1/history'],
    ['https:https://s/project/1/history?t=3'],
  ]);
  controller.tree.api = null;
  await stub.commands.get('semacli.openSemaphore')();
  assert.equal(stub.callsOf('openExternal').length, 2);
});

test('refresh command and auto-refresh timer follow the settings', async (t) => {
  const { controller, api, context } = await setup();
  assert.ok(controller.timer, 'armed with the 15s default');
  api.tasks = [TASKS[0]];
  await stub.commands.get('semacli.refresh')();
  assert.equal(controller.view.badge, undefined);

  stub.settings['semacli.autoRefreshSeconds'] = 0;
  for (const listener of stub.configListeners) listener({ affectsConfiguration: () => true });
  assert.equal(controller.timer, null);
  for (const listener of stub.configListeners) listener({ affectsConfiguration: () => false });

  // Every subscription disposes cleanly (timer included).
  for (const sub of context.subscriptions) sub.dispose();
  t.after(() => controller.timer && clearInterval(controller.timer));
});

test('auto-refresh ticks only while the window is focused', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] });
  const { controller, api } = await setup();
  let calls = 0;
  const original = api.listTasks;
  api.listTasks = async () => {
    calls += 1;
    return original();
  };
  stub.focused = false;
  t.mock.timers.tick(15000);
  assert.equal(calls, 0);
  stub.focused = true;
  t.mock.timers.tick(15000);
  assert.equal(calls, 1);
  clearInterval(controller.timer);
});

test('finishedLimit setting caps the Finished group', async (t) => {
  stub.reset();
  const { controller } = await setup();
  t.after(() => controller.timer && clearInterval(controller.timer));
  stub.settings['semacli.finishedLimit'] = 0;
  await controller.refresh();
  assert.deepEqual(roots(controller)[1].tasks, []);
});

test('taskIdOf / deactivate', () => {
  assert.equal(taskIdOf(vscode.Uri.from({ scheme: 's', path: '/12/x.log' })), 12);
  assert.equal(taskIdOf(vscode.Uri.from({ scheme: 's', path: '/0/x.log' })), null);
  assert.equal(deactivate(), undefined);
});

test('activate without deps uses the real config loader', async (t) => {
  stub.reset();
  stub.folders = [{ uri: vscode.Uri.file('/nonexistent-semacli-ws') }];
  const controller = activate({ subscriptions: [] });
  t.after(() => controller.timer && clearInterval(controller.timer));
  await controller.refresh();
  // Either no semacli.ini at all, or ~/.semacli.ini incomplete: a message, no crash.
  const [first] = roots(controller);
  assert.ok(first.kind === 'message' || first.kind === 'group');
});
