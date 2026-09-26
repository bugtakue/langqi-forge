// INTERNAL fault sensitivity tests, not any competition's business tests.
import {test,expect} from '@playwright/test';
test.use({actionTimeout:1500});
test('state survives invalid operations, reload, process restart and multiple identities',async({page,request})=>{
  test.setTimeout(18000);
  const current=page.getByRole('status',{name:'Current user'});
  const assertUser=async(name:string)=>expect(current).toHaveText(name,{timeout:1500});
  async function credentials(id:string,secret:string,action:string){
    await page.getByLabel('Identity',{exact:true}).fill(id);
    await page.getByLabel('Secret',{exact:true}).fill(secret);
    await page.getByRole('button',{name:action,exact:true}).click();
  }
  await page.goto('/');
  await credentials('alpha','alpha-secret','Register');
  await credentials('beta','beta-secret','Register');
  await credentials('alpha','alpha-secret','Login');await assertUser('alpha');
  await credentials('beta','wrong','Login');
  await expect(page.getByRole('alert')).toHaveText('Invalid credentials',{timeout:1500});
  await assertUser('alpha');await page.reload();await assertUser('alpha');
  if(!process.env.E2E_RESTART_CONTROL_URL||!process.env.E2E_RESTART_CONTROL_TOKEN)
    throw new Error('actual restart unavailable');
  const r=await request.post(process.env.E2E_RESTART_CONTROL_URL,{headers:{'X-Grader-Token':process.env.E2E_RESTART_CONTROL_TOKEN}});
  expect(r.ok()).toBeTruthy();expect((await r.json()).restarted).toBe(true);
  await page.reload();await assertUser('alpha');
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await assertUser('');
  await credentials('beta','beta-secret','Login');await assertUser('beta');
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await assertUser('');
  await credentials('alpha','alpha-secret','Login');await assertUser('alpha');
});
