import { Browser, BrowserContext, Page, expect, test } from '@playwright/test';
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const ADMIN_EMAIL = process.env['E2E_ADMIN_EMAIL'] ?? '';
const ADMIN_PASSWORD = process.env['E2E_ADMIN_PASSWORD'] ?? '';
const PHOTO = resolve(process.env['E2E_PHOTO'] ?? '../data/images/ISIC_0027175.jpg');

const stamp = Date.now().toString(36);
const password = `Dl#${Math.random().toString(36).slice(2, 10)}Q7v`;
const people = {
  doctor: {
    first: 'Ірина',
    last: `Е2е-Лікар-${stamp}`,
    email: `e2e-${stamp}-doctor@dermalab.test`,
  },
  lab1: { first: 'Тарас', last: `Е2е-Лаборант-${stamp}`, email: `e2e-${stamp}-lab1@dermalab.test` },
  lab2: { first: 'Леся', last: `Е2е-Колега-${stamp}`, email: `e2e-${stamp}-lab2@dermalab.test` },
};

const BACKEND_LOGS_CMD =
  process.env['E2E_BACKEND_LOGS_CMD'] ?? 'docker compose logs --no-log-prefix --since 2m backend';

async function signInLinkFromLog(previous: string | null): Promise<string> {
  for (let i = 0; i < 20; i++) {
    const out = execSync(BACKEND_LOGS_CMD, { cwd: resolve('..'), encoding: 'utf8' });
    const links = [...out.matchAll(/SIGN-IN LINK \(provider=log[^)]*\) to=\S+: (\S+)/g)].map(
      (m) => m[1],
    );
    const last = links.at(-1);
    if (last && last !== previous) return last;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('no sign-in link in the backend log: is EMAIL_PROVIDER=log?');
}

let lastLink: string | null = null;

async function login(
  browser: Browser,
  email: string,
  pwd: string,
): Promise<[BrowserContext, Page]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByLabel('Електронна пошта').fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(pwd);
  await page.getByRole('button', { name: 'Увійти' }).click();
  await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
  lastLink = await signInLinkFromLog(lastLink);
  const url = new URL(lastLink);
  await page.goto(url.pathname + url.search);
  await page.getByRole('button', { name: 'Підтвердити вхід' }).click();
  await expect(page).not.toHaveURL(/\/login/);
  return [context, page];
}

async function createUser(
  admin: Page,
  p: { first: string; last: string; email: string },
  role: 'Лікар' | 'Лабораторний спеціаліст',
): Promise<string> {
  await admin.goto('/admin/users/new');
  await admin.getByLabel("Ім'я").fill(p.first);
  await admin.getByLabel('Прізвище').fill(p.last);
  await admin.getByLabel('Електронна пошта').fill(p.email);
  await admin.getByRole('radio', { name: role }).check();
  await admin.getByRole('button', { name: 'Зберегти' }).click();
  const link = (await admin.getByTestId('password-link').textContent())?.trim() ?? '';
  expect(link).toContain('/set-password#token=');
  await admin.getByRole('button', { name: 'Готово' }).click();
  return link;
}

async function setPassword(browser: Browser, link: string): Promise<void> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(link);
  await page.getByLabel('Новий пароль').fill(password);
  await page.getByLabel('Повторіть пароль').fill(password);
  await page.getByRole('button', { name: 'Зберегти пароль' }).click();
  await expect(page).toHaveURL(/\/login\?passwordSet=1/);
  await context.close();
}

