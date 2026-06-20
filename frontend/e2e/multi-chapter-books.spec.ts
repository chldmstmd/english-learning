import { test, expect } from "@playwright/test";

const BASE = "http://localhost:5173";

test("multi-chapter book golden path", async ({ page }) => {
  // --- login ---
  await page.goto(`${BASE}/login`);
  await page.getByPlaceholder("you@example.com").fill("test@example.com");
  await page.getByPlaceholder("••••••").fill("test1234");
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(`${BASE}/`);
  await expect(page.getByRole("heading", { name: "文章" })).toBeVisible();

  // --- create a book ---
  const bookTitle = `E2E 测试书 ${Date.now()}`;
  await page.getByRole("button", { name: "+ 创建书" }).click();
  await page.getByPlaceholder("书名").fill(bookTitle);
  await page.getByRole("button", { name: "创建", exact: true }).click();

  // navigates to /books/:id
  await page.waitForURL(/\/books\//);
  await expect(page.getByRole("heading", { name: bookTitle })).toBeVisible();
  await page.screenshot({ path: "e2e-1-book-detail-empty.png", fullPage: true });

  // --- add chapter 1 (long enough to scroll, so progress-save fires) ---
  const longText = Array.from(
    { length: 40 },
    (_, i) => `This is sentence number ${i + 1} in the first chapter of the test book.`
  ).join(" ");
  await page.getByRole("button", { name: "+ 添加章节" }).click();
  await page.getByPlaceholder("章节标题").fill("第一章 黎明");
  await page.getByPlaceholder("在此粘贴本章英文...").fill(longText);
  await page.getByRole("button", { name: "提交" }).click();
  await expect(page.getByText("第一章 黎明")).toBeVisible();

  // --- add chapter 2 ---
  await page.getByRole("button", { name: "+ 添加章节" }).click();
  await page.getByPlaceholder("章节标题").fill("第二章 旅人");
  await page
    .getByPlaceholder("在此粘贴本章英文...")
    .fill("A traveler walked along the dusty road toward town.");
  await page.getByRole("button", { name: "提交" }).click();
  await expect(page.getByText("第二章 旅人")).toBeVisible();
  await expect(page.getByText("2 章", { exact: true })).toBeVisible();
  await page.screenshot({ path: "e2e-2-book-detail-2-chapters.png", fullPage: true });

  // --- open chapter 1 via "继续阅读" ---
  await page.getByRole("button", { name: "继续阅读" }).click();
  await page.waitForURL(/\/articles\//);
  // reader chapter nav: ch1 has 下一章 / 目录 but no 上一章
  await expect(page.getByRole("link", { name: "下一章 →" })).toBeVisible();
  await expect(page.getByRole("link", { name: "目录" })).toBeVisible();
  await expect(page.getByRole("link", { name: "← 上一章" })).toHaveCount(0);
  await page.screenshot({ path: "e2e-3-reader-ch1.png", fullPage: true });

  // --- scroll the reader so progress is recorded (debounced 600ms) ---
  const scroller = page.locator("div.flex-1.overflow-y-auto");
  await scroller.evaluate((el) => el.scrollTo({ top: el.scrollHeight / 2 }));
  await page.waitForTimeout(1200); // let the debounced PUT /progress fire

  // --- next chapter ---
  await page.getByRole("link", { name: "下一章 →" }).click();
  await page.waitForTimeout(500);
  await expect(page.getByRole("link", { name: "← 上一章" })).toBeVisible();
  await expect(page.getByRole("link", { name: "下一章 →" })).toHaveCount(0);
  await page.screenshot({ path: "e2e-4-reader-ch2.png", fullPage: true });

  // --- back to list, confirm book card shows progress ---
  await page.goto(`${BASE}/`);
  const card = page.locator("a", { hasText: bookTitle });
  await expect(card).toBeVisible();
  await expect(card).toContainText("读到第");

  // chapters must NOT leak into the standalone article list
  await expect(page.getByText("第一章 黎明")).toHaveCount(0);
  await expect(page.getByText("第二章 旅人")).toHaveCount(0);

  await page.screenshot({ path: "e2e-5-list-with-book-card.png", fullPage: true });

  console.log("BOOK_TITLE=" + bookTitle);
});
