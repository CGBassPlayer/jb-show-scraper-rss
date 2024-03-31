from models.config import ScraperBaseModel


class Sponsor(ScraperBaseModel):
    shortname: str
    title: str
    description: str
    link: str
