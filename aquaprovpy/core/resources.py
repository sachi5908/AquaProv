"""Load documentation and support URLs from the resource-links configuration."""

import json
from pathlib import Path
from urllib.parse import urlsplit

RESOURCE_LINKS_PATH = Path(__file__).resolve().parents[1] / 'assets' / 'resource_links.json'


def load_resource_links(path=RESOURCE_LINKS_PATH):
    """Return configured HTTP(S) links, leaving missing or invalid values blank.

    If no issue URL is supplied, derive it from a GitHub repository URL.
    """
    links = dict.fromkeys(('documentation_url', 'manual_url', 'github_url', 'issues_url'), '')
    try:
        values = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return links
    if not isinstance(values, dict):
        return links
    for name in links:
        value = values.get(name, '')
        if not isinstance(value, str):
            continue
        value = value.strip()
        try:
            url = urlsplit(value)
            if url.scheme in ('https', 'http') and url.hostname:
                links[name] = value
        except ValueError:
            continue
    if not links['issues_url'] and links['github_url']:
        url = urlsplit(links['github_url'])
        parts = url.path.strip('/').split('/')
        if url.hostname == 'github.com' and len(parts) == 2:
            links['issues_url'] = f'{url.scheme}://github.com/{parts[0]}/{parts[1]}/issues'
    return links
