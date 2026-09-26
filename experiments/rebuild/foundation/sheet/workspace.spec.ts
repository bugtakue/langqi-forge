// INTERNAL, source: public hackathon--sheet requirements, not official tests.
import {test,expect} from '@playwright/test';
import {restart} from './restart';

async function create(page) {
  await page.goto('/');
  await page.getByRole('button',{name:'New blank workbook',exact:true}).click();
  await page.getByRole('button',{name:'Create',exact:true}).click();
  await expect(page.getByRole('tab',{name:'Sheet1',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.getByRole('grid',{name:'Worksheet grid',exact:true})).toBeVisible();
  await expect(page.getByRole('gridcell',{name:'A1',exact:true})).toHaveAttribute('aria-selected','true');
}

async function enter(page,coordinate,value) {
  await page.getByRole('gridcell',{name:coordinate,exact:true}).click();
  await page.getByRole('textbox',{name:'Formula bar',exact:true}).fill(value);
  await page.getByRole('textbox',{name:'Formula bar',exact:true}).press('Enter');
  await expect(page.getByRole('gridcell',{name:coordinate,exact:true})).toHaveText(value);
}

test('foundation: create -> edit -> refresh -> restart -> direct reopen from new browser context', async ({page,browser,request}) => {
  await create(page);
  const value='saved-'+Date.now();
  await enter(page,'A1',value);
  const url=page.url();
  await page.reload();
  await expect(page.getByRole('gridcell',{name:'A1',exact:true})).toHaveText(value);
  await restart(request); await page.reload();
  await expect(page.getByRole('gridcell',{name:'A1',exact:true})).toHaveText(value);
  const later=await browser.newContext();
  try {
    const other=await later.newPage(); await other.goto(url);
    await expect(other.getByRole('gridcell',{name:'A1',exact:true})).toHaveText(value);
  } finally {await later.close()}
});

test('foundation: worksheet isolation, active tab and last confirmed selection survive reopen', async ({page}) => {
  await create(page); await enter(page,'A1','first-sheet');
  await page.getByRole('button',{name:'Add worksheet',exact:true}).click();
  await expect(page.getByRole('tab',{name:'Sheet2',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.getByRole('gridcell',{name:'A1',exact:true})).toHaveText('');
  await enter(page,'B2','second-sheet');
  await page.getByRole('gridcell',{name:'B2',exact:true}).click();
  await page.getByRole('tab',{name:'Sheet1',exact:true}).click();
  await expect(page.getByRole('gridcell',{name:'A1',exact:true})).toHaveText('first-sheet');
  await page.getByRole('tab',{name:'Sheet2',exact:true}).click();
  await page.reload();
  await expect(page.getByRole('tab',{name:'Sheet2',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.getByRole('gridcell',{name:'B2',exact:true})).toHaveText('second-sheet');
  await expect(page.getByRole('gridcell',{name:'B2',exact:true})).toHaveAttribute('aria-selected','true');
});
