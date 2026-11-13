
import requests
import json
import time
import re

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag

# =====================================
# WEBSITE SETTINGS
# =====================================

BASE_URL = "https://vegamovies.lease"  # YOUR WEBSITE URL
START_URL = BASE_URL

OUTPUT_FILE = "data.json"

MAX_PAGES = 3
TIMEOUT = 10
REQUEST_DELAY = 1

# =====================================
# HEADERS
# =====================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9"
}

session = requests.Session()
session.headers.update(HEADERS)

BASE_HOST = urlparse(BASE_URL).netloc.lower()


# =====================================
# URL CLEANER
# =====================================

def clean_url(url, base):

    if not url:
        return ""

    url = urljoin(base, url.strip())
    url, _ = urldefrag(url)

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    return url


def same_domain(url):

    return (
        urlparse(url).netloc.lower()
        == BASE_HOST
    )


# =====================================
# FETCH WEBSITE
# =====================================

def get_soup(url):

    try:

        response = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "html" not in content_type.lower():
            print("[WARNING] Not an HTML page:", url)
            return None

        return BeautifulSoup(
            response.text,
            "html.parser"
        )

    except requests.Timeout:

        print("[TIMEOUT] Website took too long:", url)
        return None

    except requests.RequestException as error:

        print("[ERROR]", error)
        return None


# =====================================
# EXTRACT IMAGES
# =====================================

def extract_images(container, page_url):

    images = []

    for img in container.select("img"):

        src = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("src")
        )

        if not src and img.get("srcset"):

            src = (
                img["srcset"]
                .split(",")[0]
                .strip()
                .split(" ")[0]
            )

        if src:

            image_url = clean_url(src, page_url)

            if image_url:
                images.append(image_url)

    return list(set(images))


# =====================================
# EXTRACT ALL LINKS
# =====================================

def extract_links(container, page_url):

    links = []

    for a in container.select("a[href]"):

        href = clean_url(
            a.get("href"), page_url
        )

        if not href:
            continue

        links.append({
            "Text": a.get_text(" ", strip=True),
            "URL": href
        })

    unique = {
        link["URL"]: link
        for link in links
    }

    return list(unique.values())


# =====================================
# DOWNLOAD LINK DETECTION
# =====================================

DOWNLOAD_WORDS = [
    "download",
    "direct download",
    "mediafire",
    "gofile",
    "mega.nz",
    "drive.google",
    "download.php",
    "file-download"
]

WATCH_WORDS = [
    "watch",
    "player",
    "stream",
    "embed",
    "play",
    "video"
]


def classify_links(links):

    downloads = []
    watch = []

    for link in links:

        combined = (
            link["Text"] + " " + link["URL"]
        ).lower()

        if any(
            word in combined
            for word in DOWNLOAD_WORDS
        ):
            downloads.append(link)

        if any(
            word in combined
            for word in WATCH_WORDS
        ):
            watch.append(link)

    return downloads, watch


# =====================================
# EXTRACT TITLE
# =====================================

def extract_title(container):

    selectors = [
        "h1",
        "h2",
        "h3",
        "h4",
        ".post-title",
        ".entry-title",
        ".movie-title",
        ".title"
    ]

    for selector in selectors:

        element = container.select_one(selector)

        if element:

            title = element.get_text(
                " ", strip=True
            )

            if title:
                return title

    for element in container.select(
        "a[title], img[alt]"
    ):

        title = (
            element.get("title")
            or element.get("alt")
        )

        if title:
            return title.strip()

    return ""


# =====================================
# EXTRACT POST URL
# =====================================

def extract_post_url(container, page_url):

    for a in container.select("a[href]"):

        href = clean_url(
            a.get("href"), page_url
        )

        if not href or not same_domain(href):
            continue

        if href == page_url:
            continue

        if (
            a.find(["h1", "h2", "h3", "h4"])
            or a.find("img")
            or a.get_text(strip=True)
        ):
            return href

    return page_url


# =====================================
# FIND POST CONTAINERS
# =====================================

