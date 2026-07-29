import { expect, test } from "@playwright/test";

test.afterEach(async ({ page }) => {
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth
  }));
  expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth);
});

test("observa jobs e baixa mídia e relatório físicos", async ({ page }, testInfo) => {
  const started = Date.now();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Operação Playwright", level: 1 })
  ).toBeVisible();
  expect(Date.now() - started).toBeLessThan(2_000);

  await page.getByRole("button", { name: /Jobs e exportações/ }).click();
  await expect(
    page.getByRole("heading", { name: "Jobs e exportações", level: 2 })
  ).toBeVisible();

  const physicalDeliverable = page
    .locator(".deliverables")
    .getByRole("article")
    .filter({ hasText: "Render concluído sobre mídia física" });
  await expect(
    physicalDeliverable.getByText("Render pronto")
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("jobs-exportacoes.png"),
    fullPage: true
  });

  await physicalDeliverable.getByRole("button", { name: "Exportar" }).click();
  await expect(page.getByRole("dialog", { name: /Exportar/ })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("dialog-exportacao.png"),
    fullPage: true
  });

  const mediaPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Baixar MP4" }).click();
  const media = await mediaPromise;
  expect(media.suggestedFilename()).toMatch(/\.mp4$/);
  expect(await media.path()).not.toBeNull();

  await page.getByRole("button", { name: "Fechar exportação" }).click();
  const reportPromise = page.waitForEvent("download");
  await page
    .locator(".job-card")
    .filter({ hasText: "Render concluído sobre mídia física" })
    .getByRole("link", { name: "Relatório" })
    .click();
  const report = await reportPromise;
  expect(report.suggestedFilename()).toMatch(/^job_.+\.json$/);
});
