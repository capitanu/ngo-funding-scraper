"""Notification system using ntfy.sh"""

import logging
import requests
import unicodedata
from typing import Dict, List

logger = logging.getLogger(__name__)

NTFY_TOPIC = "qub-ngo-funding"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def sanitize_header(text: str) -> str:
    """Sanitize text for HTTP headers (ASCII-safe)"""
    text = unicodedata.normalize('NFKD', text)
    replacements = {
        '\u2013': '-',
        '\u2014': '-',
        '\u2018': "'",
        '\u2019': "'",
        '\u201c': '"',
        '\u201d': '"',
        '\u0103': 'a',  # ă
        '\u00e2': 'a',  # â
        '\u00ee': 'i',  # î
        '\u0219': 's',  # ș
        '\u021b': 't',  # ț
        '\u0102': 'A',  # Ă
        '\u00c2': 'A',  # Â
        '\u00ce': 'I',  # Î
        '\u0218': 'S',  # Ș
        '\u021a': 'T',  # Ț
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode('ascii', 'ignore').decode('ascii')


def send_notification(funding: Dict, matched_keywords: List[str]) -> bool:
    """
    Send a push notification for a new funding opportunity via ntfy.sh
    """
    try:
        title_text = sanitize_header(funding['title'][:60])
        title = f"Finantare: {title_text}"
        if len(funding['title']) > 60:
            title += "..."

        lines = []

        if funding.get('deadline'):
            lines.append(f"Termen limita: {funding['deadline']}")

        source_names = {
            'finantare_ro': 'Finantare.ro',
            'fonduri_structurale': 'Fonduri Structurale EU',
            'afcn': 'AFCN - Fond Cultural National',
            'fdsc': 'FDSC',
            'active_citizens': 'Active Citizens Fund',
        }
        source = source_names.get(funding.get('source'), funding.get('source', 'Necunoscut'))
        lines.append(f"Sursa: {source}")

        if matched_keywords:
            high_priority = [
                'educatie', 'educatia', 'educational', 'steam', 'stiinta',
                'tineret', 'tineri', 'copii', 'elevi', 'scoala', 'scoli',
                'ngo', 'ong', 'societate civila', 'cultura', 'cultural',
            ]
            high = [k for k in matched_keywords if k.lower() in high_priority]
            medium = [k for k in matched_keywords if k.lower() not in high_priority]

            if high:
                lines.append(f"Prioritate ridicata: {', '.join(high)}")
            if medium:
                lines.append(f"Relevante: {', '.join(medium)}")

        message = "\n".join(lines)

        response = requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Click": funding.get('url', ''),
                "Tags": "money_with_wings,romania",
                "Priority": "high" if any(k.lower() in ['educatie', 'educatia', 'steam', 'tineret', 'copii', 'ong'] for k in matched_keywords) else "default"
            },
            timeout=10
        )
        response.raise_for_status()

        logger.info(f"Notification sent for funding: {funding['id']}")
        return True

    except requests.RequestException as e:
        logger.error(f"Failed to send notification: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return False


def send_test_notification() -> bool:
    """Send a test notification to verify ntfy.sh is working"""
    try:
        response = requests.post(
            NTFY_URL,
            data="Aceasta este o notificare de test de la QUB NGO Funding Scraper.\n\nDaca vezi asta, notificarile functioneaza!",
            headers={
                "Title": "QUB Funding Scraper - Test",
                "Tags": "white_check_mark,test_tube",
                "Priority": "low"
            },
            timeout=10
        )
        response.raise_for_status()
        logger.info("Test notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}")
        return False


def send_summary_notification(new_count: int, total_matching: int) -> bool:
    """Send a daily summary notification"""
    try:
        if new_count == 0:
            message = f"Nicio oportunitate noua de finantare astazi.\n\nTotal oportunitati deschise: {total_matching}"
            title = "QUB Funding - Verificare zilnica"
            priority = "low"
        else:
            message = f"Am gasit {new_count} oportunitati noi de finantare!\n\nTotal oportunitati deschise: {total_matching}"
            title = f"QUB Funding - {new_count} oportunitati noi!"
            priority = "default"

        response = requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Tags": "clipboard",
                "Priority": priority
            },
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send summary notification: {e}")
        return False
