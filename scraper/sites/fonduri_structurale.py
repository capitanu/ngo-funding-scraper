"""Scraper for fonduri-structurale.ro - EU structural funds for Romania"""

import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

BASE_URL = "https://www.fonduri-structurale.ro"


def scrape() -> List[Dict]:
    """
    Scrape EU structural fund opportunities from fonduri-structurale.ro

    The site is Next.js-based, so we try to scrape the server-rendered HTML
    and also check for any API endpoints.
    """
    jobs = []
    seen_urls = set()

    urls_to_try = [
        f"{BASE_URL}/apeluri-deschise",
        f"{BASE_URL}/apeluri",
        BASE_URL,
    ]

    for page_url in urls_to_try:
        try:
            logger.info(f"Fetching {page_url}")
            response = requests.get(page_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.8',
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')

            # Try to find funding call cards/articles
            # Look for common patterns
            cards = soup.select('article, .card, [class*="card"], [class*="apel"], [class*="call"], a[href*="/apel"]')

            if not cards:
                # Try finding any internal links that look like funding calls
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    if not href.startswith('/') and not href.startswith(BASE_URL):
                        continue
                    if href.startswith('/'):
                        href = BASE_URL + href

                    # Filter for funding-related pages
                    if not any(kw in href.lower() for kw in ['apel', 'finantare', 'grant', 'program']):
                        continue

                    if href in seen_urls:
                        continue

                    title = link.get_text(strip=True)
                    if not title or len(title) < 10:
                        continue

                    seen_urls.add(href)
                    fund_id = hashlib.md5(href.encode()).hexdigest()[:12]

                    jobs.append({
                        'id': f"fonduri_structurale_{fund_id}",
                        'title': title,
                        'url': href,
                        'deadline': None,
                        'deadline_date': None,
                        'source': 'fonduri_structurale',
                        'description': ''
                    })
            else:
                for card in cards:
                    job_data = parse_card(card)
                    if job_data and job_data['url'] not in seen_urls:
                        seen_urls.add(job_data['url'])
                        jobs.append(job_data)

            # Also try to extract data from Next.js __NEXT_DATA__ script
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
                import json
                try:
                    data = json.loads(next_data.string)
                    props = data.get('props', {}).get('pageProps', {})
                    # Look for any list of items in the page props
                    for key, value in props.items():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict) and ('title' in item or 'name' in item or 'titlu' in item):
                                    title = item.get('title') or item.get('name') or item.get('titlu', '')
                                    url = item.get('url') or item.get('link') or item.get('slug', '')
                                    if url and not url.startswith('http'):
                                        url = f"{BASE_URL}/{url.lstrip('/')}"

                                    if not title or url in seen_urls:
                                        continue

                                    seen_urls.add(url)
                                    fund_id = hashlib.md5(url.encode()).hexdigest()[:12]

                                    deadline = item.get('deadline') or item.get('termen') or item.get('data_limita')

                                    jobs.append({
                                        'id': f"fonduri_structurale_{fund_id}",
                                        'title': title,
                                        'url': url,
                                        'deadline': deadline,
                                        'deadline_date': parse_date(deadline) if deadline else None,
                                        'source': 'fonduri_structurale',
                                        'description': item.get('description', item.get('descriere', ''))[:3000]
                                    })
                except (json.JSONDecodeError, KeyError):
                    pass

        except requests.RequestException as e:
            logger.error(f"Error fetching {page_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {page_url}: {e}")

    logger.info(f"Found {len(jobs)} EU structural fund opportunities")
    return jobs


def parse_card(card) -> Optional[Dict]:
    """Parse a funding card element"""
    link = card.find('a', href=True)
    if not link and card.name == 'a':
        link = card

    if not link:
        return None

    href = link.get('href', '')
    if href.startswith('/'):
        url = BASE_URL + href
    elif not href.startswith('http'):
        url = f"{BASE_URL}/{href}"
    else:
        url = href

    title_elem = card.find(['h2', 'h3', 'h4'])
    title = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)

    if not title or len(title) < 5:
        return None

    fund_id = hashlib.md5(url.encode()).hexdigest()[:12]

    # Try to find deadline
    text = card.get_text()
    deadline, deadline_date = parse_deadline_text(text)

    desc_elem = card.find('p')
    description = desc_elem.get_text(strip=True)[:200] if desc_elem else ''

    return {
        'id': f"fonduri_structurale_{fund_id}",
        'title': title,
        'url': url,
        'deadline': deadline,
        'deadline_date': deadline_date,
        'source': 'fonduri_structurale',
        'description': description
    }


def parse_deadline_text(text: str) -> tuple:
    """Parse deadline from Romanian text"""
    patterns = [
        r'(?:termen|data)\s*(?:limita|limită)[:\s]*(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
        r'(?:până|pana)\s*(?:la|pe)\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
        r'deadline[:\s]+(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            return date_str, parse_date(date_str)

    return None, None


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string"""
    if not date_str:
        return None
    for fmt in ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
