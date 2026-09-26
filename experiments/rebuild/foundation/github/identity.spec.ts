// INTERNAL tests authored from the public requirement text, not official tests.
// Freeze before any candidate implementation; never relax to match a UI.
import { test, expect } from '@playwright/test';
import {restart} from './restart';

const password = 'Valid-password-123!';

async function register(page, username: string) {
  await page.goto('/');
  await page.getByRole('link', {name:'Sign in', exact:true}).click();
  await page.getByRole('link', {name:'Create an account', exact:true}).click();
  await page.getByRole('textbox', {name:'Username', exact:true}).fill(username);
  await page.getByRole('textbox', {name:'Email', exact:true}).fill(username+'@example.test');
  await page.getByLabel('Password', {exact:true}).fill(password);
  await page.getByLabel('Confirm password', {exact:true}).fill(password);
  await page.getByRole('checkbox', {name:'Agree to the terms', exact:true}).check();
  await page.getByRole('button', {name:'Create account', exact:true}).click();
  await expect(page.getByRole('button', {name:'Sign in', exact:true})).toBeVisible();
}

async function signIn(page, identifier: string, secret=password) {
  await page.getByLabel('Username or email', {exact:true}).fill(identifier);
  await page.getByLabel('Password', {exact:true}).fill(secret);
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
}

test('foundation: registration -> login -> refresh -> restart -> signout -> relogin preserves account', async ({page,request}) => {
  const name='foundation-'+Date.now().toString(36);
  await register(page,name);
  await signIn(page,name+'@example.test');
  await expect(page.getByRole('button', {name:'Account menu',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', {name:'Account menu',exact:true})).toBeVisible();
  await restart(request); await page.reload();
  await page.getByRole('button', {name:'Account menu',exact:true}).click();
  await expect(page.getByText(name,{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Sign out',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Sign out',exact:true});
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.reload();
  await page.getByRole('button', {name:'Account menu',exact:true}).click();
  await page.getByRole('link',{name:'Sign out',exact:true}).click();
  await dialog.getByRole('button',{name:'Confirm sign out',exact:true}).click();
  await page.reload();
  await expect(page.getByRole('button', {name:'Account menu',exact:true})).toHaveCount(0);
  await restart(request); await page.reload();
  await expect(page.getByRole('button', {name:'Account menu',exact:true})).toHaveCount(0);
  await page.getByRole('link',{name:'Sign in',exact:true}).click();
  await signIn(page,name);
  await expect(page.getByRole('button', {name:'Account menu',exact:true})).toBeVisible();
});

test('foundation: invalid registration shows all errors and does not create a session', async ({page}) => {
  await page.goto('/');
  await page.getByRole('link',{name:'Sign in',exact:true}).click();
  await page.getByRole('link',{name:'Create an account',exact:true}).click();
  await page.getByLabel('Username',{exact:true}).fill('-invalid');
  await page.getByLabel('Email',{exact:true}).fill('not-an-email');
  await page.getByLabel('Password',{exact:true}).fill('short');
  await page.getByLabel('Confirm password',{exact:true}).fill('different');
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  for(const text of ['Username format is invalid','Email format is invalid','Password requirements are not satisfied','Agree to terms is required'])
    await expect(page.getByText(text,{exact:true})).toBeVisible();
  await expect(page.getByLabel('Username',{exact:true})).toHaveValue('-invalid');
  await expect(page.getByRole('button',{name:'Account menu',exact:true})).toHaveCount(0);
});

test('foundation: authenticated organization and private repository persist; stranger cannot read private repository', async ({page,browser}) => {
  const name='org-owner-'+Date.now().toString(36);
  const org='org-'+Date.now().toString(36);
  const repo='private-'+Date.now().toString(36);
  await register(page,name); await signIn(page,name);
  await page.getByRole('button',{name:'Account menu',exact:true}).click();
  await page.getByRole('link',{name:'Your organizations',exact:true}).click();
  await page.getByRole('link',{name:'New organization',exact:true}).click();
  await page.getByLabel('Organization name',{exact:true}).fill(org);
  await page.getByLabel('Display name',{exact:true}).fill('Foundation Org');
  await page.getByRole('button',{name:'Create organization',exact:true}).click();
  await expect(page.getByRole('heading').filter({hasText:org})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading').filter({hasText:org})).toBeVisible();
  await page.goto('/');
  await page.getByRole('link',{name:'New repository',exact:true}).click();
  await page.getByLabel('Repository name',{exact:true}).fill(repo);
  await page.getByRole('radio',{name:'Private',exact:true}).check();
  await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check();
  await page.getByRole('button',{name:'Create repository',exact:true}).click();
  await expect(page.getByRole('heading').filter({hasText:repo})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading').filter({hasText:repo})).toBeVisible();
  const url=page.url();
  const outsider=await browser.newContext();
  try {
    const guest=await outsider.newPage(); await guest.goto(url);
    await expect(guest.getByRole('link',{name:/README/})).toHaveCount(0);
    await expect(guest.getByRole('heading').filter({hasText:repo})).toHaveCount(0);
  } finally {await outsider.close()}
});
