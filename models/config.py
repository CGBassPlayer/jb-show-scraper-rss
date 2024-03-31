from typing import Dict, Set

from pydantic import BaseModel, HttpUrl, ConfigDict
from pydantic_xml import BaseXmlModel


class ScraperBaseModel(BaseModel):
    model_config: dict = ConfigDict(extra='ignore')


class ScraperBaseXmlModel(BaseXmlModel):
    model_config: dict = ConfigDict(extra='ignore')


class ShowDetails(ScraperBaseModel):
    show_rss: HttpUrl
    show_url: HttpUrl
    jb_url: HttpUrl
    acronym: str
    name: str


class ConfigData(ScraperBaseModel):
    shows: Dict[str, ShowDetails]


usernames_map: Dict[str, Set[str]]
