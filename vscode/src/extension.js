// @ts-check
// VS Code glue: sidebar tree of the running / finished Semaphore tasks of
// the project set in semacli.ini, a read-only task detail document (header
// + raw output, refreshed while the task runs) and "Stop task" (ken #1131).

const vscode = require('vscode');
const { loadConfig } = require('./config');
const { SemaphoreApi } = require('./api');
const {
  STATUS_COLORS,
  STATUS_ICONS,
  detailText,
  isFinal,
  splitTasks,
  taskDescription,
  taskLabel,
  taskLimit,
} = require('./tasks');

const SCHEME = 'semacli-task';

/** @typedef {import('./api').Task} Task */
/**
 * @typedef {{ kind: 'group', key: 'running' | 'finished', tasks: Task[] }
 *   | { kind: 'task', task: Task }
 *   | { kind: 'message', text: string }} Node
 */
/**
 * @typedef {object} Deps
 * @property {(dir: string) => import('./config').SemaphoreConfig} loadConfig
 * @property {(cfg: import('./config').SemaphoreConfig) => SemaphoreApi} makeApi
 * @property {() => Date} now
 */

/** @type {Deps} */
const DEFAULT_DEPS = {
  loadConfig: (dir) => loadConfig(dir),
  makeApi: (cfg) => new SemaphoreApi(cfg),
  now: () => new Date(),
};

/**
 * @param {unknown} err
 * @returns {string}
 */
function errorText(err) {
  return err instanceof Error ? err.message : String(err);
}

/**
 * Task id carried by a detail document URI (`semacli-task:/<id>/<title>.log`).
 * @param {vscode.Uri} uri
 * @returns {number | null}
 */
function taskIdOf(uri) {
  const id = Number(uri.path.split('/')[1]);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** @implements {vscode.TreeDataProvider<Node>} */
class TaskTreeProvider {
  /** @param {Deps} deps */
  constructor(deps) {
    this.deps = deps;
    /** @type {vscode.EventEmitter<Node | undefined>} */
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.emitter.event;
    /** @type {SemaphoreApi | null} */
    this.api = null;
    /** @type {{ running: Task[], finished: Task[] } | null} */
    this.groups = null;
    /** @type {string | null} */
    this.error = null;
    /** @type {Map<number, Task>} last listed row per task id */
    this.known = new Map();
  }

  /** Reload the config (picks up semacli.ini edits) and the task list. */
  async reload() {
    this.groups = null;
    this.error = null;
    const folder = vscode.workspace.workspaceFolders?.[0];
    try {
      if (!folder) throw new Error('Open a folder that contains a semacli.ini.');
      this.api = this.deps.makeApi(this.deps.loadConfig(folder.uri.fsPath));
      const limit = vscode.workspace.getConfiguration('semacli').get('finishedLimit', 50);
      const tasks = await this.api.listTasks();
      for (const task of tasks) this.known.set(task.id, task);
      this.groups = splitTasks(tasks, limit);
    } catch (err) {
      this.error = errorText(err);
    }
    this.emitter.fire(undefined);
  }

  /**
   * @param {Node} node
   * @returns {vscode.TreeItem}
   */
  getTreeItem(node) {
    if (node.kind === 'message') {
      const item = new vscode.TreeItem(node.text);
      item.iconPath = new vscode.ThemeIcon('warning');
      item.tooltip = node.text;
      return item;
    }
    if (node.kind === 'group') {
      const item = new vscode.TreeItem(
        node.key === 'running' ? 'Running' : 'Finished',
        vscode.TreeItemCollapsibleState.Expanded,
      );
      item.id = `group:${node.key}`;
      item.description = String(node.tasks.length);
      return item;
    }
    const { task } = node;
    const now = this.deps.now();
    const item = new vscode.TreeItem(taskLabel(task));
    item.id = `task:${task.id}`;
    item.description = taskDescription(task, now);
    const color = STATUS_COLORS[/** @type {keyof typeof STATUS_COLORS} */ (task.status)];
    item.iconPath = new vscode.ThemeIcon(
      STATUS_ICONS[/** @type {keyof typeof STATUS_ICONS} */ (task.status)] ?? 'circle-outline',
      color ? new vscode.ThemeColor(color) : undefined,
    );
    const limit = taskLimit(task);
    item.tooltip = new vscode.MarkdownString(
      `**${taskLabel(task)}**\n\n${item.description}${limit ? `\n\nlimit: \`${limit}\`` : ''}`,
    );
    item.contextValue = isFinal(task.status) ? 'task.final' : 'task.active';
    item.command = { command: 'semacli.showTask', title: 'Show task detail', arguments: [node] };
    return item;
  }

  /**
   * @param {Node} [node]
   * @returns {Node[]}
   */
  getChildren(node) {
    if (node?.kind === 'group') return node.tasks.map((task) => ({ kind: 'task', task }));
    if (node) return [];
    if (this.error) return [{ kind: 'message', text: this.error }];
    if (!this.groups) return [];
    return [
      { kind: 'group', key: 'running', tasks: this.groups.running },
      { kind: 'group', key: 'finished', tasks: this.groups.finished },
    ];
  }
}

/**
 * Read-only `semacli-task:` documents. Each one is rendered once, then
 * re-rendered on refresh while its task has not reached a final state.
 * @implements {vscode.TextDocumentContentProvider}
 */
class TaskDocumentProvider {
  /**
   * @param {TaskTreeProvider} tree
   * @param {Deps} deps
   */
  constructor(tree, deps) {
    this.tree = tree;
    this.deps = deps;
    /** @type {vscode.EventEmitter<vscode.Uri>} */
    this.emitter = new vscode.EventEmitter();
    this.onDidChange = this.emitter.event;
    /** @type {Map<number, string>} last status rendered per task id */
    this.statuses = new Map();
  }

  /**
   * @param {vscode.Uri} uri
   * @returns {Promise<string>}
   */
  async provideTextDocumentContent(uri) {
    const id = taskIdOf(uri);
    const { api } = this.tree;
    if (id === null || !api) return 'semacli: no task to show (refresh the Tasks view).\n';
    try {
      const [fresh, output] = await Promise.all([api.getTask(id), api.getRawOutput(id)]);
      // GET /tasks/{id} omits the tpl_* fields the list carries: keep them.
      const task = { ...this.tree.known.get(id), ...fresh };
      this.statuses.set(id, task.status);
      return detailText(task, output, api.webUrl(id), this.deps.now());
    } catch (err) {
      return `semacli: cannot load task #${id}: ${errorText(err)}\n`;
    }
  }

  /** Re-render the open detail documents of tasks that are still active. */
  refreshActive() {
    for (const doc of vscode.workspace.textDocuments) {
      if (doc.uri.scheme !== SCHEME) continue;
      const id = taskIdOf(doc.uri);
      const status = id === null ? undefined : this.statuses.get(id);
      if (status === undefined || !isFinal(status)) this.emitter.fire(doc.uri);
    }
  }
}

