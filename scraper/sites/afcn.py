"""Scraper for AFCN - Administratia Fondului Cultural National"""

import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

BASE_URLS = [
    "https://www.afcn.ro/programe/proiecte-culturale",
    "https://www.afcn.ro/programe/proiecte-editoriale",
    "https://www.afcn.ro",
]


def scrape() -> List[Dict]:
    """
    Scrape cultural funding programs from AFCN
    """
    jobs = []
    seen_urls = set()

    for page_url in BASE_URLS:
        try:
            logger.info(f"Fetching {page_url}")
            response = requests.get(page_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; QUB-Funding-Scraper/1.0)'
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')

            # Find all internal links that look like funding programs
            links = soup.find_all('a', href=True)

            for link in links:
                href = link.get('href', '')

                # Normalize URL
                if href.startswith('/'):
                    href = f"https://www.afcn.ro{href}"
                elif not href.startswith('http'):
                    continue

                # Only process afcn.ro links
                if 'afcn.ro' not in href:
                    continue

                # Skip navigation/utility links
                if any(skip in href for skip in [
                    '#', '/wp-content/', '/feed/', 'javascript:',
                    'facebook.com', 'twitter.com', '/login',
                ]):
                    continue

                if href in seen_urls:
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 10:
                    continue

                # Focus on funding-related pages
                if any(kw in href.lower() or kw in title.lower() for kw in [
                    'program', 'proiect', 'sesiune', 'finantare', 'fonduri',
                    'apel', 'concurs', 'grant', 'cultural', 'editorial',
                ]):
                    seen_urls.add(href)
                    fund_id = hashlib.md5(href.encode()).hexdigest()[:12]

                    jobs.append({
                        'id': f"afcn_{fund_id}",
                        'title': title,
                        'url': href,
                        'deadline': None,
                        'deadline_date': None,
                        'source': 'afcn',
                        'description': ''
                    })

        except requests.RequestException as e:
            logger.error(f"Error fetching {page_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {page_url}: {e}")

    # Fetch details for funding pages
    logger.info(f"Found {len(jobs)} AFCN items, fetching details...")
    for job in jobs[:20]:
        details = fetch_details(job['url'])
        if details['deadline']:
            job['deadline'] = details['deadline']
            job['deadline_date'] = details['deadline_date']
        if details['description']:
            job['description'] = details['description']

    return jobs


def fetch_details(url: str) -> Dict:
    """Fetch page details for deadline and description"""
    result = {'deadline': None, 'deadline_date': None, 'description': ''}
    try:
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; QUB-Funding-Scraper/1.0)'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        text = soup.get_text(' ', strip=True)

        result['description'] = ' '.join(text.split())[:3000]

        # Romanian deadline patterns
        deadline_patterns = [
            r'(?:termen|data)\s*(?:limita|limită)\s*[:\s]*(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(?:până|pana)\s*(?:la|pe|in|în)\s*(?:data\s+de\s+)?(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(?:până|pana)\s*(?:la|pe|in|în)\s*(?:data\s+de\s+)?(\d{1,2}\s+\w+\s+\d{4})',
            r'sesiune.*?(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
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
    """Parse date string"""
    ro_months = {
        'ianuarie': '01', 'februarie': '02', 'martie': '03', 'aprilie': '04',
        'mai': '05', 'iunie': '06', 'iulie': '07', 'august': '08',
        'septembrie': '09', 'octombrie': '10', 'noiembrie': '11', 'decembrie': '12',
    }

    match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_str)
    if match:
        day, month_name, year = match.groups()
        month_num = ro_months.get(month_name.lower())
        if month_num:
            try:
                return datetime(int(year), int(month_num), int(day))
            except ValueError:
                pass

    for fmt in ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
