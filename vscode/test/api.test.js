const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { ApiError, SemaphoreApi, nodeTransport } = require('../src/api');

const cfg = {
  configFile: 'semacli.ini',
  url: 'https://sema.example/semaphore',
  token: 'tok',
  project: 1,
  timeout: 7,
  verifySsl: true,
};

function fakeTransport(status, body) {
  const calls = [];
  const impl = async (url, req) => {
    calls.push({ url, req });
    return { status, body: typeof body === 'string' ? body : JSON.stringify(body) };
  };
  return { impl, calls };
}

test('listTasks: GET /tasks/last with Bearer, timeout and SSL flags', async () => {
  const { impl, calls } = fakeTransport(200, [{ id: 1, status: 'success' }]);
  const tasks = await new SemaphoreApi(cfg, impl).listTasks();
  assert.deepEqual(tasks, [{ id: 1, status: 'success' }]);
  assert.equal(calls[0].url, 'https://sema.example/semaphore/api/project/1/tasks/last');
  assert.deepEqual(calls[0].req, {
    method: 'GET',
    headers: { Authorization: 'Bearer tok', Accept: 'application/json' },
    body: undefined,
    timeoutMs: 7000,
    verifySsl: true,
  });
});

test('listTasks: a non-list answer is rejected', async () => {
  const { impl } = fakeTransport(200, { error: 'nope' });
  await assert.rejects(new SemaphoreApi(cfg, impl).listTasks(), /expected a list/);
});

test('getTask / getRawOutput', async () => {
  const task = fakeTransport(200, { id: 9 });
  assert.deepEqual(await new SemaphoreApi(cfg, task.impl).getTask(9), { id: 9 });
  assert.equal(task.calls[0].url, 'https://sema.example/semaphore/api/project/1/tasks/9');

  const raw = fakeTransport(200, 'line 1\nline 2\n');
  assert.equal(await new SemaphoreApi(cfg, raw.impl).getRawOutput(9), 'line 1\nline 2\n');
  assert.match(raw.calls[0].url, /\/tasks\/9\/raw_output$/);
});

test('getJson: a non-JSON body is an ApiError', async () => {
  const { impl } = fakeTransport(200, '<html>');
  await assert.rejects(new SemaphoreApi(cfg, impl).getTask(1), /response is not JSON/);
});

test('stopTask: POST JSON body with the force flag', async () => {
  const { impl, calls } = fakeTransport(204, '');
  const api = new SemaphoreApi(cfg, impl);
  await api.stopTask(5);
  await api.stopTask(5, true);
  assert.equal(calls[0].url, 'https://sema.example/semaphore/api/project/1/tasks/5/stop');
  assert.equal(calls[0].req.method, 'POST');
  assert.equal(calls[0].req.body, '{"force":false}');
  assert.equal(calls[0].req.headers['Content-Type'], 'application/json');
  assert.equal(calls[1].req.body, '{"force":true}');
});

test('HTTP errors carry the status and a trimmed body', async () => {
  const { impl } = fakeTransport(401, ' invalid token \n');
  await assert.rejects(new SemaphoreApi(cfg, impl).listTasks(), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.status, 401);
    assert.equal(err.message, 'GET /project/1/tasks/last -> HTTP 401 (invalid token)');
    return true;
  });
  const empty = fakeTransport(500, '');
  await assert.rejects(new SemaphoreApi(cfg, empty.impl).getTask(1), /HTTP 500$/);
});

test('transport failures become ApiError with status 0', async () => {
  const failing = async () => {
    throw new Error('ECONNREFUSED');
  };
  const rejecting = async () => {
    throw 'boom';
  };
  await assert.rejects(new SemaphoreApi(cfg, failing).listTasks(), {
    status: 0,
    message: 'GET /project/1/tasks/last: ECONNREFUSED',
  });
  await assert.rejects(new SemaphoreApi(cfg, rejecting).listTasks(), /: boom$/);
});

test('webUrl: project history, optionally on one task', () => {
  const api = new SemaphoreApi(cfg);
  assert.equal(api.webUrl(), 'https://sema.example/semaphore/project/1/history');
  assert.equal(api.webUrl(42), 'https://sema.example/semaphore/project/1/history?t=42');
});

/** Local HTTP server answering with `handler`; returns its base URL. */
async function serve(t, handler) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());
  return `http://127.0.0.1:${server.address().port}`;
}

test('nodeTransport: real round trip (method, headers, body, status)', async (t) => {
  const base = await serve(t, (req, res) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      res.writeHead(201, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ method: req.method, auth: req.headers.authorization, body }));
    });
  });
  const resp = await nodeTransport(`${base}/api/x`, {
    method: 'POST',
    headers: { Authorization: 'Bearer t' },
    body: '{"a":1}',
    timeoutMs: 2000,
    verifySsl: false,
  });
  assert.equal(resp.status, 201);
  assert.deepEqual(JSON.parse(resp.body), { method: 'POST', auth: 'Bearer t', body: '{"a":1}' });
});

test('nodeTransport: timeout and connection errors reject', async (t) => {
  const base = await serve(t, () => {
    // never answers
  });
  const req = { method: 'GET', headers: {}, timeoutMs: 50, verifySsl: true };
  await assert.rejects(nodeTransport(`${base}/slow`, req), /timeout after 0.05s/);
  await assert.rejects(nodeTransport('http://127.0.0.1:1/', req), /ECONNREFUSED/);
});

test('nodeTransport: https with verify_ssl=false is accepted by node (no network)', async () => {
  // Port 1 refuses immediately: the call goes through the https branch and
  // its rejectUnauthorized option without needing a TLS server.
  const req = { method: 'GET', headers: {}, timeoutMs: 1000, verifySsl: false };
  await assert.rejects(nodeTransport('https://127.0.0.1:1/', req), /ECONNREFUSED/);
});
