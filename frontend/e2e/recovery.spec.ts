import { expect, test } from '@playwright/test';
import type { Request } from '@playwright/test';
import type { ExperimentResult } from '../src/api';

test('retries a disconnected load and opens an empty learning session', async ({ page }) => {
  const cases = '**/api/learning/cases';
  await page.route(cases, (route) => route.abort('internetdisconnected'));
  await page.goto('/#learn');
  await expect(page.getByRole('alert')).toContainText('无法连接实验服务');
  await expect(page.getByRole('img')).toHaveCount(0);
  await page.unroute(cases);
  await page.getByRole('button', { name: '重试加载' }).click();
  await expect(page.getByRole('spinbutton', { name: '预测答案（Hz）' })).toHaveValue('');
  await expect(page.getByRole('button', { name: '运行本题实验' })).toBeDisabled();
  await expect(page.getByText('保存预测并运行实验后，波形和频谱会显示在这里。')).toBeVisible();
  await expect(page.getByRole('link', { name: '导出 JSON' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '导出 CSV' })).toHaveCount(0);
});

test('keeps saved predictions when the model is offline and retries a missing result', async ({ page }) => {
  await page.goto('/#learn');
  await page.getByRole('spinbutton', { name: '预测答案（Hz）' }).fill('22');
  await page.getByRole('button', { name: '保存预测', exact: true }).click();
  const [computed] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/experiments/run')),
    page.getByRole('button', { name: '运行本题实验', exact: true }).click(),
  ]);
  expect(computed.ok()).toBeTruthy();
  const { run_id } = await computed.json() as ExperimentResult;
  const spectrum = page.getByRole('img', { name: '单边频谱：主峰40Hz' });
  const prediction = page.getByText('已保存预测：22 Hz');
  await expect(spectrum).toBeVisible();
  await page.getByRole('textbox', { name: '你的问题（选填）' }).fill('验收模型离线');
  const [guide] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/tutor/guide')),
    page.getByRole('button', { name: '获取 AI 指导' }).click(),
  ]);
  expect(guide.status()).toBe(502);
  expect(await guide.json()).toEqual({ detail: 'tutor_unavailable' });
  await expect(page.getByRole('alert')).toContainText('本地模型暂时不可用');
  await expect(spectrum).toBeVisible();
  await expect(prediction).toBeVisible();
  await expect(page.getByRole('button', { name: '确认运行对照实验' })).toHaveCount(0);

  const resultPath = '**/api/experiments/' + run_id;
  await page.route(resultPath, async (route) => {
    const missing = await route.fetch({
      url: new URL('/api/experiments/00000000-0000-4000-8000-000000000000', route.request().url()).href,
    });
    expect(missing.status()).toBe(404);
    await route.fulfill({ response: missing });
  });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('没有找到对应的案例或运行记录');
  await expect(spectrum).toHaveCount(0);
  await expect(prediction).toBeVisible();
  await page.unroute(resultPath);
  await page.getByRole('button', { name: '重试读取结果' }).click();
  await expect(spectrum).toBeVisible();
  await expect(prediction).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test.describe('1024 × 768 desktop', () => {
  test.use({ viewport: { width: 1024, height: 768 } });

  test('keeps the latest chart when rapid preset changes finish out of order', async ({ page }, testInfo) => {
    await page.goto('/');
    await expect(page.getByRole('img', { name: '单边频谱：主峰30Hz' })).toBeVisible();
    const olderResponse = Promise.withResolvers<Request>();
    const releaseOlder = Promise.withResolvers<void>();
    const olderFinished = Promise.withResolvers<void>();
    await page.route('**/api/experiments/run', async (route) => {
      const payload = route.request().postDataJSON();
      if (payload.params.sample_rate_hz !== 400) return route.continue();
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      expect(await response.json()).toMatchObject({ metrics: { peak_frequency_hz: 50 } });
      olderResponse.resolve(route.request());
      await releaseOlder.promise;
      try {
        await route.fulfill({ response });
      } finally {
        olderFinished.resolve();
      }
    });

    const summary = page.getByRole('region', { name: '实验结果' });
    await page.getByRole('button', { name: '正常采样', exact: true }).click();
    const olderRequest = await olderResponse.promise;
    const aborted = page.waitForEvent('requestfailed', (request) => request === olderRequest);
    try {
      await page.getByRole('button', { name: '边界退化', exact: true }).click();
      await expect(summary).toContainText('奈奎斯特边界');
      await expect(summary).toContainText('无有效主峰');
    } finally {
      releaseOlder.resolve();
    }
    await olderFinished.promise;
    expect((await aborted).failure()?.errorText).toBe('net::ERR_ABORTED');
    await expect(summary).toContainText('奈奎斯特边界');
    await expect(page.getByRole('img', { name: '单边频谱：主峰50Hz' })).toHaveCount(0);
    await expect(page.getByRole('spinbutton', { name: '信号频率' })).toHaveValue('50');
    await expect(page.getByRole('spinbutton', { name: '采样率' })).toHaveValue('100');
    await expect(page.getByRole('button', { name: '导出本次数据' })).toBeEnabled();
    await expect(page.getByRole('button', { name: '运行实验', exact: true })).toBeVisible();
    await expect(page.getByText('−π rad', { exact: true })).toBeVisible();
    await expect(page.getByRole('img', { name: /^单边频谱/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1024);
    await page.screenshot({ path: testInfo.outputPath('desktop-1024.jpg'), fullPage: true });
  });
});
