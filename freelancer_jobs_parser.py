import argparse
import csv
import json
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.freelancer.com.ua"
JOBS_URL = f"{BASE_URL}/jobs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}

PROJECT_PATH_PATTERN = re.compile(r"/projects/[\w\-]+/[\w\-]+")
LEFT_PATTERN = re.compile(r"\b\d+\s*(?:дні\(-в\)|годин\(-и\)|hours?|days?)\s+left\b", re.IGNORECASE)
BID_PATTERN = re.compile(r"(?:\$|€|£)\s?\d+[\d,\.\s]*(?:\s?-\s?(?:\$|€|£)?\s?\d+[\d,\.\s]*)?|\d+[\d,\.\s]*(?:\s?/\s?hr)", re.IGNORECASE)


@dataclass
class JobItem:
    title: str
    vacancy_url: str
    hard_skills: list[str]
    summary: str
    budget_or_rate: str
    avg_bid: str
    time_left: str
    search_keywords: list[str]
    search_mode: str
    search_query: str
    search_timestamp: str
    source_pages: str
    scraped_from: str


def fetch_html(url: str, max_retries: int = 3, timeout: int = 25) -> str:
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            last_error = error
            if attempt < max_retries:
                sleep_for = 1.5 * attempt
                time.sleep(sleep_for)

    raise RuntimeError(f"Не вдалося завантажити {url}: {last_error}")


def extract_avg_bid(text: str) -> str:
    lowered = text.lower()
    marker = "average bid"
    idx = lowered.find(marker)
    if idx == -1:
        return ""

    chunk = text[max(0, idx - 20): idx + len(marker) + 5]
    match = BID_PATTERN.search(chunk)
    return match.group(0).strip() if match else ""


def extract_budget_or_rate(text: str, avg_bid: str) -> str:
    candidates = [m.group(0).strip() for m in BID_PATTERN.finditer(text)]
    for candidate in candidates:
        if candidate != avg_bid:
            return candidate
    return ""


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def extract_hard_skills(container: BeautifulSoup) -> list[str]:
    skills: list[str] = []

    for anchor in container.select('a[href*="/jobs/"]'):
        href = anchor.get("href", "")
        if not href:
            continue

        href_lower = href.lower()
        if (
            href_lower.rstrip("/") in {"/jobs", "jobs"}
            or "/jobs/2" in href_lower
            or "/jobs/3" in href_lower
            or "/jobs/100" in href_lower
        ):
            continue

        text = normalize_space(anchor.get_text(" ", strip=True))
        if not text:
            continue

        if text.lower() in {"verified", "терміновий", "місцевий", "приватний", "прихований"}:
            continue

        skills.append(text)

    return list(dict.fromkeys(skills))


def parse_jobs_from_page(html: str, page_url: str) -> list[JobItem]:
    soup = BeautifulSoup(html, "html.parser")
    seen_urls: set[str] = set()
    jobs: list[JobItem] = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not PROJECT_PATH_PATTERN.search(href):
            continue

        job_url = urljoin(BASE_URL, href)
        if job_url in seen_urls:
            continue

        title = normalize_space(link.get_text(" ", strip=True))
        if not title:
            continue

        container = link
        for _ in range(5):
            if container.parent is None:
                break
            container = container.parent
            container_text = normalize_space(container.get_text(" ", strip=True))
            if title in container_text and len(container_text) > len(title) + 30:
                break

        container_text = normalize_space(container.get_text(" ", strip=True))
        if not container_text:
            continue

        time_left_match = LEFT_PATTERN.search(container_text)
        time_left = time_left_match.group(0).strip() if time_left_match else ""

        avg_bid = extract_avg_bid(container_text)
        budget_or_rate = extract_budget_or_rate(container_text, avg_bid)
        hard_skills = extract_hard_skills(container)

        summary = container_text
        summary = summary.replace(title, "", 1).strip()
        summary = summary[:500]

        jobs.append(
            JobItem(
                title=title,
                vacancy_url=job_url,
                hard_skills=hard_skills,
                summary=summary,
                budget_or_rate=budget_or_rate,
                avg_bid=avg_bid,
                time_left=time_left,
                search_keywords=[],
                search_mode="",
                search_query="",
                search_timestamp="",
                source_pages="",
                scraped_from=page_url,
            )
        )
        seen_urls.add(job_url)

    return jobs


def make_page_url(page: int) -> str:
    if page <= 1:
        return JOBS_URL
    return f"{JOBS_URL}/{page}"


def unique_by_url(items: Iterable[JobItem]) -> list[JobItem]:
    result: list[JobItem] = []
    seen: set[str] = set()
    for item in items:
        if item.vacancy_url in seen:
            continue
        seen.add(item.vacancy_url)
        result.append(item)
    return result


