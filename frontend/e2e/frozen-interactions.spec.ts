import { expect, test } from '@playwright/test';
import type { LearningEvent, LearningEventDraft } from '../src/features/learning/learningApi';

test('I08 rejects a real older run citation after the comparison is confirmed', async ({ page }, testInfo) => {
  let computeRequests = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/experiments/run')) computeRequests += 1;
  });
  await page.goto('/#learn');
  await page.getByRole('spinbutton', { name: '预测答案（Hz）' }).fill('22');
  await page.getByRole('button', { name: '保存预测', exact: true }).click();
  await page.getByRole('button', { name: '运行本题实验', exact: true }).click();
  await expect(page.getByRole('img', { name: '单边频谱：主峰40Hz' })).toBeVisible();
  await page.getByRole('textbox', { name: '你的问题（选填）' }).fill('I08 原始对照');
  await page.getByRole('button', { name: '获取 AI 指导' }).click();
  await page.getByRole('button', { name: '确认运行对照实验' }).click();
  await expect(page.getByRole('img', { name: '单边频谱：主峰48Hz' })).toBeVisible();
  await page.getByRole('textbox', { name: '你的问题（选填）' }).fill('I08 引用旧运行');
  const [response] = await Promise.all([
    page.waitForResponse((item) => item.url().endsWith('/api/tutor/guide')),
    page.getByRole('button', { name: '获取 AI 指导' }).click(),
  ]);
  expect(response.status()).toBe(502);
  expect(await response.json()).toEqual({ detail: 'invalid_tutor_reply' });
  await expect(page.getByRole('alert')).toContainText('未通过证据校验');
  await expect(page.getByRole('button', { name: '确认运行对照实验' })).toHaveCount(0);
  await expect(page.getByText('已保存预测：22 Hz')).toBeVisible();
  await expect(page.getByRole('img', { name: '单边频谱：主峰48Hz' })).toBeVisible();
  const href = await page.getByRole('link', { name: '导出 JSON' }).getAttribute('href');
  const report = await (await page.request.get(href!)).json();
  expect(report.events.map((event: LearningEvent) => event.stage)).toEqual(['predict', 'run', 'observe']);
  expect(Object.keys(report.runs)).toHaveLength(2);
  expect(computeRequests).toBe(2);
  await page.screenshot({ path: testInfo.outputPath('holdout-i08.jpg'), fullPage: true });
});

test('I10 preserves exactly one original transfer when the client loses the response', async ({ page }) => {
  await page.goto('/#learn');
  await page.getByRole('combobox', { name: '学习案例' }).selectOption('interpolation');
  await page.getByRole('radio', { name: '不能找回', exact: true }).check();
  await page.getByRole('button', { name: '保存预测', exact: true }).click();
  await page.getByRole('button', { name: '运行本题实验', exact: true }).click();
  await expect(page.getByRole('img', { name: '单边频谱：主峰30Hz' })).toBeVisible();

  let transferDraft: LearningEventDraft | undefined;
  let saved: LearningEvent | undefined;
  await page.route('**/api/events', async (route) => {
    const request = route.request();
    const event = request.method() === 'POST' ? request.postDataJSON() as LearningEventDraft : null;
    if (event?.stage !== 'transfer') return route.continue();
    transferDraft = event;
    const result = await route.fetch();
    expect(result.status()).toBe(200);
    saved = await result.json() as LearningEvent;
    await route.abort('failed');
  });
  await page.getByRole('radio', { name: '从已有样本计算出的点', exact: true }).check();
  await page.getByRole('button', { name: '提交迁移题', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('无法连接实验服务');
  expect(saved?.outcome).toBe('correct');
  expect(transferDraft?.answer).toEqual({ kind: 'choice', option_id: 'display-points' });
  await page.unroute('**/api/events');
  await page.reload();
  await expect(page.getByText('迁移题答对了', { exact: true })).toBeVisible();
  const replay = await page.request.post('/api/events', { data: transferDraft! });
  expect(replay.status()).toBe(200);
  expect(await replay.json()).toEqual(saved);
  const conflict = await page.request.post('/api/events', { data: {
    ...transferDraft,
    answer: { kind: 'choice', option_id: 'extra-samples' },
  } });
  expect(conflict.status()).toBe(409);
  const jsonHref = await page.getByRole('link', { name: '导出 JSON' }).getAttribute('href');
  const json = await (await page.request.get(jsonHref!)).json();
  expect(json.events.filter((event: LearningEvent) => event.stage === 'transfer')).toEqual([saved]);
  expect(json.runs[saved!.run_id!].params).toEqual({
    frequency_hz: 70, sample_rate_hz: 100, amplitude: 1, phase_rad: 0,
  });
  const csvHref = await page.getByRole('link', { name: '导出 CSV' }).getAttribute('href');
  const csv = await (await page.request.get(csvHref!)).text();
  expect(csv.split(/\r?\n/).filter((row) => row.startsWith(saved!.event_id + ','))).toHaveLength(1);
});
