import { expect, test, type Page } from "@playwright/test";

// Hidden acceptance suite (openspec-demo advanced/challenge tiers): grades
// the delivered delta — author filtering PLUS the modified sort requirement
// (sorting composes with the active filter; either control change resets
// load-more pagination). Self-contained routing, same philosophy as the
// basic suite.

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

async function mockSearch(page: Page, seen: string[]) {
  await page.route("**/search.json**", (route) => {
    const url = new URL(route.request().url());
    seen.push(url.searchParams.toString());
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

test.describe("Sort composes with the author filter (hidden acceptance)", () => {
  test("changing sort under an active filter keeps filtering and refetches with both params", async ({
    page,
  }) => {
    const seen: string[] = [];
    await mockSearch(page, seen);
    await runSearch(page);
    await page.getByLabel("Author:").selectOption("J.R.R. Tolkien");
    await expect(
      page.getByLabel("Search results").getByRole("listitem"),
    ).toHaveCount(1);
    await page.getByLabel("Sort:").selectOption("new");
    const grid = page.getByLabel("Search results");
    await expect(grid).toBeVisible();
    await expect(grid.getByRole("listitem")).toHaveCount(1);
    await expect(grid).toContainText("A Tolkien Book");
    // the refetch carried BOTH the active filter and the new sort
    expect(
      seen.some(
        (params) => params.includes("author=") && params.includes("sort="),
      ),
    ).toBe(true);
  });

  test("changing the author filter preserves the selected sort", async ({
    page,
  }) => {
    const seen: string[] = [];
    await mockSearch(page, seen);
    await runSearch(page);
    await page.getByLabel("Sort:").selectOption("new");
    await page.getByLabel("Author:").selectOption("J.R.R. Tolkien");
    const sort = page.getByLabel("Sort:");
    await expect(sort).toHaveValue("new");
    await expect(
      page.getByLabel("Search results").getByRole("listitem"),
    ).toHaveCount(1);
    await expect(
      seen.some((params) => params.includes("author=")),
    ).toBe(true);
  });
});
