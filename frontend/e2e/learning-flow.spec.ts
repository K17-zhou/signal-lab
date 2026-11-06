import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

function studyLink(session: number) {
  return '/#learn?study=00000000-0000-4000-8000-' + String(session).padStart(12, '0');
}

async function savePredictionAndRun(page: Page, prediction: string, peak: number) {
  const run = page.getByRole('button', { name: '运行本题实验', exact: true });
  await expect(run).toBeDisabled();
  await page.getByRole('spinbutton', { name: '预测答案（Hz）' }).fill(prediction);
  await page.getByRole('button', { name: '保存预测', exact: true }).click();
  await expect(run).toBeEnabled();
  await run.click();
  await expect(page.getByRole('img', { name: `单边频谱：主峰${peak}Hz` }).locator('svg path').first()).toBeAttached();
  await expect(page.getByText('完成本题指导步骤后显示迁移题。')).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: '迁移题答案（Hz）' })).toHaveCount(0);
}

async function submitTransfer(page: Page, answer: string) {
  await page.getByRole('spinbutton', { name: '迁移题答案（Hz）' }).fill(answer);
  await page.getByRole('button', { name: '提交迁移题', exact: true }).click();
  await expect(page.getByText('迁移题答对了', { exact: true })).toBeVisible();
}

async function sessionExport(page: Page, format: 'JSON' | 'CSV') {
  const href = await page.getByRole('link', { name: '导出 ' + format }).getAttribute('href');
  expect(href).toBeTruthy();
  const response = await page.request.get(href!);
  expect(response.ok()).toBeTruthy();
  return response;
}

test('switches parameter presets with real saved sampling results', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('img', { name: '单边频谱：主峰30Hz' })).toBeVisible();
  await page.getByRole('button', { name: '正常采样', exact: true }).click();
  await expect(page.getByRole('img', { name: '单边频谱：主峰50Hz' })).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: '信号频率' })).toHaveValue('50');
  await expect(page.getByRole('spinbutton', { name: '采样率' })).toHaveValue('400');
});

test('B text guidance restores after reload and exports the exact study assignment', async ({ page }, testInfo) => {
  await page.goto(studyLink(1));
  await expect(page.getByRole('combobox', { name: '学习案例' }).locator('option')).toHaveCount(3);
  await expect(page.getByRole('button', { name: '新建会话' })).toHaveCount(0);
  await savePredictionAndRun(page, '20', 32);
  await page.getByRole('button', { name: '获取 AI 指导' }).click();
  const text = page.getByText('请核对记录中的 32 Hz 主峰和原始频率。');
  await expect(text).toBeVisible();
  await expect(page.getByLabel('引用的实验数据')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认运行对照实验' })).toHaveCount(0);
  await submitTransfer(page, '44');
  await page.reload();
  await expect(text).toBeVisible();
  await expect(page.getByText('迁移题答对了', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '获取 AI 指导' })).toBeDisabled();
  const report = await (await sessionExport(page, 'JSON')).json();
  expect(report.study).toMatchObject({ condition: 'B', form: 'X', order_index: 1, cohort: 'pilot' });
  expect(report.events.map((event: { stage: string }) => event.stage)).toEqual(['predict', 'run', 'transfer']);
  expect(report.tutor_calls).toHaveLength(1);
  expect(report.tutor_calls[0]).toMatchObject({ status: 200, reply: { evidence: [], next_experiment: null } });
  expect(await (await sessionExport(page, 'CSV')).text()).toContain('study-x-safe');
  await page.screenshot({ path: testInfo.outputPath('synthetic-b.jpg'), fullPage: true });
});

test('C evidence focuses the correct run and the confirmed comparison survives reload', async ({ page }, testInfo) => {
  await page.goto(studyLink(2));
  await page.getByRole('combobox', { name: '学习案例' }).selectOption('study-y-alias');
  await savePredictionAndRun(page, '22', 51);
  await page.getByRole('button', { name: '获取 AI 指导' }).click();
  await page.getByRole('button', { name: '观测主峰 51 Hz' }).click();
  await expect(page.getByLabel('当前运行证据')).toBeFocused();
  await expect(page.getByText('观测主峰 · 51 Hz')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('synthetic-c.jpg'), fullPage: true });
  await page.getByRole('button', { name: '确认运行对照实验' }).click();
  await expect(page.getByRole('img', { name: '单边频谱：主峰81Hz' })).toBeVisible();
  await submitTransfer(page, '55');
  await page.reload();
  await expect(page.getByText('已保存预测：22 Hz')).toBeVisible();
  await expect(page.getByText('当前图表显示对照实验')).toBeVisible();
  await expect(page.getByText('迁移题答对了', { exact: true })).toBeVisible();
  const report = await (await sessionExport(page, 'JSON')).json();
  expect(report.study).toMatchObject({ condition: 'C', form: 'Y', order_index: 2 });
  expect(report.events.map((event: { stage: string }) => event.stage)).toEqual(['predict', 'run', 'observe', 'transfer']);
  expect(report.tutor_calls).toHaveLength(1);
  expect(report.events[1].run_id).toBe(report.tutor_calls[0].run_id);
  expect(report.events[2].run_id).not.toBe(report.tutor_calls[0].run_id);
});

test('records an assigned timeout once and still grades the transfer', async ({ page }) => {
  await page.goto(studyLink(3));
  await savePredictionAndRun(page, '20', 38);
  await page.getByRole('button', { name: '获取 AI 指导' }).click();
  await expect(page.getByRole('alert')).toContainText('指导超时');
  await expect(page.getByRole('button', { name: '获取 AI 指导' })).toBeDisabled();
  await submitTransfer(page, '46');
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('指导超时');
  const report = await (await sessionExport(page, 'JSON')).json();
  expect(report.tutor_calls).toHaveLength(1);
  expect(report.tutor_calls[0]).toMatchObject({ status: 504, error_code: 'tutor_timeout', reply: null });
});
