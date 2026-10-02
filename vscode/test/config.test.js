const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  ConfigError,
  findConfigFile,
  loadConfig,
  parseConfig,
  parseDotenv,
  parseIni,
} = require('../src/config');

function tmpdir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'semacli-vsc-'));
}

const BASE = '[semaphore]\nurl = https://sema.example/semaphore/\nproject = 1\n';

test('parseIni: sections, both separators, comments, case-insensitive keys, BOM', () => {
  const ini = parseIni(
    '﻿# top\n[semaphore]\nURL = https://x\n; c\nproject: 2\n  continuation\n[auth]\nmethod=env_var\nnoequals\n',
  );
  assert.deepEqual(ini, {
    semaphore: { url: 'https://x', project: '2' },
    auth: { method: 'env_var' },
  });
});

test('parseIni: keys before any section are ignored', () => {
  assert.deepEqual(parseIni('orphan = 1\n[s]\nk = v\n'), { s: { k: 'v' } });
});

test('parseDotenv: export, quotes, escapes, comments', () => {
  const env = parseDotenv(
    [
      '# comment',
      'export SEMAPHORE_TOKEN=abc=def',
      'PLAIN = value # trailing',
      "SINGLE='a\\nb # kept'",
      'DOUBLE="x\\ny \\"q\\" \\\\"',
      'not a line',
      '',
    ].join('\n'),
  );
  assert.deepEqual(env, {
    SEMAPHORE_TOKEN: 'abc=def',
    PLAIN: 'value',
    SINGLE: 'a\\nb # kept',
    DOUBLE: 'x\ny "q" \\',
  });
});

test('parseConfig: bearer_token method, defaults, trailing slash stripped', () => {
  const cfg = parseConfig(`${BASE}[auth]\nbearer_token = tok\n`, '/x/semacli.ini', {});
  assert.deepEqual(cfg, {
    configFile: '/x/semacli.ini',
    url: 'https://sema.example/semaphore',
    token: 'tok',
    project: 1,
    timeout: 30,
    verifySsl: true,
  });
});

test('parseConfig: token in [semaphore] when there is no [auth] section', () => {
  assert.equal(parseConfig(`${BASE}bearer_token = legacy\n`, 'f', {}).token, 'legacy');
  assert.equal(parseConfig(BASE, 'f', {}).token, null);
});

test('parseConfig: env_var method, default and custom variable names', () => {
  const ini = `${BASE}[auth]\nmethod = env_var\n`;
  assert.equal(parseConfig(ini, 'f', { SEMAPHORE_TOKEN: 'e1' }).token, 'e1');
  assert.equal(parseConfig(`${ini}env_var = MY_TOK\n`, 'f', { MY_TOK: 'e2' }).token, 'e2');
  assert.equal(parseConfig(ini, 'f', {}).token, null);
});

test('parseConfig: unknown auth method is an error', () => {
  assert.throws(
    () => parseConfig(`${BASE}[auth]\nmethod = oauth\n`, 'f', {}),
    new ConfigError('Unknown auth method: oauth'),
  );
});

test('parseConfig: [settings] timeout, verify_ssl, booleans like configparser', () => {
  const cfg = parseConfig(`${BASE}[settings]\ntimeout = 5\nverify_ssl = Off\n`, 'f', {});
  assert.equal(cfg.timeout, 5);
  assert.equal(cfg.verifySsl, false);
  assert.throws(
    () => parseConfig(`${BASE}[settings]\nverify_ssl = maybe\n`, 'f', {}),
    /verify_ssl: not a boolean: maybe/,
  );
  assert.throws(
    () => parseConfig(`${BASE}[settings]\ntimeout = soon\n`, 'f', {}),
    /timeout: not an integer/,
  );
});

test('parseConfig: plain http refused unless allow_http', () => {
  const ini = '[semaphore]\nurl = http://sema\n';
  assert.throws(() => parseConfig(ini, 'f', {}), /Plain HTTP url is refused/);
  assert.equal(parseConfig(`${ini}[settings]\nallow_http = yes\n`, 'f', {}).url, 'http://sema');
});

