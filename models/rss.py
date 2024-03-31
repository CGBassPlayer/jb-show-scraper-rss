from typing import Optional

from pydantic_xml import attr

from models.channel import Channel
from models.config import ScraperBaseXmlModel


class Rss(ScraperBaseXmlModel, tag='rss'):
    version: Optional[float] = attr(default=None)
    encoding: Optional[str] = attr(default=None)
    channel: Channel
