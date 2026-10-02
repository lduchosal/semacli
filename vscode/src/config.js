// @ts-check
// Resolve the Semaphore connection exactly like the `sem` CLI does
// (semacli/core/config.py): semacli.ini, its optional `.env`, the [auth]
// token methods and the secure-by-default [settings]. Pure Node — no
// `vscode` import — so it is testable with `node --test`.
//
// One deliberate difference: VS Code has no cwd, so the "current directory"
// step walks up from the workspace folder (opening a sub-folder of the
// project still finds its semacli.ini).

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const CONFIG_NAME = 'semacli.ini';
const DEFAULT_ENV_VAR = 'SEMAPHORE_TOKEN';
const DEFAULT_TIMEOUT = 30;
const TRUE_WORDS = new Set(['1', 'yes', 'true', 'on']);
const FALSE_WORDS = new Set(['0', 'no', 'false', 'off']);

/**
 * @typedef {object} SemaphoreConfig
 * @property {string} configFile absolute path of the semacli.ini in use
 * @property {string} url base URL, no trailing slash
 * @property {string | null} token
 * @property {number | null} project
 * @property {number} timeout seconds
 * @property {boolean} verifySsl
 */

/** Configuration error with a message meant for the user. */
class ConfigError extends Error {}

/**
 * Walk up from `start` looking for a file named `name`.
 * @param {string} start
 * @param {string} name
 * @returns {string | null}
 */
