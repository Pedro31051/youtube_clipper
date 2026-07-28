import { expect, type Locator, type Page, test } from "@playwright/test";

const PROJECT = "Operação Playwright";
const RED = "Candidato vermelho";
const GREEN = "Candidato verde";

function card(page: Page, title: string): Locator {
  return page.locator("article.clip-card").filter({
    has: page.getByRole("heading", { name: title, level: 3 })
  });
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: PROJECT, level: 1 })
  ).toBeVisible();
});

test("E2E-1 — revisa mídias independentes, aprova, rejeita e filtra", async ({
  page
}, testInfo) => {
  const redCard = card(page, RED);
  const greenCard = card(page, GREEN);
  await expect(redCard).toBeVisible();
  await expect(greenCard).toBeVisible();

  await redCard.getByRole("button", { name: `Reproduzir ${RED}` }).click();
  const redVideo = redCard.locator("video");
  await expect(redVideo).toBeVisible();
  await expect
    .poll(() => redVideo.evaluate((video: HTMLVideoElement) => video.currentSrc))
    .not.toBe("");
  const redSource = await redVideo.evaluate(
    (video: HTMLVideoElement) => video.currentSrc
  );

  await greenCard.getByRole("button", { name: `Reproduzir ${GREEN}` }).click();
  const greenVideo = greenCard.locator("video");
  await expect(greenVideo).toBeVisible();
  await expect
    .poll(() => greenVideo.evaluate((video: HTMLVideoElement) => video.currentSrc))
    .not.toBe("");
  const greenSource = await greenVideo.evaluate(
    (video: HTMLVideoElement) => video.currentSrc
  );
  expect(redSource).not.toBe(greenSource);

  await greenCard.getByRole("button", { name: "Aprovar" }).click();
  await expect(greenCard.getByText("Aprovado", { exact: true })).toBeVisible();
  await greenCard.getByRole("button", { name: "Rejeitar" }).click();
  await expect(greenCard.getByText("Rejeitado", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /^Rejeitados/ }).click();
  await expect(card(page, GREEN)).toBeVisible();
  await expect(card(page, RED)).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("e2e-1-revisao.png"),
    fullPage: true
  });
});

test("E2E-2 — edita, invalida preview, regenera, renderiza e baixa", async ({
  page
}, testInfo) => {
  test.setTimeout(90_000);
  let redCard = card(page, RED);
  await redCard.getByRole("button", { name: "Abrir editor" }).click();
  let editor = page.getByRole("dialog", { name: RED });
  await expect(editor).toBeVisible();

  const startInput = editor.getByRole("spinbutton", {
    name: "Início (segundos)"
  });
  const currentStart = Number(await startInput.inputValue());
  await startInput.fill(currentStart < 0.15 ? "0.2" : "0.1");
  await editor.getByRole("tab", { name: "Layout" }).click();
  const layout = editor.getByRole("combobox", { name: "Enquadramento" });
  const currentLayout = await layout.inputValue();
  await layout.selectOption(
    currentLayout === "crop_center" ? "blur_background" : "crop_center"
  );

  await expect(editor.getByText("Alterações salvas")).toBeVisible();
  await expect(editor.getByText("Preview desatualizado")).toBeVisible();
  await editor.getByRole("tab", { name: "Saída" }).click();
  await editor.getByRole("button", { name: "Regenerar preview" }).click();
  await expect(editor.locator(".editor-job")).toContainText("completed", {
    timeout: 45_000
  });
  await expect(editor.getByText(/As versões correspondem/)).toBeVisible();

  await editor.getByRole("button", { name: "Voltar à revisão" }).click();
  redCard = card(page, RED);
  await redCard.getByRole("button", { name: "Aprovar" }).click();
  await expect(redCard.getByText("Aprovado", { exact: true })).toBeVisible();
  await redCard.getByRole("button", { name: "Abrir editor" }).click();
  editor = page.getByRole("dialog", { name: RED });
  await editor.getByRole("tab", { name: "Saída" }).click();
  await expect(
    editor.getByRole("button", { name: "Render final" })
  ).toBeEnabled();
  await editor.getByRole("button", { name: "Render final" }).click();
  await expect(editor.locator(".editor-job")).toContainText("completed", {
    timeout: 45_000
  });
  await editor.getByRole("button", { name: "Voltar à revisão" }).click();

  await page.getByRole("button", { name: /Jobs e exportações/ }).click();
  const deliverable = page.locator(".deliverables article").filter({
    has: page.getByRole("heading", { name: RED })
  });
  await expect(deliverable).toBeVisible();
  await deliverable.getByRole("button", { name: "Exportar" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Baixar MP4" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.mp4$/);
  expect(await download.path()).not.toBeNull();
  await page.screenshot({
    path: testInfo.outputPath("e2e-2-render-exportado.png"),
    fullPage: true
  });
});

test("E2E-3 — recupera restart, cria novo job, cancela e tenta novamente", async ({
  page
}, testInfo) => {
  await page.getByRole("button", { name: /Jobs e exportações/ }).click();
  const interrupted = page.locator(".job-card[data-state='interrupted']").first();
  await expect(interrupted).toContainText("Interrompido");
  await expect(interrupted).toContainText(
    "Servidor reiniciado; o worker anterior não está mais disponível."
  );
  const interruptedId = await interrupted.locator("header code").innerText();

  await interrupted.getByRole("button", { name: "Tentar novamente" }).click();
  const active = page
    .locator(".job-card[data-state='queued'], .job-card[data-state='running']")
    .first();
  await expect(active).toBeVisible();
  const firstRetryId = await active.locator("header code").innerText();
  expect(firstRetryId).not.toBe(interruptedId);
  await active.getByRole("button", { name: "Cancelar" }).click();

  const cancelled = page
    .locator(".job-card[data-state='cancelled']")
    .filter({ hasText: firstRetryId });
  await expect(cancelled).toContainText("Cancelado");
  await cancelled.getByRole("button", { name: "Tentar novamente" }).click();
  const secondActive = page
    .locator(".job-card[data-state='queued'], .job-card[data-state='running']")
    .first();
  await expect(secondActive).toBeVisible();
  const secondRetryId = await secondActive.locator("header code").innerText();
  expect(secondRetryId).not.toBe(firstRetryId);
  await secondActive.getByRole("button", { name: "Cancelar" }).click();

  const reportPromise = page.waitForEvent("download");
  await interrupted.getByRole("link", { name: "Relatório" }).click();
  const report = await reportPromise;
  expect(report.suggestedFilename()).toMatch(/^job_.+\.json$/);
  await page.screenshot({
    path: testInfo.outputPath("e2e-3-recuperacao.png"),
    fullPage: true
  });
});
