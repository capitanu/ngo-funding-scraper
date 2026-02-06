#!/usr/bin/env python3
"""
NGO Funding Scraper - Main entry point

Scrapes funding opportunities for Romanian NGOs,
matches against keywords relevant to QUB Education,
sends notifications, and generates dashboard.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple
import re

from scraper.sites import finantare_ro, fonduri_structurale, afcn, fdsc, ngohub
from scraper import notifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "seen_funding.json"
DASHBOARD_FILE = PROJECT_ROOT / "docs" / "index.html"

# Keywords configuration - relevant to QUB Education (STEAM, education, youth, culture, NGOs)
HIGH_PRIORITY_KEYWORDS = [
    'educatie', 'educatia', 'educational', 'educationale', 'educativ',
    'steam', 'stiinta', 'stiinte', 'science',
    'tineret', 'tineri', 'youth',
    'copii', 'elevi', 'studenti',
    'scoala', 'scoli', 'scolar',
    'ong', 'ngo', 'societate civila', 'civil society',
    'non-formal', 'nonformal',
    'nerambursabil', 'nerambursabila', 'grant', 'granturi',
]

MEDIUM_PRIORITY_KEYWORDS = [
    'cultura', 'cultural', 'culturale',
    'inovare', 'inovatie', 'innovation',
    'digital', 'digitalizare', 'tehnologie', 'technology',
    'capacitare', 'formare profesionala',
    'comunitate', 'comunitar', 'community',
    'incluziune', 'incluziv',
    'voluntariat', 'civic', 'civica',
    'sponsorizare', 'mecenatul',
    'sustenabil', 'dezvoltare durabila',
]

ALL_KEYWORDS = HIGH_PRIORITY_KEYWORDS + MEDIUM_PRIORITY_KEYWORDS


def load_seen_funding() -> Dict:
    """Load the seen funding database"""
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading seen funding: {e}")

    return {"funding": {}, "last_updated": None}


def save_seen_funding(data: Dict) -> None:
    """Save the seen funding database"""
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved {len(data['funding'])} funding items to database")
    except Exception as e:
        logger.error(f"Error saving seen funding: {e}")


def match_keywords(funding: Dict) -> List[str]:
    """
    Check if a funding opportunity matches any of our keywords.
    Returns list of matched keywords.
    """
    text = f"{funding.get('title', '')} {funding.get('description', '')}".lower()

    matched = []
    for keyword in ALL_KEYWORDS:
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, text):
            matched.append(keyword)

    return matched


def is_closing_soon(funding: Dict) -> bool:
    """Check if funding deadline is within 14 days"""
    deadline = funding.get('deadline_date')
    if deadline:
        if isinstance(deadline, str):
            try:
                deadline = datetime.fromisoformat(deadline)
            except ValueError:
                return False
        days_left = (deadline - datetime.now()).days
        return 0 <= days_left <= 14
    return False


def scrape_all_sources() -> List[Dict]:
    """Scrape all funding sources and return combined list"""
    all_funding = []

    scrapers = [
        ('Finantare.ro', finantare_ro.scrape),
        ('Fonduri Structurale EU', fonduri_structurale.scrape),
        ('AFCN', afcn.scrape),
        ('FDSC / Active Citizens', fdsc.scrape),
        ('NGO Hub / Eurodesk', ngohub.scrape),
    ]

    for name, scraper in scrapers:
        try:
            logger.info(f"Scraping {name}...")
            items = scraper()
            all_funding.extend(items)
            logger.info(f"  Found {len(items)} items")
        except Exception as e:
            logger.error(f"Error scraping {name}: {e}")

    return all_funding


def process_funding(all_funding: List[Dict], seen_data: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    Process scraped funding, identify new and matching ones.

    Returns:
        (new_matching_funding, all_matching_funding)
    """
    new_matching = []
    all_matching = []

    for item in all_funding:
        fund_id = item['id']

        matched_keywords = match_keywords(item)

        if not matched_keywords:
            continue

        item['matched_keywords'] = matched_keywords
        item['is_high_priority'] = any(k in HIGH_PRIORITY_KEYWORDS for k in matched_keywords)
        item['closing_soon'] = is_closing_soon(item)

        all_matching.append(item)

        if fund_id not in seen_data['funding']:
            new_matching.append(item)
            seen_data['funding'][fund_id] = {
                'first_seen': datetime.now().isoformat(),
                'title': item['title'],
                'url': item['url'],
                'source': item['source'],
                'deadline': item.get('deadline'),
                'matched_keywords': matched_keywords
            }

    return new_matching, all_matching


