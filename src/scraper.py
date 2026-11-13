
import requests
import json
import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

# ==========================================
# WEBSITE SETTINGS
# ==========================================

BASE_URL = "https://vegamovies.lease"  # YOUR WEBSITE URL
START_URL = BASE_URL

OUTPUT_FILE = "data.json"

MAX_PAGES = 200
REQUEST_DELAY = 1
TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

session = requests.Session()
session.headers.update(HEADERS)

BASE_HOST = urlparse(BASE_URL).netloc.lower()

# ==========================================
# URL HELPERS
# ==========================================

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
    return urlparse(url).netloc.lower() == BASE_HOST


# ==========================================
# REQUEST HTML
# ==========================================

def get_soup(url):
    try:
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "html" not in content_type.lower():
            return None

        return BeautifulSoup(
            response.text,
            "html.parser"
        )

    except requests.RequestException as error:
        print(f"[ERROR] {url}: {error}")
        return None


# ==========================================
# IMAGE EXTRACTION
# ==========================================

def extract_images(container, page_url):
    images = []

    for img in container.select("img"):
        image_url = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("data-original-src")
            or img.get("src")
        )

        # Try srcset if src is missing
        if not image_url and img.get("srcset"):
            image_url = img["srcset"].split(",")[0].strip().split(" ")[0]

        if image_url:
            image_url = clean_url(image_url, page_url)

            if image_url:
                images.append({
                    "URL": image_url,
                    "Alt": img.get("alt", "")
                })

    # Background images
    for element in container.select("[style]"):
        style = element.get("style", "")

        matches = re.findall(
            r"url\(['\"]?(.*?)['\"]?\)",
            style,
            re.I
        )

        for match in matches:
            image_url = clean_url(match, page_url)

            if image_url:
                images.append({
                    "URL": image_url,
                    "Alt": "Background image"
                })

    # Remove duplicate images
    unique = {}

    for image in images:
        unique[image["URL"]] = image

    return list(unique.values())


# ==========================================
# ALL LINKS EXTRACTION
# ==========================================

def extract_links(container, page_url):
    links = []

    for tag in container.select("a[href]"):
        href = clean_url(tag.get("href"), page_url)

        if not href:
            continue

        links.append({
            "Text": tag.get_text(" ", strip=True),
            "URL": href,
            "Title": tag.get("title", "")
        })

    # Remove duplicate URLs
    unique = {}

    for link in links:
        unique[link["URL"]] = link

    return list(unique.values())


# ==========================================
# DOWNLOAD / WATCH LINK DETECTION
# ==========================================

DOWNLOAD_WORDS = [
    "download", "dl", "drive.google",
    "mega.nz", "mediafire", "gofile",
    "download.php", "direct-download",
    "file-download"
]

WATCH_WORDS = [
    "watch", "player", "stream",
    "embed", "play", "video"
]


def classify_links(links):
    downloads = []
    watch_links = []

    for link in links:
        text = link["Text"].lower()
        url = link["URL"].lower()

        combined = text + " " + url

        if any(word in combined for word in DOWNLOAD_WORDS):
            downloads.append(link)

        if any(word in combined for word in WATCH_WORDS):
            watch_links.append(link)

    return downloads, watch_links


# ==========================================
# POST TITLE
# ==========================================

def extract_title(container):
    selectors = [
        "h1", "h2", "h3", "h4",
        ".post-title",
        ".entry-title",
        ".title",
        ".movie-title"
    ]

    for selector in selectors:
        element = container.select_one(selector)

        if element:
            title = element.get_text(" ", strip=True)

            if title:
                return title

    # Fallback: image or anchor title
    for element in container.select("a[title], img[alt]"):
        title = element.get("title") or element.get("alt")

        if title and len(title.strip()) > 2:
            return title.strip()

    return ""


# ==========================================
# POST URL
# ==========================================

def extract_post_url(container, page_url):
    candidates = []

    for link in container.select("a[href]"):
        href = clean_url(link.get("href"), page_url)

        if not href or not same_domain(href):
            continue

        if href == page_url:
            continue

        text = link.get_text(" ", strip=True)
        has_image = link.find("img") is not None

        score = 0

        if link.find(["h1", "h2", "h3", "h4"]):
            score += 5

        if text:
            score += 2

        if has_image:
            score += 2

        if link.get("title"):
            score += 1

        candidates.append((score, href))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    return ""


# ==========================================
# SMART POST CONTAINER DETECTION
# ==========================================

def find_post_containers(soup):

    selectors = [
        "article",
        ".post",
        ".posts",
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
        ".card",
        ".video-item",
        ".download-item"
    ]

    containers = []

    for selector in selectors:
        containers.extend(soup.select(selector))

    # Fallback: detect parents containing links and images
    if not containers:
        for link in soup.select("a[href]"):
            if link.find("img") or link.get_text(strip=True):
                parent = link

                for _ in range(4):
                    if parent.parent and parent.parent.name not in (
                        "body", "html"
                    ):
                        parent = parent.parent

                containers.append(parent)

    # Remove duplicate objects
    unique = {}
    for container in containers:
        key = str(container)[:500]
        unique[key] = container

    return list(unique.values())


