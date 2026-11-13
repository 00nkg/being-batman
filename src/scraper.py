
import requests
import json
import os
import re
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Website URL
BASE_URL = "https://vegamovies.lease"
START_URL = BASE_URL

OUTPUT_FILE = "data.json"

# Browser-like headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        return BeautifulSoup(response.text, "html.parser")

    except requests.RequestException as e:
        print(f"[ERROR] {url}: {e}")
        return None


def extract_download_link(post_url):
    soup = get_soup(post_url)

    if not soup:
        return ""

    # Update selectors according to website HTML
    selectors = [
        "a.download",
        "a.download-link",
        "a[href*='download']",
        ".download-btn a",
        ".download-button"
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element and element.get("href"):
            return urljoin(post_url, element["href"])

    return ""


def scrape_posts():
    soup = get_soup(START_URL)

    if not soup:
        return []

    posts = []

    # Update this selector according to website HTML
    post_elements = soup.select(
        "article, .post, .post-item, .entry"
    )

    for post in post_elements:

        # Extract title
        title_element = post.select_one(
            "h1, h2, h3, .post-title, .entry-title"
        )

        title = (
            title_element.get_text(strip=True)
            if title_element else ""
        )

        # Extract post URL
        link_element = post.select_one(
            "a[href]"
        )

        post_url = (
            urljoin(BASE_URL, link_element["href"])
            if link_element else ""
        )

        # Extract image URL
        image_element = post.select_one("img")

        image_url = ""

        if image_element:
            image_url = (
                image_element.get("data-src")
                or image_element.get("data-lazy-src")
                or image_element.get("src")
                or ""
            )

            image_url = urljoin(BASE_URL, image_url)

        if not title or not post_url:
            continue

        # Extract download link from individual post
        download_link = extract_download_link(post_url)

        posts.append({
            "Title": title,
            "Image URL": image_url,
            "Post URL": post_url,
            "Download Link": download_link
        })

        print(f"[SCRAPED] {title}")

        time.sleep(1)

    return posts


def save_data(posts):
    # Keep previous data if the website temporarily fails
    if not posts:
        print("[WARNING] No posts extracted. Existing data preserved.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(
            posts,
            file,
            ensure_ascii=False,
            indent=4
        )

    print(f"[SUCCESS] Saved {len(posts)} posts to {OUTPUT_FILE}")


if __name__ == "__main__":
    print("[START] Scraper running...")

    posts = scrape_posts()

    save_data(posts)

    print("[DONE] Scraping completed.")
