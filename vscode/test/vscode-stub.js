// Minimal in-memory stand-in for the `vscode` module, enough to drive
// src/extension.js under `node --test`. Every UI call is recorded in
// `stub.calls`; answers to modal prompts are queued in `stub.answers`.

const Module = require('node:module');

class EventEmitter {
  constructor() {
    this.listeners = [];
    this.fired = [];
    this.event = (listener) => {
      this.listeners.push(listener);
      return { dispose() {} };
    };
  }

  fire(value) {
    this.fired.push(value);
    for (const listener of this.listeners) listener(value);
  }
}

class TreeItem {
  constructor(label, collapsibleState = 0) {
    this.label = label;
    this.collapsibleState = collapsibleState;
  }
}

class ThemeIcon {
  constructor(id, color) {
    this.id = id;
    this.color = color;
  }
}

class ThemeColor {
  constructor(id) {
    this.id = id;
  }
}

class MarkdownString {
  constructor(value) {
    this.value = value;
  }
}

class Uri {
  constructor(scheme, path, fsPath = path) {
    this.scheme = scheme;
    this.path = path;
    this.fsPath = fsPath;
  }

  static from({ scheme, path }) {
    return new Uri(scheme, path);
  }

  static parse(value) {
    return new Uri(value.split(':')[0], value);
  }

  static file(fsPath) {
    return new Uri('file', fsPath, fsPath);
  }

  toString() {
    return `${this.scheme}:${this.path}`;
  }
}

const stub = {
  calls: [],
  answers: [],
  settings: {},
  commands: new Map(),
  documents: [],
  configListeners: [],
  docProviders: new Map(),
  focused: true,
  folders: undefined,
  reset() {
    stub.calls = [];
    stub.answers = [];
    stub.settings = {};
    stub.commands = new Map();
    stub.documents = [];
    stub.configListeners = [];
    stub.docProviders = new Map();
    stub.focused = true;
    stub.folders = undefined;
  },
  record(name, ...args) {
    stub.calls.push([name, ...args]);
  },
  callsOf(name) {
    return stub.calls.filter(([n]) => n === name).map(([, ...args]) => args);
  },
};

const vscode = {
  EventEmitter,
  TreeItem,
  ThemeIcon,
  ThemeColor,
  MarkdownString,
  Uri,
  TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
  window: {
    get state() {
      return { focused: stub.focused };
    },
    createTreeView(id, options) {
      const view = { id, ...options, dispose() {} };
      stub.record('createTreeView', view);
      return view;
    },
    async showWarningMessage(message, options, ...items) {
      stub.record('showWarningMessage', message, options, items);
      return stub.answers.shift();
    },
    async showErrorMessage(message) {
      stub.record('showErrorMessage', message);
    },
    setStatusBarMessage(message, timeout) {
      stub.record('setStatusBarMessage', message, timeout);
    },
    async showTextDocument(doc, options) {
      stub.record('showTextDocument', doc, options);
    },
  },
  workspace: {
    get workspaceFolders() {
      return stub.folders;
    },
    get textDocuments() {
      return stub.documents;
    },
    getConfiguration(section) {
      return { get: (key, fallback) => stub.settings[`${section}.${key}`] ?? fallback };
    },
    registerTextDocumentContentProvider(scheme, provider) {
      stub.docProviders.set(scheme, provider);
      return { dispose() {} };
    },
    async openTextDocument(uri) {
      const doc = { uri };
      stub.documents.push(doc);
      return doc;
    },
    onDidChangeWorkspaceFolders() {
      return { dispose() {} };
    },
    onDidChangeConfiguration(listener) {
      stub.configListeners.push(listener);
      return { dispose() {} };
    },
  },
  languages: {
    async setTextDocumentLanguage(doc, language) {
      stub.record('setTextDocumentLanguage', doc, language);
      return doc;
    },
  },
  commands: {
    registerCommand(id, handler) {
      stub.commands.set(id, handler);
      return { dispose() {} };
    },
  },
  env: {
    async openExternal(uri) {
      stub.record('openExternal', uri.toString());
      return true;
    },
  },
};

// Resolve `require('vscode')` to this module for everything loaded after.
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function resolve(request, ...rest) {
  if (request === 'vscode') return __filename;
  return originalResolve.call(this, request, ...rest);
};

module.exports = vscode;
module.exports.stub = stub;
