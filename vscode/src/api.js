// @ts-check
// Thin client over the Semaphore REST API (/api), Bearer auth like `sem`.
//
// Transport is node:http(s), not the global fetch: inside VS Code the https
// module is patched to honour the OS trust store and the proxy settings
// (semacli's use_system_ca), and it is the only way to apply
// verify_ssl = false without bundling undici. No runtime dependencies.

const http = require('node:http');
const https = require('node:https');

/**
 * Subset of a Semaphore task (GET /project/{pid}/tasks/last).
 * @typedef {object} Task
 * @property {number} id
 * @property {number} template_id
 * @property {string} status
 * @property {string} [tpl_alias]
 * @property {string} [tpl_playbook]
 * @property {string} [created]
 * @property {string | null} [start]
 * @property {string | null} [end]
 * @property {string} [message]
 * @property {string} [commit_hash]
 * @property {string} [commit_message]
 * @property {string} [limit]
 * @property {number | null} [schedule_id]
 * @property {number | null} [user_id]
 * @property {{ limit?: string[] | string, tags?: string[] | string, skip_tags?: string[] | string, debug_level?: number, dry_run?: boolean, diff?: boolean }} [params]
 */

/**
 * @typedef {object} RawResponse
 * @property {number} status
 * @property {string} body
 */

/**
 * @typedef {object} TransportRequest
 * @property {string} method
 * @property {Record<string, string>} headers
 * @property {string} [body]
 * @property {number} timeoutMs
 * @property {boolean} verifySsl
 */

/** @typedef {(url: string, req: TransportRequest) => Promise<RawResponse>} Transport */

/** Error carrying the HTTP status (0 for network errors). */
class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status
   */
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** @type {Transport} */
function nodeTransport(url, req) {
  const target = new URL(url);
  const mod = target.protocol === 'http:' ? http : https;
  return new Promise((resolve, reject) => {
    const request = mod.request(
      target,
      {
        method: req.method,
        headers: req.headers,
        timeout: req.timeoutMs,
        ...(target.protocol === 'https:' && !req.verifySsl ? { rejectUnauthorized: false } : {}),
      },
      (res) => {
        /** @type {Buffer[]} */
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () =>
          resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString('utf8') }),
        );
        res.on('error', reject);
      },
    );
    request.on('timeout', () =>
      request.destroy(new Error(`timeout after ${req.timeoutMs / 1000}s`)),
    );
    request.on('error', reject);
    request.end(req.body);
  });
}

class SemaphoreApi {
  /**
   * @param {import('./config').SemaphoreConfig} cfg
   * @param {Transport} [transport]
   */
  constructor(cfg, transport = nodeTransport) {
    this.cfg = cfg;
    this.transport = transport;
  }

  /** @returns {string} */
  get projectPath() {
    return `/project/${this.cfg.project}`;
  }

  /**
   * @param {string} method
   * @param {string} path below /api
   * @param {unknown} [body]
   * @returns {Promise<string>} raw response body
   */
  async request(method, path, body) {
    /** @type {Record<string, string>} */
    const headers = { Authorization: `Bearer ${this.cfg.token}`, Accept: 'application/json' };
    const payload = body === undefined ? undefined : JSON.stringify(body);
    if (payload !== undefined) headers['Content-Type'] = 'application/json';
    let resp;
    try {
      resp = await this.transport(`${this.cfg.url}/api${path}`, {
        method,
        headers,
        body: payload,
        timeoutMs: this.cfg.timeout * 1000,
        verifySsl: this.cfg.verifySsl,
      });
    } catch (err) {
      throw new ApiError(`${method} ${path}: ${err instanceof Error ? err.message : err}`, 0);
    }
    if (resp.status < 200 || resp.status >= 300) {
      const detail = resp.body.trim().slice(0, 200);
      throw new ApiError(
        `${method} ${path} -> HTTP ${resp.status}${detail ? ` (${detail})` : ''}`,
        resp.status,
      );
    }
    return resp.body;
  }

  /**
   * @param {string} path
   * @returns {Promise<any>}
   */
  async getJson(path) {
    const body = await this.request('GET', path);
    try {
      return JSON.parse(body);
    } catch {
      throw new ApiError(`GET ${path}: response is not JSON`, 0);
    }
  }

  /**
   * Last 200 tasks of the project, newest first (Semaphore's own cap).
   * @returns {Promise<Task[]>}
   */
  async listTasks() {
    const tasks = await this.getJson(`${this.projectPath}/tasks/last`);
    if (!Array.isArray(tasks)) throw new ApiError('GET /tasks/last: expected a list', 0);
    return tasks;
  }

  /**
   * @param {number} id
   * @returns {Promise<Task>}
   */
  getTask(id) {
    return this.getJson(`${this.projectPath}/tasks/${id}`);
  }

  /**
   * Plain-text task output (the CLI's `sem task output --raw`).
   * @param {number} id
   * @returns {Promise<string>}
   */
  getRawOutput(id) {
    return this.request('GET', `${this.projectPath}/tasks/${id}/raw_output`);
  }

  /**
   * @param {number} id
   * @param {boolean} [force] kill without waiting for a graceful stop
   * @returns {Promise<void>}
   */
  async stopTask(id, force = false) {
    await this.request('POST', `${this.projectPath}/tasks/${id}/stop`, { force });
  }

  /**
   * Web UI URL of the project history, or of one task in it.
   * @param {number} [taskId]
   * @returns {string}
   */
  webUrl(taskId) {
    const url = `${this.cfg.url}${this.projectPath}/history`;
    return taskId === undefined ? url : `${url}?t=${taskId}`;
  }
}

module.exports = { ApiError, SemaphoreApi, nodeTransport };
