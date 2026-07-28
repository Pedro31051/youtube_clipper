import { expect, test } from "@playwright/test";

test("observa jobs e baixa mídia e relatório físicos", async ({ page }, testInfo) => {
  const navigationStarted = performance.now();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Operação Playwright", level: 1 })).toBeVisible();
  expect(performance.now() - navigationStarted).toBeLessThan(2_000);

  await page.getByRole("button", { name: /Jobs e exportações/ }).click();
  await expect(page.getByRole("heading", { name: "Jobs e exportações", level: 2 })).toBeVisible();
  await page.getByRole("button", { name: /Operação Playwright/ }).click();
  await expect(page.getByRole("heading", { name: "Operação Playwright", level: 2 })).toBeVisible();

  const interactionElapsed = await page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        const started = performance.now();
        const button = document.querySelector<HTMLButtonElement>(".operation-nav");
        button?.click();
        requestAnimationFrame(() => resolve(performance.now() - started));
      })
  );
  await expect(page.getByRole("heading", { name: "Jobs e exportações", level: 2 })).toBeVisible();
  expect(interactionElapsed).toBeLessThan(100);

  await expect(
    page.locator(".deliverables").getByRole("heading", {
      name: "Render concluído sobre mídia física"
    })
  ).toBeVisible();
  await expect(page.getByText("Render pronto")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("jobs-exportacoes.png"),
    fullPage: true
  });

  await page.getByRole("button", { name: "Exportar" }).click();
  await expect(page.getByRole("dialog", { name: /Exportar/ })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("dialog-exportacao.png"),
    fullPage: true
  });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Baixar MP4" }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  expect(download.suggestedFilename()).toMatch(/\.mp4$/);
  expect(downloadPath).not.toBeNull();

  await page.getByRole("button", { name: "Fechar exportação" }).click();
  const reportPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Relatório" }).click();
  const report = await reportPromise;
  expect(report.suggestedFilename()).toMatch(/^job_.+\.json$/);
});
