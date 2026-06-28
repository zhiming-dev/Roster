import { expect, test } from "@playwright/test";

// Run with: `npm run dev` (frontend) + `python -m roster` (backend on :8765),
// then `npm run test:e2e`. Verifies the shell renders and a message round-trips.
test("loads the shell and sends a message", async ({ page }) => {
  await page.goto("/app/");

  // Shell is present.
  await expect(page.getByText("Roster")).toBeVisible();
  await expect(page.getByText("Agent lineage")).toBeVisible();

  // Send a message; the optimistic user bubble appears immediately.
  const input = page.getByPlaceholder("Message the Planner…");
  await input.fill("hello team");
  await input.press("Enter");
  await expect(page.getByText("hello team")).toBeVisible();

  // Opening the activity panel reveals the inter-agent feed.
  await page.getByRole("button", { name: "Activity" }).click();
  await expect(page.getByText("Inter-agent activity")).toBeVisible();
});