def find_post_containers(soup):

    selectors = [
        "article",
        ".post",
        ".post-item",
        ".post-box",
        ".post-card",
        ".entry",
        ".entry-card",
        ".blog-post",
        ".movie",
        ".movie-item",
        ".movie-card",
        ".item",
        ".grid-item",
        ".video-item",
        ".download-item"
    ]

    containers = []

    for selector in selectors:

        containers.extend(
            soup.select(selector)
        )

    # Fallback
    if not containers:

        for link in soup.select("a[href]"):

            if link.find("img"):

                parent = link.parent

                if parent:
                    containers.append(parent)

    # Deduplicate using object identity
    unique = {}

    for container in containers:

        unique[id(container)] = container

    return list(unique.values())


# =====================================
# EXTRACT POST DATA
# =====================================

def extract_post(container, page_url):

    title = extract_title(container)

    post_url = extract_post_url(
        container, page_url
    )

    images = extract_images(
        container, page_url
    )

    links = extract_links(
        container, page_url
    )

    if not title and not images:
        return None

    downloads, watch = classify_links(links)

    return {

        "Title": title,

        "Image URL": (
            images[0] if images else ""
        ),

        "All Images": images,

        "Post URL": post_url,

        "Download Link": (
            downloads[0]["URL"]
            if downloads else ""
        ),

        "All Download Links": downloads,

        "Watch / Player Links": watch,

        "All Links": links,

        "Source Page": page_url

    }


# =====================================
# FIND NEXT PAGE
# =====================================

def find_next_page(soup, current_url):

    next_tag = soup.select_one(
        'a[rel="next"]'
    )

    if next_tag:

        url = clean_url(
            next_tag.get("href"),
            current_url
        )

        if url and same_domain(url):
            return url

    next_words = [
        "next",
        "older",
        "next page",
        "»",
        "›"
    ]

    for a in soup.select("a[href]"):

        text = (
            a.get_text(" ", strip=True)
            + " "
            + a.get("aria-label", "")
            + " "
            + a.get("title", "")
            + " "
            + " ".join(a.get("class", []))
        ).lower()

        if any(word in text for word in next_words):

            url = clean_url(
                a.get("href"),
                current_url
            )

            if url and same_domain(url):
                return url

    return ""


# =====================================
# MAIN SCRAPER
# =====================================

def scrape_website():

    current_url = START_URL

    visited_pages = set()
    all_posts = {}

    page_count = 0

    while current_url and page_count < MAX_PAGES:

        current_url = clean_url(
            current_url, START_URL
        )

        if not current_url:
            break

        if not same_domain(current_url):
            print("[STOP] External domain detected")
            break

        if current_url in visited_pages:
            print("[STOP] Duplicate page detected")
            break

        visited_pages.add(current_url)

        page_count += 1

        # REQUIRED PROGRESS LOG
        print(
            f"\nScraping page: {current_url}",
            flush=True
        )

        soup = get_soup(current_url)

        if soup is None:
            print("[SKIP] Page could not be loaded")
            break

        containers = find_post_containers(soup)

        print(
            f"[INFO] Found {len(containers)} containers",
            flush=True
        )

        for container in containers:

            try:

                post = extract_post(
                    container, current_url
                )

                if not post:
                    continue

                post_url = post["Post URL"]

                if post_url not in all_posts:

                    all_posts[post_url] = post

                    print(
                        "[POST]", post["Title"][:70],
                        flush=True
                    )

            except Exception as error:

                print("[POST ERROR]", error)

        # Stop after 3 pages
        if page_count >= MAX_PAGES:
            print("[INFO] Maximum 3 pages reached")
            break

        next_url = find_next_page(
            soup, current_url
        )

        if not next_url:
            print("[INFO] Next page not found")
            break

        current_url = next_url

        time.sleep(REQUEST_DELAY)

    return list(all_posts.values()), page_count


# =====================================
# SAVE JSON
# =====================================

def save_data(posts, page_count):

    if not posts:

        print(
            "[WARNING] No posts found. "
            "Existing data.json preserved."
        )

        return

    data = {

        "Website": BASE_URL,

        "Total Pages Scraped": page_count,

        "Total Posts": len(posts),

        "Posts": posts

    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n==============================")
    print("SCRAPING COMPLETED")
    print("TOTAL PAGES:", page_count)
    print("TOTAL POSTS:", len(posts))
    print("SAVED:", OUTPUT_FILE)
    print("==============================")


# =====================================
# START
# =====================================

if __name__ == "__main__":

    print("SMART SCRAPER STARTED", flush=True)

    try:

        posts, pages = scrape_website()

        save_data(posts, pages)

    finally:

        session.close()

    print("PROGRAM FINISHED", flush=True)
