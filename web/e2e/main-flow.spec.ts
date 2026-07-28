import { expect, test } from "@playwright/test";

test("mantém identidade independente entre três cards", async ({ page }, testInfo) => {
  await page.goto("/");
  const cards = page.locator(".clip-card");
  await expect(cards).toHaveCount(3);

  await page.getByRole("button", { name: "Reproduzir Segundo corte independente" }).click();
  const second = page.getByLabel("Preview de Segundo corte independente");
  await expect(second).toBeVisible();
  const secondSource = await second.getAttribute("src");

  await page.getByRole("button", { name: "Reproduzir Terceiro corte independente" }).click();
  const third = page.getByLabel("Preview de Terceiro corte independente");
  await expect(third).toBeVisible();
  const thirdSource = await third.getAttribute("src");

  expect(secondSource).not.toBe(thirdSource);
  await expect(second).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("cards-independentes.png"), fullPage: true });
});

test("abre o editor correto e salva nova versão do plano", async ({ page }, testInfo) => {
  await page.goto("/");
  const card = page.locator(".clip-card").filter({ hasText: "Segundo corte independente" });
  await card.getByRole("button", { name: "Abrir editor" }).click();
  await expect(page.getByRole("dialog")).toContainText("Segundo corte independente");

  const start = page.getByLabel("Início (ms)");
  await start.fill("3200");
  await expect(page.locator(".sync-state")).toContainText("Alterações salvas", {
    timeout: 5_000
  });
  await expect(page.getByText("Preview desatualizado")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("editor-preview-stale.png"), fullPage: true });
});
