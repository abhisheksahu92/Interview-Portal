"""WeWorkRemotely's programming RSS feed.

Titles arrive as "Company: Role" so the company is split off the title; the
description is HTML, which :func:`snippet_of` flattens.
"""

import xml.etree.ElementTree as ET

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get

FEED = "https://weworkremotely.com/categories/remote-programming-jobs.rss"


class WwrRssAdapter(Adapter):
    slug = "wwr_rss"
    name = "We Work Remotely"
    kind = "RSS"

    def fetch(self, source):
        return self.parse(get(source.config.get("url") or FEED, check_robots=True))

    def parse(self, raw):
        root = ET.fromstring(raw)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            company, _, role = title.partition(":")
            link = (item.findtext("link") or "").strip()
            yield RawItem(
                external_id=(item.findtext("guid") or link).strip(),
                title=(role or title).strip(),
                url=link,
                company_name=company.strip() if role else "",
                snippet=snippet_of(item.findtext("description")),
                location=(item.findtext("region") or "Anywhere").strip(),
                remote=True,
                tags=[(c.text or "").strip().lower() for c in item.findall("category")],
                posted_at=parse_dt(item.findtext("pubDate")),
            )
