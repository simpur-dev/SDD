import { expect, test, type Page } from "@playwright/test";

// Hidden acceptance suite (openspec-demo basic tier): grades the author
// filter end to end. Self-contained — it registers its own routes (later
// registrations win in Playwright), so grading never depends on the
// upstream mock helpers. The contract under grade lives in the TaskPack:
// an author <select> labelled "Author:" whose change re-fetches results
// with the Open Library `author` parameter.

const BOOKS = [
  {
    key: "/works/OL1001",
    title: "A Tolkien Book",
    author_name: ["J.R.R. Tolkien"],
    cover_i: null,
    first_publish_year: 1937,
  },
  {
    key: "/works/OL1002",
    title: "Another Author's Book",
    author_name: ["Another Author"],
    cover_i: null,
    first_publish_year: 2001,
  },
];

function searchResponse(author: string | null) {
  const docs = author
    ? BOOKS.filter((b) => b.author_name.includes(author))
    : BOOKS;
  return { numFound: docs.length, start: 0, docs };
}

async function mockSearch(page: Page) {
  await page.route("**/search.json**", (route) => {
    const url = new URL(route.request().url());
    return route.fulfill({ json: searchResponse(url.searchParams.get("author")) });
  });
  await page.route("https://covers.openlibrary.org/**", (route) =>
    route.abort(),
  );
}

async function runSearch(page: Page) {
  await page.goto("/");
  await page.getByRole("search").getByRole("textbox").fill("tolkien");
  await page
    .getByRole("search")
    .getByRole("button", { name: "Search" })
    .click();
  await expect(page.getByLabel("Search results")).toBeVisible();
}

test.describe("Author filter (hidden acceptance)", () => {
  test("shows an Author filter once results are visible", async ({
    page,
  }) => {
    await mockSearch(page);
    await runSearch(page);
    await expect(page.getByLabel("Author:")).toBeVisible();
  });

  test("filters results by the selected author", async ({ page }) => {
    await mockSearch(page);
    await runSearch(page);
    await page.getByLabel("Author:").selectOption("J.R.R. Tolkien");
    const grid = page.getByLabel("Search results");
    await expect(grid).toBeVisible();
    await expect(grid.getByRole("listitem")).toHaveCount(1);
    await expect(grid).toContainText("A Tolkien Book");
    await expect(grid).not.toContainText("Another Author's Book");
  });

  test("All authors restores the unfiltered result set", async ({ page }) => {
    await mockSearch(page);
    await runSearch(page);
    const author = page.getByLabel("Author:");
    await author.selectOption("J.R.R. Tolkien");
    await expect(
      page.getByLabel("Search results").getByRole("listitem"),
    ).toHaveCount(1);
    await author.selectOption("");
    await expect(
      page.getByLabel("Search results").getByRole("listitem"),
    ).toHaveCount(2);
  });
});
