"""Adapter registry: one instance per upstream feed, keyed by adapter slug.

``Source.adapter_slug`` is what looks a row up here, so the ~30 ATS board rows
all share the four ATS adapters and differ only by ``config["slug"]``.
"""

from sources.adapters.adzuna import AdzunaAdapter
from sources.adapters.arbeitnow import ArbeitnowAdapter
from sources.adapters.ashby import AshbyAdapter
from sources.adapters.base import Adapter, RawItem
from sources.adapters.freelancer import FreelancerAdapter
from sources.adapters.greenhouse import GreenhouseAdapter
from sources.adapters.himalayas import HimalayasAdapter
from sources.adapters.hn import HackerNewsAdapter
from sources.adapters.jobicy import JobicyAdapter
from sources.adapters.lever import LeverAdapter
from sources.adapters.manual import ManualAdapter
from sources.adapters.reddit import RedditAdapter
from sources.adapters.remoteok import RemoteOkAdapter
from sources.adapters.remotive import RemotiveAdapter
from sources.adapters.smartrecruiters import SmartRecruitersAdapter
from sources.adapters.wwr_rss import WwrRssAdapter

ADAPTERS = {
    adapter.slug: adapter
    for adapter in (
        HackerNewsAdapter(),
        RemotiveAdapter(),
        ArbeitnowAdapter(),
        RemoteOkAdapter(),
        JobicyAdapter(),
        HimalayasAdapter(),
        WwrRssAdapter(),
        FreelancerAdapter(),
        GreenhouseAdapter(),
        LeverAdapter(),
        AshbyAdapter(),
        SmartRecruitersAdapter(),
        RedditAdapter(),
        AdzunaAdapter(),
        ManualAdapter(),
    )
}

__all__ = ["ADAPTERS", "Adapter", "RawItem"]