test('full scenario: doctor → referral → lab → approval → notification → PDF → closing', async ({
  browser,
}) => {
  test.skip(!ADMIN_EMAIL || !ADMIN_PASSWORD, 'set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD');
  expect(existsSync(PHOTO), `photo for the case: ${PHOTO}`).toBe(true);

  const [adminCtx, admin] = await login(browser, ADMIN_EMAIL, ADMIN_PASSWORD);
  const links = {
    doctor: await createUser(admin, people.doctor, 'Лікар'),
    lab1: await createUser(admin, people.lab1, 'Лабораторний спеціаліст'),
    lab2: await createUser(admin, people.lab2, 'Лабораторний спеціаліст'),
  };
  await adminCtx.close();
  for (const link of Object.values(links)) await setPassword(browser, link);

  const [, doctor] = await login(browser, people.doctor.email, password);
  await expect(doctor).toHaveURL(/\/doctor\/dashboard/);
  await doctor.goto('/doctor/patients/new');
  await doctor.getByLabel("Ім'я").fill('Ганна');
  await doctor.getByLabel('Прізвище').fill(`Е2е-Пацієнтка-${stamp}`);
  await doctor.getByLabel('Дата народження').fill('1979-03-04');
  await doctor.getByLabel('По батькові').fill('Василівна');
  await doctor.getByLabel('Електронна пошта').fill(`e2e-${stamp}-patient@example.test`);
  await doctor.getByRole('button', { name: 'Зберегти' }).click();
  await expect(doctor).toHaveURL(/\/doctor\/patients\/[0-9a-f-]{36}$/);

  await doctor.getByRole('link', { name: 'Новий випадок' }).click();
  await doctor.getByLabel('Локалізація на тілі').fill('спина');
  await doctor.getByLabel('Клінічний опис / скарги').fill('Вузлик 7 мм з телеангіектазіями (e2e)');
  await doctor.locator('input[type=file]').setInputFiles(PHOTO);
  await doctor.getByRole('button', { name: 'Створити' }).click();
  await expect(doctor).toHaveURL(/\/doctor\/cases\/[0-9a-f-]{36}$/);
  const caseUrl = doctor.url();

  await doctor.getByRole('tab', { name: 'Аналіз ШІ' }).click();
  await doctor.getByRole('button', { name: 'Проаналізувати зображення' }).click();
  await expect(doctor.getByText('Оцінка моделі:')).toBeVisible({ timeout: 90_000 });
  await expect(doctor.getByText('Результат класифікації')).toBeVisible();
  await expect(doctor.getByText('Пояснення рішення моделі')).toBeVisible();
  await expect(doctor.getByAltText(/Теплова карта/)).toBeVisible(); // a real XAI map is shown

  await doctor.getByRole('tab', { name: 'Клінічний висновок' }).click();
  await doctor
    .getByRole('textbox', { name: 'Оцінка лікаря' })
    .fill('Підозра на базальноклітинну карциному');
  await doctor.getByRole('radio', { name: 'Направити на гістопатологію' }).check();
  await doctor.getByLabel('Клінічне питання / підстава направлення').fill('Виключити BCC');
  await doctor.getByRole('button', { name: /Зберегти: направити/ }).click();
  await doctor.getByRole('button', { name: 'Створити направлення' }).click();
  const refText = doctor.getByText(/REF-\d{4}-\d{6}/).first();
  await expect(refText).toBeVisible();
  const refNumber = ((await refText.textContent()) ?? '').match(/REF-\d{4}-\d{6}/)![0];

  const [, lab1] = await login(browser, people.lab1.email, password);
  await expect(lab1).toHaveURL(/\/lab\/referrals/);
  const row = lab1.getByRole('row', { name: new RegExp(refNumber) });
  await expect(row).toContainText('не взято');
  await row.getByRole('link', { name: 'Опрацювати' }).click();
  await lab1.getByRole('button', { name: 'Аналіз ШІ' }).click();
  await expect(lab1.getByAltText(/Теплова карта/)).toBeVisible();
  await lab1.getByRole('button', { name: 'Почати опрацювання' }).click();
  await expect(lab1.getByText('Направлення закріплене за вами')).toBeVisible();
  const referralUrl = lab1.url();

  const [, lab2] = await login(browser, people.lab2.email, password);
  await lab2.goto(referralUrl);
  await expect(lab2.getByText(`В роботі: ${people.lab1.last} ${people.lab1.first}`)).toBeVisible();
  await expect(lab2.getByRole('button', { name: 'Затвердити результат' })).toHaveCount(0);

  await lab1.getByLabel('Номер лабораторного дослідження').fill(`E2E-${stamp}`);
  await lab1.getByRole('button', { name: 'Зберегти чернетку' }).click();
  await expect(lab1.getByRole('status').filter({ hasText: /Чернетку збережено \d/ })).toBeVisible();
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Kyiv' });
  await lab1.getByLabel('Дата дослідження').fill(today);
  await lab1
    .getByRole('textbox', { name: 'Гістопатологічний висновок' })
    .fill('Базальноклітинна карцинома, нодулярний тип');
  await lab1
    .getByRole('textbox', { name: 'Опис (мікроскопічний)' })
    .fill('Гнізда базалоїдних клітин з палісадою. Краї вільні.');
  await lab1.getByRole('button', { name: 'Затвердити результат' }).click();
  await lab1.getByRole('button', { name: 'Затвердити', exact: true }).click();
  await expect(lab1.getByText('Результат затверджено', { exact: false }).first()).toBeVisible();
  const pdfHref = await lab1.getByRole('link', { name: /Відкрити PDF/ }).getAttribute('href');
  const pdf = await lab1.request.get(pdfHref!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()['content-type']).toBe('application/pdf');
  expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-');

  await doctor.goto('/doctor/dashboard');
  const bell = doctor.getByRole('link', { name: /Сповіщення: непрочитаних 1/ });
  await expect(bell).toBeVisible();
  await bell.click();
  await doctor.getByRole('link', { name: `Відкрити результат ${refNumber}` }).click();
  await expect(doctor.getByText('Базальноклітинна карцинома, нодулярний тип')).toBeVisible();
  await expect(doctor.getByText(`${people.lab1.last} ${people.lab1.first}`).first()).toBeVisible();
  const openPdf = doctor.getByRole('link', { name: /Відкрити PDF/ }).first();
  expect(await openPdf.getAttribute('target')).toBe('_blank');
  const viewed = await doctor.request.get((await openPdf.getAttribute('href'))!);
  expect(viewed.headers()['content-disposition']).toBe(
    `inline; filename="${refNumber}-lab-result.pdf"`,
  );
  await expect(doctor.getByRole('link', { name: /Завантажити PDF/ })).toHaveCount(0);
  await expect(doctor.getByRole('link', { name: 'Сповіщення: непрочитаних немає' })).toBeVisible();

  await doctor.goto(caseUrl);
  await doctor.getByRole('tab', { name: 'Клінічний висновок' }).click();
  await doctor
    .getByRole('textbox', { name: 'Оцінка лікаря' })
    .fill('Гістологія: BCC, нодулярний тип. Направлено до онколога.');
  await doctor.getByRole('radio', { name: 'Завершити випадок' }).check();
  await doctor.getByRole('button', { name: /Зберегти: завершити/ }).click();
  await doctor.getByRole('button', { name: 'Завершити випадок', exact: true }).click();
  await expect(
    doctor.getByText('Випадок завершено. Дані доступні лише для перегляду.'),
  ).toBeVisible();
  await expect(doctor.locator('app-case-status').first()).toHaveText('Закритий');
});