# ==========================================
# SINGLE POST EXTRACTION
# ==========================================

def extract_post(container, page_url):

    title = extract_title(container)
    post_url = extract_post_url(container, page_url)

    images = extract_images(container, page_url)
    links = extract_links(container, page_url)

    if not title and not images:
        return None

    if not post_url:
        post_url = page_url

    # Fetch individual post page for more links/images
    detail_soup = get_soup(post_url) if post_url != page_url else None

    if detail_soup:
        detail_images = extract_images(
            detail_soup, post_url
        )

        detail_links = extract_links(
            detail_soup, post_url
        )

        images.extend(detail_images)
        links.extend(detail_links)

        if not title:
            title = extract_title(detail_soup)

    # Remove duplicates
    unique_images = {
        image["URL"]: image for image in images
    }

    unique_links = {
        link["URL"]: link for link in links
    }

    images = list(unique_images.values())
    links = list(unique_links.values())

    downloads, watch_links = classify_links(links)

    return {
        "Title": title,
        "Image URL": images[0]["URL"] if images else "",
        "All Images": images,
        "Post URL": post_url,
        "Download Link": downloads[0]["URL"] if downloads else "",
        "All Download Links": downloads,
        "Watch / Player Links": watch_links,
        "All Links": links,
        "Source Page": page_url
    }


# ==========================================
# NEXT PAGE DETECTION
# ==========================================

def find_next_page(soup, current_url):

    # rel="next"
    next_tag = soup.select_one(
        'a[rel="next"], link[rel="next"]'
    )

    if next_tag and next_tag.get("href"):
        url = clean_url(next_tag["href"], current_url)

        if url and same_domain(url):
            return url

    next_words = [
        "next", "older", "older posts",
        "next page", "→", "»", "›"
    ]

    for link in soup.select("a[href]"):

        text = link.get_text(" ", strip=True).lower()
        aria = link.get("aria-label", "").lower()
        title = link.get("title", "").lower()
        classes = " ".join(link.get("class", [])).lower()

        combined = " ".join([
            text, aria, title, classes
        ])

        if any(word in combined for word in next_words):

            url = clean_url(
                link.get("href"), current_url
            )

            if url and same_domain(url):
                return url

    # Common pagination selectors
    selectors = [
        ".next a",
        ".pagination-next a",
        ".nav-next a",
        ".next-page a",
        "a.next"
    ]

    for selector in selectors:
        tag = soup.select_one(selector)

        if tag and tag.get("href"):
            url = clean_url(tag["href"], current_url)

            if url and same_domain(url):
                return url

    return ""


# ==========================================
# MAIN PAGINATION SCRAPER
# ==========================================

def scrape_website():

    current_url = START_URL

    visited_pages = set()
    all_posts = {}

    page_count = 0

    while current_url and page_count < MAX_PAGES:

        current_url = clean_url(
            current_url, START_URL
        )

        if not current_url or not same_domain(current_url):
            break

        if current_url in visited_pages:
            print("[STOP] Repeated page detected")
            break

        visited_pages.add(current_url)
        page_count += 1

        print(f"\n[PAGE {page_count}] {current_url}")

        soup = get_soup(current_url)

        if not soup:
            break

        containers = find_post_containers(soup)

        print(f"[FOUND] {len(containers)} possible containers")

        for container in containers:

            try:
                post = extract_post(
                    container, current_url
                )

                if not post:
                    continue

                key = post["Post URL"]

                # Keep only first occurrence
                if key not in all_posts:
                    all_posts[key] = post

                    print(
                        f"[POST] {post['Title'][:70]}"
                    )

                time.sleep(REQUEST_DELAY)

            except Exception as error:
                print(f"[POST ERROR] {error}")

        next_url = find_next_page(
            soup, current_url
        )

        if not next_url:
            print("[INFO] No next page found")
            break

        current_url = next_url

        time.sleep(REQUEST_DELAY)

    return list(all_posts.values()), page_count


# ==========================================
# SAVE JSON
# ==========================================

def save_data(posts, page_count):

    if not posts:
        print("[WARNING] No posts found. Old JSON preserved.")
        return

    data = {
        "Website": BASE_URL,
        "Total Pages Scraped": page_count,
        "Total Posts": len(posts),
        "Posts": posts
    }

    with open(
        OUTPUT_FILE, "w", encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n================================")
    print(f"TOTAL PAGES: {page_count}")
    print(f"TOTAL POSTS: {len(posts)}")
    print(f"OUTPUT: {OUTPUT_FILE}")
    print("================================")


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":

    print("SMART WEBSITE SCRAPER STARTED")

    posts, pages = scrape_website()

    save_data(posts, pages)

    print("SCRAPING COMPLETED")