/** Wires the views, documents and commands; `deps` are swapped in tests. */
class Controller {
  /**
   * @param {vscode.ExtensionContext} context
   * @param {Deps} deps
   */
  constructor(context, deps) {
    this.context = context;
    this.tree = new TaskTreeProvider(deps);
    this.docs = new TaskDocumentProvider(this.tree, deps);
    this.view = vscode.window.createTreeView('semacli.tasks', { treeDataProvider: this.tree });
    /** @type {ReturnType<typeof setInterval> | null} */
    this.timer = null;
  }

  /** Tree + open detail documents, both reloaded from the API. */
  async refresh() {
    await this.tree.reload();
    const running = this.tree.groups?.running.length ?? 0;
    this.view.badge = running
      ? { value: running, tooltip: `${running} running task${running > 1 ? 's' : ''}` }
      : undefined;
    const cfg = this.tree.api?.cfg;
    // Like the CLI's stderr warning: verify_ssl = false stays visible.
    this.view.description = cfg
      ? `project ${cfg.project}${cfg.verifySsl ? '' : ' · TLS NOT VERIFIED'}`
      : undefined;
    this.docs.refreshActive();
  }

  /** (Re)arm the periodic refresh from the `semacli.autoRefreshSeconds` setting. */
  armTimer() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    const seconds = vscode.workspace.getConfiguration('semacli').get('autoRefreshSeconds', 15);
    if (seconds > 0) {
      this.timer = setInterval(() => {
        if (vscode.window.state.focused) void this.refresh();
      }, seconds * 1000);
    }
  }

  /** @param {Node} node */
  async showTask(node) {
    if (node?.kind !== 'task') return;
    const { task } = node;
    const uri = vscode.Uri.from({ scheme: SCHEME, path: `/${task.id}/${taskLabel(task)}.log` });
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.languages.setTextDocumentLanguage(doc, 'log');
    await vscode.window.showTextDocument(doc, { preview: true });
  }

  /** @param {Node} [node] */
  openInBrowser(node) {
    const { api } = this.tree;
    if (!api) return;
    const url = api.webUrl(node?.kind === 'task' ? node.task.id : undefined);
    void vscode.env.openExternal(vscode.Uri.parse(url));
  }

  /**
   * Stop after a modal confirmation; a task already `stopping` is offered a
   * force stop (Semaphore kills the process instead of waiting).
   * @param {Node} node
   */
  async stopTask(node) {
    const { api } = this.tree;
    if (node?.kind !== 'task' || !api) return;
    const { task } = node;
    const force = task.status === 'stopping';
    const action = force ? 'Force stop' : 'Stop';
    const answer = await vscode.window.showWarningMessage(
      `${action} task ${taskLabel(task)} (${task.status})?`,
      { modal: true },
      action,
    );
    if (answer !== action) return;
    try {
      await api.stopTask(task.id, force);
      vscode.window.setStatusBarMessage(
        `semacli: ${action.toLowerCase()} #${task.id} requested`,
        3000,
      );
    } catch (err) {
      void vscode.window.showErrorMessage(`semacli: ${errorText(err)}`);
    }
    await this.refresh();
  }

  register() {
    const cmd = vscode.commands.registerCommand;
    this.context.subscriptions.push(
      this.view,
      vscode.workspace.registerTextDocumentContentProvider(SCHEME, this.docs),
      cmd('semacli.refresh', () => this.refresh()),
      cmd('semacli.openSemaphore', () => this.openInBrowser()),
      cmd('semacli.openTask', (/** @type {Node} */ node) => this.openInBrowser(node)),
      cmd('semacli.showTask', (/** @type {Node} */ node) => this.showTask(node)),
      cmd('semacli.stopTask', (/** @type {Node} */ node) => this.stopTask(node)),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.refresh()),
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration('semacli')) {
          this.armTimer();
          void this.refresh();
        }
      }),
      { dispose: () => this.timer && clearInterval(this.timer) },
    );
    this.armTimer();
    return this.refresh();
  }
}

/**
 * @param {vscode.ExtensionContext} context
 * @param {Deps} [deps]
 * @returns {Controller}
 */
function activate(context, deps = DEFAULT_DEPS) {
  const controller = new Controller(context, deps);
  void controller.register();
  return controller;
}

function deactivate() {}

module.exports = { activate, deactivate, taskIdOf };