function findFileUpwards(start, name) {
  let cur = path.resolve(start);
  for (;;) {
    const candidate = path.join(cur, name);
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

/**
 * semacli's search order, with the cwd step replaced by a walk up from the
 * workspace folder: ./semacli.ini (upwards), ~/.semacli.ini,
 * /usr/local/etc/semacli.ini.
 * @param {string} startDir
 * @param {string} [home]
 * @returns {string | null}
 */
function findConfigFile(startDir, home = os.homedir()) {
  const candidates = [path.join(home, `.${CONFIG_NAME}`), path.join('/usr/local/etc', CONFIG_NAME)];
  return findFileUpwards(startDir, CONFIG_NAME) ?? candidates.find((p) => fs.existsSync(p)) ?? null;
}

/**
 * configparser subset: `[section]`, `key = value` / `key: value`, full-line
 * `#`/`;` comments, case-insensitive keys, indented continuation lines
 * ignored. Same interpolation-free reading as semacli.
 * @param {string} text
 * @returns {Record<string, Record<string, string>>}
 */
function parseIni(text) {
  /** @type {Record<string, Record<string, string>>} */
  const sections = {};
  /** @type {Record<string, string> | null} */
  let current = null;
  for (const raw of text.replace(/^﻿/, '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || line.startsWith(';') || /^\s/.test(raw)) continue;
    const section = /^\[(.+)\]$/.exec(line);
    if (section) {
      const name = section[1].trim();
      sections[name] ??= {};
      current = sections[name];
      continue;
    }
    const kv = /^([^=:]+)[=:](.*)$/.exec(line);
    if (kv && current) current[kv[1].trim().toLowerCase()] = kv[2].trim();
  }
  return sections;
}

/**
 * python-dotenv subset: `KEY=value`, optional `export `, single/double
 * quoted values (escapes `\n` `\"` in double quotes), ` #` comments after
 * unquoted values.
 * @param {string} text
 * @returns {Record<string, string>}
 */
function parseDotenv(text) {
  /** @type {Record<string, string>} */
  const result = {};
  for (const raw of text.replace(/^﻿/, '').split(/\r?\n/)) {
    const m = /^\s*(?:export\s+)?([A-Za-z_][\w.-]*)\s*=\s*(.*?)\s*$/.exec(raw);
    if (m) result[m[1]] = dotenvValue(m[2]);
  }
  return result;
}

/**
 * @param {string} value raw right-hand side, already trimmed
 * @returns {string}
 */
function dotenvValue(value) {
  const quoted = /^(['"])(.*)\1/.exec(value);
  if (quoted) {
    return quoted[1] === "'"
      ? quoted[2]
      : quoted[2].replaceAll('\\n', '\n').replaceAll('\\"', '"').replaceAll('\\\\', '\\');
  }
  return value.replace(/\s+#.*$/, '');
}

/**
 * configparser getboolean().
 * @param {string | undefined} raw
 * @param {boolean} fallback
 * @param {string} key for the error message
 * @returns {boolean}
 */
function parseBool(raw, fallback, key) {
  if (raw === undefined) return fallback;
  const word = raw.toLowerCase();
  if (TRUE_WORDS.has(word)) return true;
  if (FALSE_WORDS.has(word)) return false;
  throw new ConfigError(`[settings] ${key}: not a boolean: ${raw}`);
}

/**
 * Optional positive integer.
 * @param {string | undefined} raw
 * @param {string} key for the error message
 * @returns {number | null}
 */
function parseInteger(raw, key) {
  if (!raw) return null;
  if (!/^\d+$/.test(raw)) throw new ConfigError(`${key}: not an integer: ${raw}`);
  return Number(raw);
}

/**
 * The environment semacli would see: the process env, completed (never
 * overridden) by the `.env` file when [settings] load_dotenv = true. The
 * process env itself is left untouched — it is shared by every extension.
 * @param {string} configFile
 * @param {Record<string, string>} settings
 * @param {Record<string, string | undefined>} env
 * @returns {Record<string, string | undefined>}
 */
function effectiveEnv(configFile, settings, env) {
  if (!parseBool(settings.load_dotenv, false, 'load_dotenv')) return env;
  const configDir = path.dirname(configFile);
  const dotenvPath = path.resolve(configDir, settings.load_dotenv_file || '.env');
  if (!fs.existsSync(dotenvPath)) return env;
  return { ...parseDotenv(fs.readFileSync(dotenvPath, 'utf8')), ...env };
}

/**
 * semacli's _resolve_token: [auth] method = bearer_token | env_var, or
 * [semaphore] bearer_token when there is no [auth] section.
 * @param {Record<string, Record<string, string>>} ini
 * @param {Record<string, string | undefined>} env
 * @returns {string | null}
 */
function resolveToken(ini, env) {
  const auth = ini.auth;
  if (!auth) return ini.semaphore.bearer_token || null;
  const method = auth.method || 'bearer_token';
  if (method === 'bearer_token') return auth.bearer_token || null;
  if (method === 'env_var') return env[auth.env_var || DEFAULT_ENV_VAR] || null;
  throw new ConfigError(`Unknown auth method: ${method}`);
}

/**
 * Parse semacli.ini text into a connection config.
 * @param {string} text
 * @param {string} configFile
 * @param {Record<string, string | undefined>} env
 * @returns {SemaphoreConfig}
 */
function parseConfig(text, configFile, env) {
  const ini = parseIni(text);
  if (!ini.semaphore) throw new ConfigError('Missing [semaphore] section in configuration');
  const rawUrl = ini.semaphore.url;
  if (!rawUrl) throw new ConfigError("Missing 'url' in [semaphore] section");
  const settings = ini.settings ?? {};
  const url = rawUrl.replace(/\/+$/, '');
  if (url.startsWith('http://') && !parseBool(settings.allow_http, false, 'allow_http')) {
    throw new ConfigError(
      "Plain HTTP url is refused by default. Set 'allow_http = true' in the [settings] section to enable it (not recommended).",
    );
  }
  return {
    configFile,
    url,
    token: resolveToken(ini, effectiveEnv(configFile, settings, env)),
    project: parseInteger(ini.semaphore.project, '[semaphore] project'),
    timeout: parseInteger(settings.timeout, '[settings] timeout') ?? DEFAULT_TIMEOUT,
    verifySsl: parseBool(settings.verify_ssl, true, 'verify_ssl'),
  };
}

/**
 * Find and load the config for a workspace folder.
 * @param {string} startDir
 * @param {Record<string, string | undefined>} [env]
 * @param {string} [home]
 * @returns {SemaphoreConfig}
 */
function loadConfig(startDir, env = process.env, home = os.homedir()) {
  const configFile = findConfigFile(startDir, home);
  if (!configFile) {
    throw new ConfigError(
      'No semacli.ini found (workspace and parents, ~/.semacli.ini, /usr/local/etc). Run `sem init`.',
    );
  }
  const config = parseConfig(fs.readFileSync(configFile, 'utf8'), configFile, env);
  if (!config.token) throw new ConfigError(`No API token resolved from ${configFile} [auth].`);
  if (config.project === null) {
    throw new ConfigError(`No project set: add 'project = <id>' to [semaphore] in ${configFile}.`);
  }
  return config;
}

module.exports = {
  ConfigError,
  findConfigFile,
  findFileUpwards,
  loadConfig,
  parseConfig,
  parseDotenv,
  parseIni,
};
