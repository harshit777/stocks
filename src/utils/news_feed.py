"""
Headlines from Google News RSS — free, no API key.

Never raises: any network/parse problem returns an empty list so the trading
loop is never affected by news availability.
"""
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
_UA = "Mozilla/5.0 (compatible; trading-research/1.0)"

# Tickers that make poor search terms -> company names
_ALIASES = {
    'IDFCFIRSTB': 'IDFC First Bank', 'CANBK': 'Canara Bank', 'PNB': 'Punjab National Bank',
    'BANKBARODA': 'Bank of Baroda', 'TATASTEEL': 'Tata Steel', 'TATAMOTORS': 'Tata Motors',
    'ICICIBANK': 'ICICI Bank', 'HDFCBANK': 'HDFC Bank', 'AXISBANK': 'Axis Bank',
    'KOTAKBANK': 'Kotak Mahindra Bank', 'INDUSINDBK': 'IndusInd Bank', 'FEDERALBNK': 'Federal Bank',
    'SBIN': 'State Bank of India', 'ITC': 'ITC Ltd', 'ONGC': 'ONGC', 'NTPC': 'NTPC',
    'POWERGRID': 'Power Grid', 'COALINDIA': 'Coal India', 'SAIL': 'SAIL steel',
    'YESBANK': 'Yes Bank', 'IRCTC': 'IRCTC', 'WIPRO': 'Wipro', 'TECHM': 'Tech Mahindra',
    'HCLTECH': 'HCL Technologies', 'BPCL': 'BPCL', 'JSWSTEEL': 'JSW Steel', 'HINDALCO': 'Hindalco',
}

MARKET_QUERY = "Sensex Nifty stock market India"


def query_for(symbol: str) -> str:
    return f"{_ALIASES.get(symbol, symbol)} share price"


def parse_rss(xml_text: str, max_items: int = 8, max_age_hours: float = 36.0,
              now: Optional[datetime] = None) -> List[Dict]:
    """Parse a Google News RSS document into [{title, source, age_hours}], newest first."""
    now = now or datetime.now(timezone.utc)
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    for item in root.iter('item'):
        title = (item.findtext('title') or '').strip()
        if not title:
            continue
        source = ''
        src = item.find('source')
        if src is not None and src.text:
            source = src.text.strip()
        if ' - ' in title:                       # Google appends " - Publisher"
            head, tail = title.rsplit(' - ', 1)
            if not source or tail.strip() == source:
                title, source = head.strip(), source or tail.strip()
        age = None
        try:
            pub = parsedate_to_datetime(item.findtext('pubDate') or '')
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age = max((now - pub).total_seconds() / 3600.0, 0.0)
        except Exception:
            pass
        if age is not None and age > max_age_hours:
            continue
        out.append({'title': title, 'source': source,
                    'age_hours': round(age, 1) if age is not None else None})
        if len(out) >= max_items:
            break
    return out


def fetch(query: str, max_items: int = 8, max_age_hours: float = 36.0,
          timeout: float = 6.0) -> List[Dict]:
    """Fetch recent headlines for a search query. Returns [] on any failure."""
    try:
        url = _RSS.format(q=urllib.parse.quote_plus(f"{query} when:2d"))
        req = urllib.request.Request(url, headers={'User-Agent': _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_rss(r.read().decode('utf-8', 'replace'), max_items, max_age_hours)
    except Exception as e:
        logger.debug(f"news fetch failed for {query!r}: {e}")
        return []