def generate_dashboard(matching_funding: List[Dict], last_updated: str) -> None:
    """Generate the static HTML dashboard"""
    sorted_funding = sorted(
        matching_funding,
        key=lambda j: (
            not j.get('closing_soon', False),
            not j.get('is_high_priority', False),
            j.get('title', '').lower()
        )
    )

    source_names = {
        'finantare_ro': 'Finantare.ro',
        'fonduri_structurale': 'Fonduri Structurale EU',
        'afcn': 'AFCN - Fondul Cultural National',
        'fdsc': 'FDSC',
        'active_citizens': 'Active Citizens Fund',
        'ngohub': 'NGO Hub / Eurodesk',
    }

    funding_json = json.dumps([{
        'id': item['id'],
        'title': item['title'],
        'url': item['url'],
        'deadline': item.get('deadline'),
        'deadline_date': item.get('deadline_date').isoformat() if item.get('deadline_date') and hasattr(item.get('deadline_date'), 'isoformat') else item.get('deadline_date'),
        'source': item['source'],
        'matched_keywords': item.get('matched_keywords', []),
        'is_high_priority': item.get('is_high_priority', False),
        'closing_soon': item.get('closing_soon', False)
    } for item in matching_funding])

    html = f'''<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QUB Education - Funding Tracker</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>💰</text></svg>">
    <style>
        :root {{
            --primary: #6546c8;
            --primary-dark: #4a2fa0;
            --accent: #F8D32A;
            --accent-dark: #d4b41e;
            --success: #276749;
            --warning: #c05621;
            --light: #faf9fc;
            --border: #e8e4f0;
            --text: #2d2d3d;
            --text-light: #6b6b80;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--light);
            color: var(--text);
            line-height: 1.6;
            padding: 1rem;
        }}
        .top-container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .main-layout {{
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .left-column {{
            min-width: 0;
        }}
        .right-column {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}
        .brand-header {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 1.5rem 2rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }}
        .brand-logo {{
            font-size: 2rem;
            font-weight: 800;
            color: var(--accent);
            text-decoration: none;
            letter-spacing: -0.5px;
            white-space: nowrap;
        }}
        .brand-logo:hover {{
            color: white;
        }}
        .brand-info {{
            flex: 1;
        }}
        .brand-info p {{
            opacity: 0.85;
            font-size: 0.85rem;
        }}
        header {{
            background: white;
            color: var(--text);
            padding: 1.5rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
            border: 1px solid var(--border);
            border-left: 4px solid var(--primary);
        }}
        header h1 {{
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
            color: var(--primary);
        }}
        .subtitle {{
            color: var(--text-light);
            font-size: 0.9rem;
        }}
        .stats {{
            display: flex;
            gap: 1rem;
            margin-top: 1rem;
            flex-wrap: wrap;
        }}
        .stat {{
            background: var(--light);
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            border: 1px solid var(--border);
        }}
        .stat strong {{
            font-size: 1.2rem;
            color: var(--primary);
        }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            border: 1px solid var(--border);
        }}
        .section h2 {{
            color: var(--primary);
            font-size: 1.1rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--border);
        }}
        .section.applied {{
            border-left: 4px solid var(--success);
        }}
        .section.applied h2 {{
            color: var(--success);
        }}
        .section.irrelevant {{
            border-left: 4px solid #a0aec0;
        }}
        .section.irrelevant h2 {{
            color: #718096;
        }}
        .job-list {{
            list-style: none;
        }}
        .job {{
            padding: 1rem;
            border-bottom: 1px solid var(--border);
        }}
        .job:last-child {{
            border-bottom: none;
        }}
        .job-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.5rem;
        }}
        .job-title {{
            font-weight: 600;
            color: var(--primary);
            text-decoration: none;
            flex: 1;
        }}
        .job-title:hover {{
            text-decoration: underline;
            color: var(--primary-dark);
        }}
        .job-actions {{
            display: flex;
            gap: 0.25rem;
            flex-shrink: 0;
        }}
        .btn {{
            padding: 0.25rem 0.5rem;
            border: none;
            border-radius: 4px;
            font-size: 0.7rem;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .btn:hover {{
            opacity: 0.8;
        }}
        .btn-applied {{
            background: #c6f6d5;
            color: var(--success);
        }}
        .btn-irrelevant {{
            background: #e2e8f0;
            color: #718096;
        }}
        .btn-undo {{
            background: #fed7d7;
            color: #c53030;
        }}
        .job-meta {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            font-size: 0.85rem;
            color: var(--text-light);
            margin-top: 0.5rem;
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .badge-high {{
            background: #fed7d7;
            color: #c53030;
        }}
        .badge-closing {{
            background: #feebc8;
            color: var(--warning);
        }}
        .badge-keyword {{
            background: #e9e4f5;
            color: var(--primary);
        }}
        .keywords {{
            margin-top: 0.5rem;
            display: flex;
            gap: 0.25rem;
            flex-wrap: wrap;
        }}
        .empty {{
            color: #a0aec0;
            text-align: center;
            padding: 1rem;
            font-size: 0.9rem;
        }}
        footer {{
            text-align: center;
            color: var(--text-light);
            font-size: 0.8rem;
            margin-top: 2rem;
        }}
        footer a {{
            color: var(--primary);
        }}
        .right-job {{
            padding: 0.75rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.85rem;
        }}
        .right-job:last-child {{
            border-bottom: none;
        }}
        .right-job-title {{
            font-weight: 500;
            color: var(--primary);
            text-decoration: none;
            display: block;
            margin-bottom: 0.25rem;
        }}
        .right-job-title:hover {{
            text-decoration: underline;
        }}
        .right-job-meta {{
            font-size: 0.75rem;
            color: var(--text-light);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        @media (max-width: 900px) {{
            .main-layout {{
                grid-template-columns: 1fr;
            }}
            .right-column {{
                order: -1;
            }}
        }}
        @media (max-width: 600px) {{
            body {{
                padding: 0.5rem;
            }}
            .brand-header {{
                flex-direction: column;
                text-align: center;
                padding: 1rem;
            }}
            header {{
                padding: 1rem;
            }}
            .job-meta {{
                flex-direction: column;
                gap: 0.5rem;
            }}
            .job-header {{
                flex-direction: column;
            }}
            .job-actions {{
                align-self: flex-start;
            }}
        }}
    </style>
</head>
<body>
    <div class="top-container">
        <div class="brand-header">
            <a href="https://qub.education/" target="_blank" class="brand-logo">QUB</a>
            <div class="brand-info">
                <p>Educatia este conectare &mdash; STEAM Education &amp; Community in Cluj-Napoca</p>
            </div>
        </div>
        <header>
            <h1>Funding &amp; Grant Tracker</h1>
            <p class="subtitle">Oportunitati de finantare pentru ONG-uri din Romania</p>
            <p class="subtitle">Focus: Educatie, STEAM, Tineret, Cultura, Societate Civila</p>
            <div class="stats">
                <div class="stat"><strong id="stat-total">{len(matching_funding)}</strong> oportunitati</div>
                <div class="stat"><strong id="stat-closing">{sum(1 for j in matching_funding if j.get('closing_soon'))}</strong> termen apropiat</div>
                <div class="stat"><strong id="stat-high">{sum(1 for j in matching_funding if j.get('is_high_priority'))}</strong> prioritate ridicata</div>
            </div>
        </header>
    </div>

    <div class="main-layout">
        <div class="left-column" id="main-jobs">
            <div class="section"><p class="empty">Se incarca...</p></div>
        </div>
        <div class="right-column">
            <div class="section applied">
                <h2>Aplicate (<span id="applied-count">0</span>)</h2>
                <ul class="job-list" id="applied-list">
                    <li class="empty" id="applied-empty">Nicio aplicare inca</li>
                </ul>
            </div>
            <div class="section irrelevant">
                <h2>Irelevante (<span id="irrelevant-count">0</span>)</h2>
                <ul class="job-list" id="irrelevant-list">
                    <li class="empty" id="irrelevant-empty">Nimic marcat</li>
                </ul>
            </div>
        </div>
    </div>

    <footer>
        <p>Ultima actualizare: {last_updated}</p>
        <p>Notificari: <a href="https://ntfy.sh/qub-ngo-funding">ntfy.sh/qub-ngo-funding</a></p>
        <p style="margin-top: 0.5rem;"><a href="https://qub.education/" target="_blank">qub.education</a></p>
        <p id="sync-status" style="font-size: 0.7rem; margin-top: 0.5rem; color: #718096;"></p>
    </footer>

    <script>
        const allJobs = {funding_json};
        const sourceNames = {{
            'finantare_ro': 'Finantare.ro',
            'fonduri_structurale': 'Fonduri Structurale EU',
            'afcn': 'AFCN - Fondul Cultural National',
            'fdsc': 'FDSC',
            'active_citizens': 'Active Citizens Fund',
            'ngohub': 'NGO Hub / Eurodesk'
        }};

        let applied = [];
        let irrelevant = [];

        function loadState() {{
            applied = JSON.parse(localStorage.getItem('qub-funding-applied') || '[]');
            irrelevant = JSON.parse(localStorage.getItem('qub-funding-irrelevant') || '[]');
            render();
        }}

        function saveState() {{
            localStorage.setItem('qub-funding-applied', JSON.stringify(applied));
            localStorage.setItem('qub-funding-irrelevant', JSON.stringify(irrelevant));
        }}

        function formatDate(dateStr) {{
            if (!dateStr) return 'Nespecificat';
            try {{
                const date = new Date(dateStr);
                if (isNaN(date.getTime())) return dateStr;
                return date.toLocaleDateString('ro-RO', {{ day: '2-digit', month: 'short', year: 'numeric' }});
            }} catch {{
                return dateStr;
            }}
        }}

        function createJobCard(job) {{
            const badges = [];
            if (job.is_high_priority) badges.push('<span class="badge badge-high">Prioritate Ridicata</span>');
            if (job.closing_soon) badges.push('<span class="badge badge-closing">Termen Apropiat</span>');

            const keywords = job.matched_keywords.slice(0, 5).map(k => `<span class="badge badge-keyword">${{k}}</span>`).join('');
            const deadline = formatDate(job.deadline_date || job.deadline);

            const actions = `
                <button class="btn btn-applied" onclick="markApplied('${{job.id}}')">Aplicat</button>
                <button class="btn btn-irrelevant" onclick="markIrrelevant('${{job.id}}')">Irelevant</button>
            `;

            return `
                <li class="job" data-job-id="${{job.id}}">
                    <div class="job-header">
                        <a href="${{job.url}}" class="job-title" target="_blank">${{job.title}}</a>
                        <div class="job-actions">${{actions}}</div>
                    </div>
                    <div class="job-meta">
                        <span>Termen: ${{deadline}}</span>
                        ${{badges.join(' ')}}
                    </div>
                    <div class="keywords">${{keywords}}</div>
                </li>
            `;
        }}

        function createRightJobCard(job, listType) {{
            const deadline = formatDate(job.deadline_date || job.deadline);
            return `
                <li class="right-job" data-job-id="${{job.id}}">
                    <a href="${{job.url}}" class="right-job-title" target="_blank">${{job.title}}</a>
                    <div class="right-job-meta">
                        <span>${{deadline}}</span>
                        <button class="btn btn-undo" onclick="undoJob('${{job.id}}', '${{listType}}')">Anuleaza</button>
                    </div>
                </li>
            `;
        }}

        function markApplied(jobId) {{
            if (!applied.includes(jobId)) {{
                applied.push(jobId);
                irrelevant = irrelevant.filter(id => id !== jobId);
                saveState();
                render();
            }}
        }}

        function markIrrelevant(jobId) {{
            if (!irrelevant.includes(jobId)) {{
                irrelevant.push(jobId);
                applied = applied.filter(id => id !== jobId);
                saveState();
                render();
            }}
        }}

        function undoJob(jobId, listType) {{
            if (listType === 'applied') {{
                applied = applied.filter(id => id !== jobId);
            }} else {{
                irrelevant = irrelevant.filter(id => id !== jobId);
            }}
            saveState();
            render();
        }}

        function render() {{
            const mainJobs = allJobs.filter(j => !applied.includes(j.id) && !irrelevant.includes(j.id));
            const appliedJobs = allJobs.filter(j => applied.includes(j.id));
            const irrelevantJobs = allJobs.filter(j => irrelevant.includes(j.id));

            const bySource = {{}};
            mainJobs.forEach(job => {{
                if (!bySource[job.source]) bySource[job.source] = [];
                bySource[job.source].push(job);
            }});

            const mainContainer = document.getElementById('main-jobs');
            if (mainJobs.length === 0) {{
                mainContainer.innerHTML = '<div class="section"><p class="empty">Nu s-au gasit oportunitati de finantare. Verificati mai tarziu!</p></div>';
            }} else {{
                let html = '';
                for (const [source, jobs] of Object.entries(bySource)) {{
                    const sourceName = sourceNames[source] || source;
                    html += `<div class="section"><h2>${{sourceName}} (${{jobs.length}})</h2><ul class="job-list">`;
                    jobs.forEach(job => {{
                        html += createJobCard(job);
                    }});
                    html += '</ul></div>';
                }}
                mainContainer.innerHTML = html;
            }}

            const appliedList = document.getElementById('applied-list');
            document.getElementById('applied-count').textContent = appliedJobs.length;
            if (appliedJobs.length === 0) {{
                appliedList.innerHTML = '<li class="empty">Nicio aplicare inca</li>';
            }} else {{
                appliedList.innerHTML = appliedJobs.map(j => createRightJobCard(j, 'applied')).join('');
            }}

            const irrelevantList = document.getElementById('irrelevant-list');
            document.getElementById('irrelevant-count').textContent = irrelevantJobs.length;
            if (irrelevantJobs.length === 0) {{
                irrelevantList.innerHTML = '<li class="empty">Nimic marcat</li>';
            }} else {{
                irrelevantList.innerHTML = irrelevantJobs.map(j => createRightJobCard(j, 'irrelevant')).join('');
            }}

            document.getElementById('stat-total').textContent = mainJobs.length;
            document.getElementById('stat-closing').textContent = mainJobs.filter(j => j.closing_soon).length;
            document.getElementById('stat-high').textContent = mainJobs.filter(j => j.is_high_priority).length;
        }}

        loadState();
    </script>
</body>
</html>
'''

    try:
        DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DASHBOARD_FILE, 'w') as f:
            f.write(html)
        logger.info(f"Dashboard generated: {DASHBOARD_FILE}")
    except Exception as e:
        logger.error(f"Error generating dashboard: {e}")


