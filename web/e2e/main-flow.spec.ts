import { expect, test } from "@playwright/test";

test.afterEach(async ({ page }) => {
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth
  }));
  expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth);
});

test("mantém identidade independente entre três cards", async ({ page }, testInfo) => {
  await page.goto("/");
  const skipLink = page.locator(".skip-link");
  await expect(skipLink).toHaveCSS("opacity", "0");
  const initialBox = await skipLink.boundingBox();
  expect(initialBox?.y).toBeLessThan(0);
  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();

  await expect(
    page.getByRole("heading", { name: "Operação Playwright" })
  ).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "Candidatos de corte", level: 2 })
  ).toBeVisible();
  await expect(page.locator(".inspector")).toHaveCount(0);

  const cards = page.locator(".clip-card");
  await expect(cards).toHaveCount(3);

  await page.getByRole("button", { name: "Reproduzir Render concluído sobre mídia física" }).click();
  const first = page.getByLabel("Preview de Render concluído sobre mídia física");
  await expect(first).toBeVisible();
  const firstSource = await first.getAttribute("src");

  await page.getByRole("button", { name: "Reproduzir Terceiro corte independente" }).click();
  const third = page.getByLabel("Preview de Terceiro corte independente");
  await expect(third).toBeVisible();
  const thirdSource = await third.getAttribute("src");

  expect(firstSource).not.toBe(thirdSource);
  await expect(first).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("cards-independentes.png") });
});

test("abre o editor correto e salva nova versão do plano", async (
  { page, request },
  testInfo
) => {
  test.setTimeout(300_000);
  await page.goto("/");
  const card = page.locator(".clip-card").filter({ hasText: "Segundo corte independente" });
  await card.getByRole("button", { name: "Abrir editor" }).click();
  await expect(page.getByRole("dialog")).toContainText("Segundo corte independente");
  for (const backgroundCard of await page.locator(".clip-card").all()) {
    await expect(backgroundCard).toBeHidden();
  }
  const exposedMedia = await page.locator("video").evaluateAll((videos) =>
    videos.some((video) => !video.closest(".editor-player"))
  );
  expect(exposedMedia).toBe(false);

  const start = page.getByLabel("Início (ms)");
  const originalStart = Number(await start.inputValue());
  const physicalProject = testInfo.project.name === "chromium-1280x800";
  if (!physicalProject) {
    await start.fill(String(originalStart + 100));
    await expect(page.locator(".editor-overlay")).toHaveAttribute("data-ui-state", "stale");
    await page.screenshot({ path: testInfo.outputPath("editor-preview-stale.png") });
    const restoredPlanResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        response.url().includes("/edit-plan")
    );
    await start.fill(String(originalStart));
    const restoredPlan = await restoredPlanResponse;
    expect(restoredPlan.ok(), await restoredPlan.text()).toBeTruthy();
    return;
  }

  const savedPlanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().includes("/edit-plan")
  );
  await start.fill(String(originalStart + 100));
  const savedPlan = await savedPlanResponse;
  expect(savedPlan.ok(), await savedPlan.text()).toBeTruthy();
  await expect(page.locator(".sync-state")).toContainText("Alterações salvas", {
    timeout: 5_000
  });
  await expect(page.locator(".editor-overlay")).toHaveAttribute("data-ui-state", "stale");
  await page.screenshot({ path: testInfo.outputPath("editor-preview-stale.png") });

  await page.getByRole("tab", { name: "Saída" }).click();
  const previewSubmissionResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/preview-jobs")
  );
  await page.getByRole("button", { name: "Regenerar preview" }).click();
  const previewSubmission = await previewSubmissionResponse;
  expect(
    previewSubmission.status(),
    await previewSubmission.text()
  ).toBe(202);
  const previewJobId = (await previewSubmission.json()).job.job_id;

  let previewJob;
  for (let attempt = 0; attempt < 2_700; attempt += 1) {
    previewJob = (
      await (
        await request.get(`/api/v1/jobs/${previewJobId}`)
      ).json()
    ).job;
    if (previewJob && ["completed", "failed"].includes(previewJob.state)) break;
    await page.waitForTimeout(100);
  }
  expect(previewJob?.state, previewJob?.error).toBe("completed");
  await page.reload({ waitUntil: "domcontentloaded" });
  const restored = page.locator(".clip-card").filter({ hasText: "Segundo corte independente" });
  await expect(restored.getByRole("button", { name: "Abrir editor" })).toBeEnabled();
});

test("cancela, repete, baixa por Range e valida relatório", async (
  { page, request },
  testInfo
) => {
  test.setTimeout(300_000);
  test.skip(
    testInfo.project.name !== "chromium-1280x800",
    "Fluxo físico destrutivo executado uma vez; a matriz visual roda em todos os projetos."
  );
  await page.goto("/");
  const projectsResponse = await request.get("/api/v1/projects");
  const projects = (await projectsResponse.json()).projects;
  const clipsResponse = await request.get(
    `/api/v1/projects/${projects[0].project_id}/clips`
  );
  const clips = (await clipsResponse.json()).clips;
  const clip = clips.find((item: { title: string }) =>
    item.title.includes("Segundo corte")
  );

  const approval = await request.post("/api/v1/clips/review", {
    data: { clip_ids: [clip.clip_id], decision: "approve" }
  });
  expect(approval.ok()).toBeTruthy();
  const submitted = await request.post(`/api/v1/clips/${clip.clip_id}/render-jobs`);
  expect(submitted.status()).toBe(202);
  const firstJob = (await submitted.json()).job;

  let running;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    running = (await (await request.get(`/api/v1/jobs/${firstJob.job_id}`)).json()).job;
    if (running.state === "running") break;
    await page.waitForTimeout(20);
  }
  expect(running.state).toBe("running");
  const cancelled = await request.post(`/api/v1/jobs/${firstJob.job_id}/cancel`);
  expect(cancelled.ok()).toBeTruthy();

  const retryResponse = await request.post(`/api/v1/jobs/${firstJob.job_id}/retry`);
  expect(retryResponse.status()).toBe(202);
  const retried = (await retryResponse.json()).job;
  expect(retried.job_id).not.toBe(firstJob.job_id);
  expect(retried.parent_job_id).toBe(firstJob.job_id);

  let settled;
  for (let attempt = 0; attempt < 2_700; attempt += 1) {
    settled = (await (await request.get(`/api/v1/jobs/${retried.job_id}`)).json()).job;
    if (["completed", "failed"].includes(settled.state)) break;
    await page.waitForTimeout(100);
  }
  expect(settled.state).toBe("completed");

  const range = await request.get(`/api/v1/clips/${clip.clip_id}/export/download`, {
    headers: { Range: "bytes=0-255" }
  });
  expect(range.status()).toBe(206);
  expect((await range.body()).byteLength).toBe(256);
  const report = await request.get(`/api/v1/jobs/${retried.job_id}/report`);
  expect(report.ok()).toBeTruthy();
  expect((await report.json()).report.events.at(-1).state).toBe("completed");
});
