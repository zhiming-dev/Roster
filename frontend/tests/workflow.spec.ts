import { expect, test } from "@playwright/test";

test("approved plan becomes a reviewed, tested, downloadable patch", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Code change", exact: true }).click();
  await page.getByLabel("What should change?").fill("Change VALUE in src/app.py to 2");
  await page.getByLabel("Test command", { exact: true }).fill("python3 -c \"from pathlib import Path; assert Path('src/app.py').read_text().strip() == 'VALUE = 2'\"");
  await page.getByRole("button", { name: "Prepare plan" }).click();
  await expect(page.getByRole("button", { name: "Approve plan and run" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download approved patch" })).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "Code change", exact: true }).click();
  await page.getByRole("button", { name: "Approve plan and run" }).click();
  await expect(page.getByRole("button", { name: "Approve diff and prepare patch" })).toBeVisible();
  await expect(page.getByText("Test evidence · exit 0")).toBeVisible();
  await page.screenshot({ path: "/tmp/roster_workflow_review.png", fullPage: true });
  await page.getByRole("button", { name: "Approve diff and prepare patch" }).click();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download approved patch" }).click();
  const download = await downloadEvent;
  await download.saveAs("/tmp/roster_workflow_download.patch");
  expect(download.suggestedFilename()).toBe("change.patch");
  expect(errors).toEqual([]);
});