def parse_keywords(raw_keywords: list[str]) -> list[str]:
    keywords: list[str] = []
    for raw in raw_keywords:
        parts = [part.strip().lower() for part in raw.split(",")]
        keywords.extend([part for part in parts if part])
    return list(dict.fromkeys(keywords))


def filter_jobs_by_keywords(items: list[JobItem], keywords: list[str], mode: str) -> list[JobItem]:
    if not keywords:
        return items

    filtered: list[JobItem] = []
    for item in items:
        haystack = f"{item.title} {item.summary}".lower()
        checks = [keyword in haystack for keyword in keywords]

        if mode == "all" and all(checks):
            filtered.append(item)
        elif mode == "any" and any(checks):
            filtered.append(item)

    return filtered


def build_search_query_label(keywords: list[str], mode: str) -> str:
    if not keywords:
        return "Без фільтра по ключових словах"

    if len(keywords) == 1:
        return f"Ключове слово: {keywords[0]}"

    return f"Ключові слова ({mode}): {', '.join(keywords)}"


def scrape_jobs(pages: int, min_delay: float, max_delay: float) -> list[JobItem]:
    if pages < 1:
        raise ValueError("Параметр pages має бути >= 1")

    all_items: list[JobItem] = []
    for page in range(1, pages + 1):
        url = make_page_url(page)
        print(f"[INFO] Завантажую сторінку {page}/{pages}: {url}")
        html = fetch_html(url)
        page_items = parse_jobs_from_page(html, page_url=url)
        print(f"[INFO] Знайдено на сторінці: {len(page_items)} вакансій")
        all_items.extend(page_items)

        if page < pages:
            pause = random.uniform(min_delay, max_delay)
            time.sleep(pause)

    return unique_by_url(all_items)


def save_csv(items: list[JobItem], filepath: Path) -> None:
    if not items:
        filepath.write_text("", encoding="utf-8")
        return

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(items[0]).keys()))
        writer.writeheader()
        for item in items:
            row = asdict(item)
            row["hard_skills"] = " | ".join(item.hard_skills)
            row["search_keywords"] = " | ".join(item.search_keywords)
            writer.writerow(row)


def save_json(items: list[JobItem], filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in items]
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Парсер вакансій з freelancer.com.ua/jobs"
    )
    parser.add_argument("--pages", type=int, default=2, help="Кількість сторінок для парсингу")
    parser.add_argument("--csv", type=Path, default=Path("freelancer_jobs.csv"), help="Шлях до CSV")
    parser.add_argument("--json", type=Path, default=Path("freelancer_jobs.json"), help="Шлях до JSON")
    parser.add_argument("--min-delay", type=float, default=1.4, help="Мінімальна пауза між сторінками")
    parser.add_argument("--max-delay", type=float, default=3.0, help="Максимальна пауза між сторінками")
    parser.add_argument(
        "--keywords",
        nargs="*",
        default=[],
        help="Ключові слова для відбору (через пробіл або кому)",
    )
    parser.add_argument(
        "--keywords-mode",
        choices=["any", "all"],
        default="any",
        help="Режим фільтра: any (будь-яке слово) або all (усі слова)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.min_delay < 0 or args.max_delay < 0 or args.max_delay < args.min_delay:
        raise ValueError("Некоректні затримки: перевір min-delay/max-delay")

    jobs = scrape_jobs(pages=args.pages, min_delay=args.min_delay, max_delay=args.max_delay)
    keywords = parse_keywords(args.keywords)
    filtered_jobs = filter_jobs_by_keywords(jobs, keywords=keywords, mode=args.keywords_mode)
    search_query_label = build_search_query_label(keywords=keywords, mode=args.keywords_mode)
    search_timestamp = datetime.now(timezone.utc).isoformat()
    source_pages = f"1-{args.pages}"

    for item in filtered_jobs:
        item.search_keywords = keywords
        item.search_mode = args.keywords_mode
        item.search_query = search_query_label
        item.search_timestamp = search_timestamp
        item.source_pages = source_pages

    save_csv(filtered_jobs, args.csv)
    save_json(filtered_jobs, args.json)

    print(f"[DONE] Унікальних вакансій зібрано: {len(jobs)}")
    if keywords:
        print(
            f"[DONE] Після фільтрації ({args.keywords_mode}: {', '.join(keywords)}): {len(filtered_jobs)}"
        )
    else:
        print(f"[DONE] Після фільтрації: {len(filtered_jobs)}")
    print(f"[DONE] CSV: {args.csv.resolve()}")
    print(f"[DONE] JSON: {args.json.resolve()}")


if __name__ == "__main__":
    main()
