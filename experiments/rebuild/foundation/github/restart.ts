import {expect} from '@playwright/test';
export async function restart(request) {
  if (!process.env.E2E_RESTART_CONTROL_URL || !process.env.E2E_RESTART_CONTROL_TOKEN)
    throw new Error('grader-owned restart control is required; never skip');
  const r=await request.post(process.env.E2E_RESTART_CONTROL_URL,{headers:{'X-Grader-Token':process.env.E2E_RESTART_CONTROL_TOKEN}});
  expect(r.ok()).toBeTruthy(); expect((await r.json()).restarted).toBe(true);
}
