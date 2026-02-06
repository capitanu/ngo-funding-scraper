"""Scraper for NGO Hub / Code for Romania ecosystem - funding opportunities"""

import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

BASE_URLS = [
    "https://ngohub.ro",
    "https://www.eurodesk.ro",
]


def scrape() -> List[Dict]:
    """
    Scrape funding opportunities from NGO Hub and Eurodesk Romania
    """
    jobs = []
    seen_urls = set()

    for base_url in BASE_URLS:
        try:
            logger.info(f"Fetching {base_url}")
            response = requests.get(base_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.8',
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')
            links = soup.find_all('a', href=True)

            for link in links:
                href = link.get('href', '')

                if href.startswith('/'):
                    href = base_url.rstrip('/') + href
                elif not href.startswith('http'):
                    continue

                # Skip external/utility links
                if any(skip in href for skip in [
                    '#', 'javascript:', '.pdf', '.doc',
                    'facebook.com', 'twitter.com', 'linkedin.com',
                ]):
                    continue

                if href in seen_urls:
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 10:
                    continue

                # Focus on funding/grant pages
                combined = (href + ' ' + title).lower()
                if any(kw in combined for kw in [
                    'grant', 'finantare', 'finantar', 'fond', 'funding',
                    'apel', 'program', 'concurs', 'burs', 'sponsoriz',
                ]):
                    seen_urls.add(href)
                    fund_id = hashlib.md5(href.encode()).hexdigest()[:12]

                    jobs.append({
                        'id': f"ngohub_{fund_id}",
                        'title': title,
                        'url': href,
                        'deadline': None,
                        'deadline_date': None,
                        'source': 'ngohub',
                        'description': ''
                    })

        except requests.RequestException as e:
            logger.error(f"Error fetching {base_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {base_url}: {e}")

    # Fetch details
    logger.info(f"Found {len(jobs)} NGO Hub items, fetching details...")
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

        deadline_patterns = [
            r'(?:termen|data)\s*(?:limita|limită)\s*[:\s]*(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'(?:până|pana)\s*(?:la|pe|in|în)\s*(?:data\s+de\s+)?(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'deadline[:\s]+(\d{1,2}[\./-]\d{1,2}[\./-]\d{4})',
            r'deadline[:\s]+(\d{4}-\d{2}-\d{2})',
        ]

        for pattern in deadline_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                result['deadline'] = date_str
                for fmt in ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                    try:
                        result['deadline_date'] = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                break

        return result
    except Exception as e:
        logger.debug(f"Could not fetch details from {url}: {e}")
        return result
