// Grader infrastructure, not a task-specific test or an app endpoint.
import {expect} from '@playwright/test';
export async function restart(request) {
  if (!process.env.E2E_RESTART_CONTROL_URL || !process.env.E2E_RESTART_CONTROL_TOKEN)
    throw new Error('grader-owned restart control is required; never skip');
  const response=await request.post(process.env.E2E_RESTART_CONTROL_URL,{
    headers:{'X-Grader-Token':process.env.E2E_RESTART_CONTROL_TOKEN}
  });
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).restarted).toBe(true);
}
