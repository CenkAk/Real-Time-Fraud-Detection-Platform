import { expect, test } from "@playwright/test";

const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

test("renders live command-center views without an error state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Fraud Command Center" })).toBeVisible();
  await expect(page.getByText("Loading live platform data…")).toBeHidden();

  for (const tab of ["Overview", "Alerts", "Model", "Drift", "System"]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("data-state", "active");
  }
});

test("analyst resolves a deterministic velocity alert as confirmed fraud", async ({
  page,
  request,
}) => {
  const runId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const userId = `e2e-user-${runId}`;
  let alertedTransactionId = "";
  const start = Date.now();

  for (let index = 0; index < 9; index += 1) {
    const transactionId = `e2e-tx-${runId}-${index}`;
    const response = await request.post(`${apiUrl}/transactions`, {
      data: {
        transaction_id: transactionId,
        user_id: userId,
        merchant_id: "e2e-merchant",
        timestamp: new Date(start + index * 1_000).toISOString(),
        amount: 100,
        currency: "USD",
        merchant_category: "electronics",
        country: "US",
        device_id: "e2e-device",
        ip_address: "192.0.2.25",
        channel: "web",
      },
    });
    expect(response.ok()).toBeTruthy();
    const prediction = (await response.json()) as { decision: string };
    if (prediction.decision !== "APPROVE") alertedTransactionId = transactionId;
  }

  expect(alertedTransactionId).not.toBe("");
  await page.goto("/");
  await expect(page.getByText("Loading live platform data…")).toBeHidden();
  await page.getByRole("tab", { name: "Alerts" }).click();
  const alert = page.locator("article").filter({ hasText: alertedTransactionId });
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Confirm fraud" }).click();
  await expect(alert.getByText("FRAUD", { exact: true })).toBeVisible();

  const alertsResponse = await request.get(`${apiUrl}/alerts?limit=100`);
  expect(alertsResponse.ok()).toBeTruthy();
  const alerts = (await alertsResponse.json()) as Array<{
    transaction_id: string;
    status: string;
    resolution: string | null;
  }>;
  expect(alerts.find((item) => item.transaction_id === alertedTransactionId)).toMatchObject({
    status: "RESOLVED",
    resolution: "FRAUD",
  });
});
