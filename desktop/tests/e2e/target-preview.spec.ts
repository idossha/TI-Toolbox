import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication } from "@playwright/test";
import { gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { showRunPaneTab } from "./_runPane";
import { analysisRows, analysisTargetText, closeAnalysisTarget, openAnalysisTarget, openOptEditor, closeOptEditor, optRows, optRowSummary } from "./_jobs";

let app: ElectronApplication;
test.afterEach(async () => { await app?.close(); });

for (const surface of ["analyzer", "optimizer"] as const) {
  test(`${surface} replaces read-only sphere preview with a mask without changing the Viewer`, async () => {
    app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-target-preview-")) });
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1500, height: 900 });
    await page.fill("#server-url", process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790");
    await page.fill("#token", process.env.TIT_E2E_TOKEN ?? "mock-token");
    await page.click("#connect");
    await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
    await openPalette(page);
    await page.getByTestId("palette-input").fill("ernie");
    await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();

    await gotoPage(page, "viewer", "Viewer");
    const viewerFrame = page.getByTestId("tetravox-frame");
    await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-renderer", /.+/);
    await viewerFrame.evaluate((node) => node.setAttribute("data-e2e-identity", "independent-viewer"));
    const viewerLayers = page.frameLocator('[data-testid="tetravox-frame"]').getByTestId("fake-embed-layers");
    await expect(viewerLayers.locator("li")).toHaveCount(0);

    await gotoPage(page, surface, surface === "analyzer" ? "Analyzer" : "Optimizer");
    await showRunPaneTab(page, "scene");
    const row = surface === "analyzer" ? analysisRows(page).first() : optRows(page).first();
    const openEditor = () => surface === "analyzer" ? openAnalysisTarget(page, row) : openOptEditor(page, row);
    const closeEditor = () => surface === "analyzer" ? closeAnalysisTarget(page) : closeOptEditor(page);
    const summary = surface === "analyzer" ? analysisTargetText(row) : optRowSummary(row);
    const dialog = await openEditor();
    await dialog.getByRole("radio", { name: "Spherical", exact: true }).click();
    for (const [label, value] of [["X", "10"], ["Y", "20"], ["Z", "30"], ["radius", "8"]] as const) {
      await dialog.getByLabel(`Sphere 1 ${label}`, { exact: true }).fill(value);
    }
    await closeEditor();
    const preview = page.locator(`[data-page-panel="${surface}"]`).getByTestId("target-preview");
    const previewFrame = page.frameLocator(`[data-page-panel="${surface}"] [data-testid="target-preview-frame"]`);
    const layers = previewFrame.getByTestId("fake-embed-layers");
    await expect(layers).toContainText("spherical-target.nii.gz");
    await expect(preview).toContainText("Read-only preview");
    const sphereSummary = await summary.textContent();
    // Even an unsolicited embed pick must not change coordinates in the job's editor.
    await previewFrame.locator("body").evaluate(() => {
      window.parent.postMessage({ tvx: 1, type: "cursor", world: [99, 98, 97] }, window.location.origin);
      window.parent.postMessage({ tvx: 1, type: "pick", world: [99, 98, 97] }, window.location.origin);
    });
    const checked = await openEditor();
    await expect(checked.getByLabel("Sphere 1 X", { exact: true })).toHaveValue("10");
    await expect(checked.getByLabel("Sphere 1 Y", { exact: true })).toHaveValue("20");
    await expect(checked.getByLabel("Sphere 1 Z", { exact: true })).toHaveValue("30");
    await closeEditor();
    await expect(summary).toHaveText(sphereSummary!);

    await page.route("**/api/files/mask?**", (route) => route.fulfill({ json: { path: "/mock/ernie/imported-mask.nii.gz" } }));
    const maskEditor = await openEditor();
    await maskEditor.getByRole("radio", { name: "NIfTI mask", exact: true }).click();
    await maskEditor.getByLabel("Import NIfTI mask").setInputFiles({ name: "imported-mask.nii.gz", mimeType: "application/octet-stream", buffer: Buffer.from("mock mask") });
    await expect(maskEditor.getByRole("textbox", { name: "Imported mask" })).toHaveValue("/mock/ernie/imported-mask.nii.gz");
    await closeEditor();
    await expect(layers).toContainText("mask-target.nii.gz");
    await expect(layers).not.toContainText("spherical-target.nii.gz");
    await expect(viewerLayers.locator("li")).toHaveCount(0);
    await expect(viewerFrame).toHaveAttribute("data-e2e-identity", "independent-viewer");
    await expect(page.getByTestId("viewer-strip-name")).toHaveText("Tetravox");
  });
}
