"""Scraper for finantare.ro - Romanian funding opportunities aggregator"""

import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

BASE_URL = "https://www.finantare.ro"
PAGES = [
    f"{BASE_URL}/fonduri-nerambursabile.html",
    f"{BASE_URL}/",
]


def scrape() -> List[Dict]:
    """
    Scrape funding opportunities from finantare.ro

    Returns list of funding dicts with keys:
    - id: unique identifier
    - title: funding title
    - url: direct link to funding page
    - deadline: deadline date string
    - deadline_date: parsed datetime or None
    - source: 'finantare_ro'
    - description: brief description
    """
    jobs = []
    seen_urls = set()

    for page_url in PAGES:
        try:
            logger.info(f"Fetching {page_url}")
            response = requests.get(page_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; QUB-Funding-Scraper/1.0)'
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')

            # Find all article links on finantare.ro
            # The site uses panel-grid-cell containers with article links
            links = soup.find_all('a', href=True)

            for link in links:
                href = link.get('href', '')

                # Only process article links on finantare.ro
                if not href.startswith(BASE_URL + '/') and not href.startswith('/'):
                    continue
                if href.startswith('/'):
                    href = BASE_URL + href

                # Skip navigation, category, and non-article links
                if any(skip in href for skip in [
                    '/category/', '/tag/', '/page/', '/author/',
                    '#', '/wp-content/', '/feed/', '/contact',
                    'facebook.com', 'twitter.com', '/despre-noi',
                    '/wp-login', '/wp-admin',
                ]):
                    continue

                # Must be an .html article or a clean URL article
                if not (href.endswith('.html') or re.match(r'https://www\.finantare\.ro/[a-z0-9-]+/$', href)):
                    continue

                if href in seen_urls:
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 10:
                    continue

                # Skip if title looks like navigation
                if title.lower() in ['acasa', 'home', 'contact', 'despre noi', 'mai multe']:
                    continue

                # Clean up title - remove Previous/Next post prefixes
                title = re.sub(r'^(Previous|Next)(Previous|Next)?\s*post:', '', title).strip()
                if not title or len(title) < 10:
                    continue

                seen_urls.add(href)
                fund_id = hashlib.md5(href.encode()).hexdigest()[:12]

                jobs.append({
                    'id': f"finantare_ro_{fund_id}",
                    'title': title,
                    'url': href,
                    'deadline': None,
                    'deadline_date': None,
                    'source': 'finantare_ro',
                    'description': ''
                })

        except requests.RequestException as e:
            logger.error(f"Error fetching {page_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {page_url}: {e}")

    # Fetch details for each article (deadline + description)
    logger.info(f"Found {len(jobs)} articles, fetching details...")
    for job in jobs[:30]:  # Limit to 30 to avoid rate-limiting
        details = fetch_article_details(job['url'])
        if details['deadline']:
            job['deadline'] = details['deadline']
            job['deadline_date'] = details['deadline_date']
        if details['description']:
            job['description'] = details['description']

    return jobs


def fetch_article_details(url: str) -> Dict:
    """Fetch article page to extract deadline and description"""
    result = {'deadline': None, 'deadline_date': None, 'description': ''}
    try:
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; QUB-Funding-Scraper/1.0)'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        # Get article body text for keyword matching
        article = soup.find('div', class_='articlebody') or soup.find('article') or soup.find('div', class_='entry-content')
        if article:
            text = article.get_text(' ', strip=True)
        else:
            text = soup.get_text(' ', strip=True)

        result['description'] = ' '.join(text.split())[:3000]

        # Search for deadline patterns in Romanian
        deadline_patterns = [
            r'(?:termen|data)\s*(?:limita|limită)\s*[:\s]*(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(?:până|pana)\s*(?:la|pe|in|în)\s*(?:data\s+de\s+)?(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(?:până|pana)\s*(?:la|pe|in|în)\s*(?:data\s+de\s+)?(\d{1,2}\s+\w+\s+\d{4})',
            r'(?:inscrieri|înscrieri)\s*(?:până|pana)\s*(?:la|pe)\s*(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(?:inscrieri|înscrieri)\s*(?:până|pana)\s*(?:la|pe)\s*(\d{1,2}\s+\w+\s+\d{4})',
            r'deadline[:\s]+(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
        ]

        for pattern in deadline_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                result['deadline'] = date_str
                result['deadline_date'] = parse_date(date_str)
                break

        return result
    except Exception as e:
        logger.debug(f"Could not fetch details from {url}: {e}")
        return result


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various Romanian date formats"""
    # Map Romanian month names
    ro_months = {
        'ianuarie': '01', 'februarie': '02', 'martie': '03', 'aprilie': '04',
        'mai': '05', 'iunie': '06', 'iulie': '07', 'august': '08',
        'septembrie': '09', 'octombrie': '10', 'noiembrie': '11', 'decembrie': '12',
    }

    # Try named month format: "15 aprilie 2026"
    match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_str)
    if match:
        day, month_name, year = match.groups()
        month_num = ro_months.get(month_name.lower())
        if month_num:
            try:
                return datetime(int(year), int(month_num), int(day))
            except ValueError:
                pass

    # Try numeric formats
    for fmt in ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None
