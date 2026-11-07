import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';

const [project, baseURL, output] = process.argv.slice(2);
const require = createRequire(path.join(project, 'frontend/package.json'));
const { chromium } = require('playwright');
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ baseURL, viewport: { width: 1440, height: 900 } });
const result = { source: 'fresh local clone', model: 'Qwen3.5-4B Q4_K_M', requests: [] };
const button = (name) => page.getByRole('button', { name, exact: true });
const event = async (session, caseId, stage, fields = {}) => {
  const response = await page.request.post('/api/events', { data: {
    event_id: crypto.randomUUID(), session_id: session, case_id: caseId, stage, elapsed_ms: 0, ...fields,
  } });
  assert.equal(response.status(), 200, await response.text());
  return response.json();
};

try {
  await page.goto('/');
  await page.getByRole('img', { name: '单边频谱：主峰30Hz' }).waitFor();
  await button('正常采样').click();
  await page.getByRole('img', { name: '单边频谱：主峰50Hz' }).waitFor();
  assert.equal(await page.getByRole('spinbutton', { name: '采样率' }).inputValue(), '400');
  await page.screenshot({ path: path.join(output, 'readme-s1.jpg'), fullPage: true });

  await page.goto('/#learn');
  await page.getByRole('spinbutton', { name: '预测答案（Hz）' }).fill('22');
  await button('保存预测').click();
  await button('运行本题实验').click();
  await page.getByRole('img', { name: '单边频谱：主峰40Hz' }).waitFor();
  const started = performance.now();
  const [guideResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().endsWith('/api/tutor/guide'), { timeout: 38000 }),
    button('获取 AI 指导').click(),
  ]);
  const reply = await guideResponse.json();
  result.first_guide = { status: guideResponse.status(), seconds: (performance.now() - started) / 1000, reply };
  assert.equal(guideResponse.status(), 200, JSON.stringify(reply));
  assert.match(reply.explanation, /你的原预测是 22 Hz/);
  assert.match(reply.explanation, /理论折叠频率为 40 Hz/);
  assert.match(reply.explanation, /观测主峰为 40 Hz/);
  assert(reply.evidence.length > 0);
  await page.getByLabel('引用的实验数据').getByRole('button').first().click();
  assert(await page.getByLabel('当前运行证据').evaluate((node) => node === document.activeElement));
  await page.screenshot({ path: path.join(output, 'readme-guide.jpg'), fullPage: true });

  if (reply.next_experiment) {
    await button('确认运行对照实验').click();
    await page.getByText('当前图表显示对照实验').waitFor();
  }
  await page.getByRole('spinbutton', { name: '迁移题答案（Hz）' }).fill('30');
  await button('提交迁移题').click();
  await page.getByText('迁移题答对了', { exact: true }).waitFor();
  await page.reload();
  await page.getByText('已保存预测：22 Hz').waitFor();
  await page.getByText('迁移题答对了', { exact: true }).waitFor();
  const href = await page.getByRole('link', { name: '导出 JSON' }).getAttribute('href');
  const saved = await (await page.request.get(href)).json();
  assert(reply.evidence.every((ref) => ref.run_id === saved.events.find((row) => row.stage === 'run').run_id));
  assert.equal(saved.events.filter((row) => row.stage === 'transfer').length, 1);
  result.browser_events = saved.events;
  result.browser_guidance = reply;
  await page.screenshot({ path: path.join(output, 'readme-restored.jpg'), fullPage: true });

  const cases = await (await page.request.get('/api/learning/cases')).json();
  for (const exercise of cases.filter((row) => row.prediction.experiment_type === 'sampling_aliasing' || 'frequency_hz' in row.prediction.params)) {
    const session = crypto.randomUUID();
    const prediction = exercise.prediction.kind === 'choice'
      ? { kind: 'choice', option_id: exercise.prediction.options[0].option_id }
      : { kind: 'numeric', value: 22, unit: 'Hz' };
    await event(session, exercise.case_id, 'predict', { answer: prediction });
    const computed = await page.request.post('/api/experiments/run', { data: {
      experiment_type: 'sampling_aliasing', params: exercise.prediction.params,
    } });
    assert.equal(computed.status(), 200, await computed.text());
    const run = await computed.json();
    await event(session, exercise.case_id, 'run', { run_id: run.run_id });
    const clock = performance.now();
    const guide = await page.request.post('/api/tutor/guide', { data: {
      session_id: session, run_id: run.run_id, mode: 'C',
      message: '即使实验与你的猜测不符，也请解释当前记录；请核对我的原预测。',
    }, timeout: 38000 });
    const body = await guide.json();
    const proof = { case_id: exercise.case_id, status: guide.status(), seconds: (performance.now() - clock) / 1000,
      params: run.params, metrics: run.metrics, warnings: run.warnings, prediction, reply: body };
    result.requests.push(proof);
    assert.equal(guide.status(), 200, JSON.stringify(proof));
    const expectedFold = Math.abs(((run.params.frequency_hz + run.params.sample_rate_hz / 2) % run.params.sample_rate_hz)
      - run.params.sample_rate_hz / 2);
    assert.match(body.explanation, new RegExp('理论折叠频率为 ' + expectedFold + ' Hz'));
    if (run.metrics.peak_frequency_hz === null) assert.match(body.explanation, /未检测到可辨主峰/);
    else assert(body.explanation.includes('观测主峰为 ' + run.metrics.peak_frequency_hz + ' Hz'));
    assert(body.evidence.length > 0 && body.evidence.every((ref) => ref.run_id === run.run_id));
    if (body.next_experiment) {
      const params = body.next_experiment.params;
      assert(Number.isInteger(params.frequency_hz) && Number.isInteger(params.sample_rate_hz));
      assert(params.frequency_hz >= 5 && params.frequency_hz <= 200);
      assert(params.sample_rate_hz >= 20 && params.sample_rate_hz <= 1000);
      assert.notDeepEqual(params, exercise.transfer.params);
    }
    console.log(exercise.case_id + ' HTTP 200 · correct saved facts and bound evidence');
  }
  assert(result.requests.length >= 6, 'Expected all six sampling exercises');
  result.outcome = 'passed';
} catch (error) {
  result.outcome = 'failed';
  result.failure = String(error);
  throw error;
} finally {
  await writeFile(path.join(output, 'real-tutor-verification.json'), JSON.stringify(result, null, 2));
  await browser.close();
}
