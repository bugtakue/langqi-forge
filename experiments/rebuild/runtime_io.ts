// Controller-owned browser file operations. No host paths or arbitrary I/O.
// Uploaded bytes are declared test data; downloaded bytes come from that UI.
import type {Locator, Page} from '@playwright/test';

const LIMIT = 512 * 1024;

export async function uploadCsv(control: Locator, name: string, text: string) {
  if (typeof name !== 'string' || !/^[\p{L}\p{N}_ .-]+\.csv$/u.test(name) ||
      name.includes('..') || name.length > 128 || typeof text !== 'string') {
    throw new Error('CSV upload requires a simple .csv filename and literal text');
  }
  const buffer = Buffer.from(text, 'utf8');
  if (buffer.length > LIMIT) throw new Error('CSV upload exceeds 512 KiB');
  await control.setInputFiles({name, mimeType: 'text/csv', buffer});
}

export async function downloadCsv(page: Page, trigger: Locator) {
  // Register before clicking so a fast download cannot be missed. Both
  // promises are observed, including click failures (no dangling rejection).
  const [download] = await Promise.all([
    page.waitForEvent('download', {timeout: 10000}), trigger.click(),
  ]);
  const stream = await download.createReadStream();
  if (!stream) throw new Error('CSV download produced no readable content');
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    const data = Buffer.from(chunk);
    size += data.length;
    if (size > LIMIT) {
      stream.destroy();
      throw new Error('CSV download exceeds 512 KiB');
    }
    chunks.push(data);
  }
  if (await download.failure()) throw new Error('CSV download failed');
  return {filename: download.suggestedFilename(), text: Buffer.concat(chunks).toString('utf8')};
}
