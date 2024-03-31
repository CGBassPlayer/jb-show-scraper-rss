from typing import Optional, Literal

from pydantic import EmailStr, PositiveInt, AnyHttpUrl, Extra
from pydantic_xml import attr, element, wrapped

from models.config import ScraperBaseXmlModel

NSMAP = {
    'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
}

TYPE_VALUES = Literal[
    'episodic',
    'serial',
    'Episodic',
    'Serial'
]

EPISODE_TYPES = Literal[
    'Full',
    'Trailer',
    'Bonus',
]

Title: str = element(tag='title', default=None, ns='itunes', nsmap=NSMAP)


class ItunesImage(ScraperBaseXmlModel, tag='image', ns='itunes', nsmap=NSMAP):
    href: Optional[AnyHttpUrl] = attr(default=None)


Author: str = element(tag='author', default=None, ns='itunes', nsmap=NSMAP)


class Owner(ScraperBaseXmlModel, tag='owner', ns='itunes', nsmap=NSMAP):
    name: Optional[str] = wrapped('name', default=None)
    email: Optional[EmailStr] = wrapped('email', default=None)


Explicit: bool = element(tag='explicit', default=None, ns='itunes', nsmap=NSMAP)


class Category(ScraperBaseXmlModel, tag='category', ns='itunes', nsmap=NSMAP):
    text: str = attr()
    category: Optional[str] = wrapped('category', attr(name='text', default=None), default=None)


Type: Optional[TYPE_VALUES] = element(tag='type', default=None, ns='itunes', nsmap=NSMAP)

Duration: Optional[str] = element(tag='duration', default=None, ns='itunes', nsmap=NSMAP)

ItunesEpisode: Optional[PositiveInt] = element(tag='episode', default=None, ns='itunes', nsmap=NSMAP)

EpisodeType: Optional[EPISODE_TYPES] = element(tag='episodeType', default='Full', ns='itunes', nsmap=NSMAP)