def cleanup_old_funding(seen_data: Dict, current_ids: Set[str]) -> int:
    """Remove funding that is no longer listed (expired)"""
    old = [fid for fid in seen_data['funding'] if fid not in current_ids]
    for fid in old:
        del seen_data['funding'][fid]
    return len(old)


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("NGO Funding Scraper - Starting")
    logger.info("=" * 60)

    seen_data = load_seen_funding()
    logger.info(f"Loaded {len(seen_data['funding'])} previously seen items")

    all_funding = scrape_all_sources()
    logger.info(f"Total items scraped: {len(all_funding)}")

    current_ids = {item['id'] for item in all_funding}

    new_matching, all_matching = process_funding(all_funding, seen_data)

    logger.info(f"Matching items: {len(all_matching)}")
    logger.info(f"New matching items: {len(new_matching)}")

    notification_count = 0
    for item in new_matching:
        logger.info(f"  NEW: {item['title']}")
        logger.info(f"       Keywords: {', '.join(item['matched_keywords'][:5])}")
        if notifier.send_notification(item, item['matched_keywords']):
            notification_count += 1

    removed = cleanup_old_funding(seen_data, current_ids)
    if removed:
        logger.info(f"Removed {removed} expired items from database")

    now = datetime.now()
    seen_data['last_updated'] = now.isoformat()
    save_seen_funding(seen_data)

    last_updated = now.strftime("%Y-%m-%d %H:%M CET")
    generate_dashboard(all_matching, last_updated)

    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info(f"  Total scraped: {len(all_funding)}")
    logger.info(f"  Matching: {len(all_matching)}")
    logger.info(f"  New: {len(new_matching)}")
    logger.info(f"  Notifications sent: {notification_count}")
    logger.info("=" * 60)

    return 0


def test_notifications():
    """Test that notifications are working"""
    logger.info("Sending test notification...")
    if notifier.send_test_notification():
        logger.info("Test notification sent! Check your phone.")
        return 0
    else:
        logger.error("Failed to send test notification")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-notify":
        sys.exit(test_notifications())
    else:
        sys.exit(main())
