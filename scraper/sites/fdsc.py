"""Scraper for FDSC - Fundatia pentru Dezvoltarea Societatii Civile"""

import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

BASE_URLS = [
    "https://www.fdsc.ro",
    "https://www.activecitizensfund.ro",
]


def scrape() -> List[Dict]:
    """
    Scrape funding opportunities from FDSC and Active Citizens Fund Romania
    """
    jobs = []
    seen_urls = set()

    for base_url in BASE_URLS:
        try:
            logger.info(f"Fetching {base_url}")
            response = requests.get(base_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')
            links = soup.find_all('a', href=True)

            for link in links:
                href = link.get('href', '')

                if href.startswith('/'):
                    href = base_url + href
                elif not href.startswith('http'):
                    continue

                # Only process internal links
                domain = base_url.replace('https://', '').replace('http://', '').replace('www.', '')
                if domain not in href:
                    continue

                # Skip utility links
                if any(skip in href for skip in [
                    '#', '/wp-content/', '/feed/', 'javascript:',
                    '.pdf', '.doc', '.png', '.jpg', '.css', '.js',
                ]):
                    continue

                if href in seen_urls:
                    continue

                title = link.get_text(strip=True)

                # Try to get a better title from parent or sibling elements
                if not title or len(title) < 15 or title.lower() in ['află mai multe', 'afla mai multe', 'citeste', 'read more', 'mai mult']:
                    # Try parent heading
                    parent = link.parent
                    for _ in range(3):
                        if parent is None:
                            break
                        heading = parent.find(['h1', 'h2', 'h3', 'h4'])
                        if heading:
                            title = heading.get_text(strip=True)
                            break
                        parent = parent.parent

                if not title or len(title) < 10:
                    continue

                # Focus on funding-related content
                combined = (href + ' ' + title).lower()
                if any(kw in combined for kw in [
                    'grant', 'finantare', 'finantar', 'apel', 'fond',
                    'program', 'proiect', 'concurs', 'sesiune',
                    'call', 'funding', 'ngo', 'ong', 'civic',
                    'democratie', 'drept', 'egal', 'incluziune',
                ]):
                    seen_urls.add(href)
                    source = 'active_citizens' if 'activecitizensfund' in base_url else 'fdsc'
                    fund_id = hashlib.md5(href.encode()).hexdigest()[:12]

                    jobs.append({
                        'id': f"{source}_{fund_id}",
                        'title': title,
                        'url': href,
                        'deadline': None,
                        'deadline_date': None,
                        'source': source,
                        'description': ''
                    })

        except requests.RequestException as e:
            logger.error(f"Error fetching {base_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {base_url}: {e}")

    # Fetch details
    logger.info(f"Found {len(jobs)} FDSC/ACF items, fetching details...")
    for job in jobs[:20]:
        details = fetch_details(job['url'])
        if details['deadline']:
            job['deadline'] = details['deadline']
            job['deadline_date'] = details['deadline_date']
        if details['description']:
            job['description'] = details['description']

    return jobs


def fetch_details(url: str) -> Dict:
    """Fetch page details"""
    result = {'deadline': None, 'deadline_date': None, 'description': ''}
    try:
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
            r'deadline[:\s]+(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
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
