// Utility positive/negative controls. Not generated application acceptance.
import {test, expect} from '@playwright/test';
import {uploadCsv, downloadCsv} from './io';

test('real UI upload and download preserve UTF-8 quoted CSV bytes', async ({page}) => {
  const csv = '区域,Note\n华东,"a,b"\n北部,"line1\nline2"\n';
  await page.setContent(`<label>CSV file<input type="file" onchange="this.files[0].text().then(t=>document.querySelector('output').textContent=t)"></label><output></output><a download="sample.csv" href="data:text/csv;charset=utf-8,${encodeURIComponent(csv)}">Export CSV</a>`);
  await uploadCsv(page.getByLabel('CSV file'), '样例.csv', csv);
  await expect(page.locator('output')).toHaveText(csv);
  expect(await page.locator('output').textContent()).toBe(csv);
  const result = await downloadCsv(page, page.getByRole('link', {name:'Export CSV',exact:true}));
  expect(result.filename).toBe('sample.csv');
  expect(result.text).toBe(csv);
});

test('upload rejects paths and excessive bytes before touching the UI', async ({page}) => {
  const input = page.getByLabel('CSV file');
  for (const name of ['../secret.csv', '/tmp/secret.csv', 'C:\\secret.csv', 'bad.txt']) {
    await expect(uploadCsv(input, name, 'a,b')).rejects.toThrow('simple .csv');
  }
  await expect(uploadCsv(input, 'large.csv', 'x'.repeat(512*1024+1))).rejects.toThrow('512 KiB');
});

test('download stops reading oversized UI content', async ({page}) => {
  await page.setContent(`<a download="large.csv" href="data:text/csv,${'x'.repeat(512*1024+1)}">Export CSV</a>`);
  await expect(downloadCsv(page, page.getByRole('link',{name:'Export CSV',exact:true}))).rejects.toThrow('512 KiB');
});