test('parseConfig: missing section / url / bad project', () => {
  assert.throws(() => parseConfig('[auth]\n', 'f', {}), /Missing \[semaphore\] section/);
  assert.throws(() => parseConfig('[semaphore]\nproject = 1\n', 'f', {}), /Missing 'url'/);
  assert.throws(
    () => parseConfig('[semaphore]\nurl = https://x\nproject = one\n', 'f', {}),
    /\[semaphore\] project: not an integer: one/,
  );
  assert.equal(parseConfig('[semaphore]\nurl = https://x\n', 'f', {}).project, null);
});

test('load_dotenv: .env beside the ini fills the env, the shell env wins', () => {
  const dir = tmpdir();
  fs.writeFileSync(path.join(dir, '.env'), 'SEMAPHORE_TOKEN=from-dotenv\n');
  const ini = `[settings]\nload_dotenv = true\n${BASE}[auth]\nmethod = env_var\n`;
  const file = path.join(dir, 'semacli.ini');
  assert.equal(parseConfig(ini, file, {}).token, 'from-dotenv');
  assert.equal(parseConfig(ini, file, { SEMAPHORE_TOKEN: 'shell' }).token, 'shell');
});

test('load_dotenv: custom relative file, missing file is a no-op, off by default', () => {
  const dir = tmpdir();
  fs.mkdirSync(path.join(dir, 'secrets'));
  fs.writeFileSync(path.join(dir, 'secrets', 'sema.env'), 'SEMAPHORE_TOKEN=custom\n');
  fs.writeFileSync(path.join(dir, '.env'), 'SEMAPHORE_TOKEN=ignored\n');
  const file = path.join(dir, 'semacli.ini');
  const auth = `${BASE}[auth]\nmethod = env_var\n`;
  const custom = `[settings]\nload_dotenv = 1\nload_dotenv_file = secrets/sema.env\n${auth}`;
  assert.equal(parseConfig(custom, file, {}).token, 'custom');
  const missing = `[settings]\nload_dotenv = 1\nload_dotenv_file = nope.env\n${auth}`;
  assert.equal(parseConfig(missing, file, {}).token, null);
  assert.equal(parseConfig(auth, file, {}).token, null);
});

test('findConfigFile: walks up from the workspace, then ~/.semacli.ini', () => {
  const root = tmpdir();
  const sub = path.join(root, 'a', 'b');
  fs.mkdirSync(sub, { recursive: true });
  const home = tmpdir();
  const homeIni = path.join(home, '.semacli.ini');
  fs.writeFileSync(homeIni, BASE);
  // No project ini anywhere above `sub` (tmpdir has none): falls back to home.
  assert.equal(findConfigFile(sub, home), homeIni);
  fs.writeFileSync(path.join(root, 'semacli.ini'), BASE);
  assert.equal(findConfigFile(sub, home), path.join(root, 'semacli.ini'));
  assert.equal(findConfigFile(sub, tmpdir()), path.join(root, 'semacli.ini'));
});

test('loadConfig: reads the file found, reports what is missing', () => {
  const emptyHome = tmpdir();
  const root = tmpdir();
  assert.throws(() => loadConfig(root, {}, emptyHome), /No semacli.ini found/);

  const file = path.join(root, 'semacli.ini');
  fs.writeFileSync(file, '[semaphore]\nurl = https://x\n');
  assert.throws(() => loadConfig(root, {}, emptyHome), /No API token resolved/);

  fs.writeFileSync(file, '[semaphore]\nurl = https://x\nbearer_token = t\n');
  assert.throws(() => loadConfig(root, {}, emptyHome), /No project set/);

  fs.writeFileSync(file, '[semaphore]\nurl = https://x\nbearer_token = t\nproject = 3\n');
  const cfg = loadConfig(root, {}, emptyHome);
  assert.equal(cfg.project, 3);
  assert.equal(cfg.configFile, file);
});
