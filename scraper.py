#!/usr/bin/env python3

import concurrent.futures
from html import escape
import sys
import re
from types import NoneType, SimpleNamespace
from unicodedata import normalize
import requests
import yaml
from bs4 import BeautifulSoup, NavigableString, SoupStrainer, Tag, ResultSet
from typing import Union, Optional, Dict, List
from pydantic import AnyHttpUrl, ValidationError
from frontmatter import Post, dumps, load
from html2text import html2text
from loguru import logger
from pathlib import Path
from threading import Lock

from models import Rss
from models.pick import Pick, PickShow
from models.scraper import Settings
from models.config import ConfigData, ShowDetails
from models.episode import Episode, Chapters
from models.participant import Participant
from models.item import Item
from models.podcast import Person
from models.sponsor import Sponsor
from models.strategies.sponsor import FiresideSponsorParse, PodhomeSponsorParse, SponsorParser
from models.strategies.tag import FiresideTagParse, PodhomeTagParse, TagParser


# The sponsors' data is collected into this global when episode files are scraped.
# This data is saved to files files after the episode files have been created.
SPONSORS: Dict[str, Sponsor] = {}  # JSON filename as key (e.g. "linode.com-lup.json")
PARTICIPANTS: Dict[str, Participant] = {}

LOCK = Lock()
CONFIGURATION: ConfigData = None

# Regex to strip Episode Numbers and information after the |
# https://regex101.com/r/gkUzld/
SHOW_TITLE_REGEX = re.compile(r"^(?:(?:Episode)?\s?[0-9]+:+\s+)?(.+?)(?:(\s+\|+.*)|\s+)?$")

def get_plain_title(title: str) -> str:
    """
    Get just the show title, without any numbering etc
    """
    return SHOW_TITLE_REGEX.match(title)[1]

def get_podcast_chapters(chapters: Chapters) -> Optional[Chapters]:
    """
        Get chapters and validate json structure
    """
    response: requests.Response = None

    for _ in range(Settings.Retry_Count):
        try:
            response = requests.get(chapters.url, headers={'Accept':'application/json'})
            response.raise_for_status()

            if not response.text:
                continue

            Chapters.model_validate_json(response.text)
            break

        except requests.exceptions.ChunkedEncodingError:
            logger.warning(f'Chapters request response error will retry. {chapters.url}')
            continue
        except requests.HTTPError:
            # No chapters
            return
        except AttributeError:
            return
        except ValidationError as e:
            logger.warning('Invalid chapters JSON.\n'
                           f'{e}\n' f'{chapters.url=}')
            return
    else:
        logger.error(f'Unable to retrive Chapters from {chapters.url}')

    return Chapters(**response.json())

def get_canonical_username(username: Person) -> str:
    """
    Get the last path part of the url which is the username for the hosts and guests.
    Replace it using the `username_map` from config.yml
    """

    return next(filter(str.__instancecheck__,(key for key, list in CONFIGURATION.usernames_map.items() if username.name in list)), username.name.lower().replace(" ", "-"))

def parse_sponsors(page_url: AnyHttpUrl, episode_number: str, show: str, show_details: ShowDetails) -> List[str]:
    """
    Fetch page and use parse strategy based on host platform to parse list of sponsors.
    """
    response = requests.get(page_url,headers={"Accept": "text/html,application/xhtml+xml,application/xml"})
    response.raise_for_status()

    page_soup = BeautifulSoup(response.text, features="html.parser")


    match show_details.host_platform:
        case 'podhome':
            parse_strategy = PodhomeSponsorParse()
        case _:
            parse_strategy = FiresideSponsorParse()

    try:
        sp: SponsorParser = SponsorParser(page_soup, show_details, parse_strategy, episode_number)
        sponsors = sp.run()
    except Exception as e:
        logger.warning(f"Failed to collect/parse sponsor data! # Show: {show} Ep: {episode_number}\n"
            f"{e}")
        sponsors = {}

    SPONSORS.update([(key, sponsor) for key, sponsor in sponsors.items() if  int(sponsor.episode or -1) > SPONSORS.get(key, SimpleNamespace(episode=-1)).episode])

    return list(map(lambda sponsor: sponsors[sponsor].shortname, sponsors))

def parse_tags(page_url: AnyHttpUrl, episode_number: str, show: str, show_details: ShowDetails) -> List[str]:
    """
    Fetch page and use parse strategy based on host platform to parse list of tags.
    """
    tags: List[str] = []
    try:
        response = requests.get(page_url,)
        page_soup = BeautifulSoup(response.text, features="html.parser")
    except requests.exceptions.MissingSchema:
        return tags

    match show_details.host_platform:
        case 'podhome':
            parse_strategy = PodhomeTagParse()
        case _:
            parse_strategy = FiresideTagParse()

    try:
        tag_parser: TagParser = TagParser(page_soup, show_details, parse_strategy)
        tags = tag_parser.run()
    except Exception as e:
        logger.warning(f"Failed to collect/parse tags! # Show: {show} Ep: {episode_number}\n"
            f"{e}")

    return tags

def parse_episode_number(title: str) -> str:
    """
    Get just the episode number, without the title text
    """
    # return re.match(r'.*?(\d+):', title).groups()[0]
    try:
        return re.match(r'.*?((?:Pocket Office )?\d+):', title).groups()[0]
    except AttributeError:
        return ''

def build_episode_file(item: Item, show: str, show_details: ShowDetails) -> None:
    if item.itunes_episodeType == 'bonus':
        logger.warning(f'Skipping episode of type {item.itunes_episodeType}:\n{item.title}')
        return

    episode_string = item.podcast_episode.episode if item.podcast_episode else parse_episode_number(item.title)
    episode_number, episode_number_padded = (int(episode_string), f'{int(episode_string):04}') if episode_string.isnumeric() else tuple((item.link.split("/")[-1],))*2

    output_file = Path(Settings.DATA_DIR) / 'content' / 'show' / show / f'{episode_number_padded.replace("/","")}.md'

    if not Settings.Overwrite_Existing and output_file.exists():
        logger.warning(f"Skipping saving `{output_file}` as it already exists and not overwriting")
        return

    try:
        sponsors = parse_sponsors(item.link, episode_number,show,show_details)
    except requests.HTTPError as e:
        logger.exception(
            f"Skipping {show_details.name} episode {episode_number} could not get episode page.\n"
            f"{e}"
        )
        return
    except requests.exceptions.MissingSchema:
        sponsors = set()
    tags = sorted(item.itunes_keywords.keywords) if item.itunes_keywords else parse_tags(item.link, episode_number,show,show_details)

    episode_links = get_links(item.content_encoded if item.content_encoded else item.description)

    # 🩹 for the launch phone number
    if show == 'the-launch':
        if episode_links[0:4] == '****':
            episode_links = episode_links.replace('****','**CALL 1-774-462-5667**')
        else:
            episode_links = '**CALL 1-774-462-5667**\n\n' + episode_links

    episode = Episode(
                show_slug=show,
                show_name=show_details.name,
                episode=episode_number,
                episode_padded=episode_number_padded,
                episode_guid=item.guid.guid,
                title=get_plain_title(item.title),
                description=item.itunes_subtitle.root if item.itunes_subtitle else get_description(item.description),
                date=item.pubDate,
                tags=tags,
                hosts=sorted(list(map(get_canonical_username, list(filter(lambda person: person.role in Settings.Host_Roles, item.podcast_persons))))),
                guests=sorted(list(map(get_canonical_username, list(filter(lambda person: person.role in Settings.Guest_Roles, item.podcast_persons))))),
                sponsors=sponsors,
                podcast_duration=item.itunes_duration.root,
                podcast_file=item.enclosure.url,
                podcast_bytes=item.enclosure.length,
                podcast_chapters=get_podcast_chapters(item.podcast_chapters),
                podcast_alt_file=None,
                podcast_ogg_file=None,
                video_file=None,
                video_hd_file=None,
                video_mobile_file=None,
                youtube_link=None,
                jb_url=f'{show_details.jb_url}/{episode_number}',
                fireside_url=item.link,
                value=item.podcast_value,
                episode_links=episode_links,
                transcripts=item.podcast_transcripts
            )

    # 🩹 for twib feed not supporting podcast:person
    if show == 'this-week-in-bitcoin' and len(episode.hosts) == 0:
        episode.hosts = ['chris']

    get_picks(item.description, episode_number, show, show_details)
    build_participants(item.podcast_persons)

    save_file(output_file, episode.get_hugo_md_file_content(), overwrite=Settings.Overwrite_Existing if output_file.name not in show_details.dont_override else False)

def get_picks(description: str, episode_number: int, show: str, show_details: ShowDetails) -> List[Pick]:
    picked: List[Pick] = []
    soup = BeautifulSoup(description, features="html.parser", parse_only=SoupStrainer(['a', 'li']))
    picks: ResultSet  = soup.find_all(['a','li>a'],string=re.compile('^Pick:.*'))
    for pick in picks:
        obj = Pick(
            title=pick.string.replace('Pick:','').strip(),
            url=pick['href'],
            description=pick.parent.contents[-1].replace('—', '').strip() if pick.parent.contents != [pick] else None,
            shows= [
                PickShow(
                    show=show_details.name,
                    episode=episode_number,
                    slug=show
                )
            ]
        )
        picked.append(obj)
        output_file = Path(f'{Settings.DATA_DIR}/data/picks/', re.sub(r'[\\/:*?"<>|]', "", obj.title.lower().replace(' ','-'))+'.yaml')
        save_file(output_file, dumps(Post('',**obj.model_dump(mode='json'))), overwrite=True)
    return picked

def get_links(description: str) -> str:
    """
    Parse only the show links, removing sponsors and description
    """
    soup = BeautifulSoup(description, features="html.parser", parse_only=SoupStrainer(['strong', 'ul', 'p']))
    # Remove Sponsor Links found in the description
    if type(sponsor_p := soup.find('p',string='Sponsored By:')) is not NoneType:
        sponsor_p.find_next('ul').decompose()
    if type(node := soup.find(['strong','p'],string=re.compile(r'.*Links|Show.*',re.IGNORECASE))) is not NoneType:
        while(type(node.previous_element) is not NoneType):
            node_next = node.previous_element
            if node.text == 'Affiliate LINKS:':
                node = node_next
                continue
            if type(node) is not NavigableString:
                node.decompose()
            else:
                node.extract()
            node = node_next

    soup = BeautifulSoup(str(soup), features="html.parser", parse_only=SoupStrainer(['strong', 'li']))

    for strong in soup.find_all('strong'):
        if type(strong.previous) is NavigableString:
            strong.insert_before(BeautifulSoup('<br/>', features="html.parser"))
        if strong.text == 'Affiliate LINKS:':
            strong.string.replace_with(strong.text.title())
        if br := strong.find('br'):
            br.extract()

    # Escape title attr that has quotes
    for link in soup.find_all('a'):
        if link.has_attr('title'):
            link['title'] = escape(link['title'])

    return re.sub(r'\ {2,}\n',r'\n', html2text(str(soup)).strip())

def get_description(description: str) -> str:
    """
    Parse only the description, excluding show links and sponsors
    """
    soup = BeautifulSoup(f'<div>{description.strip()}</div>', features="html.parser")

    for elem in soup.find_all(['br', 'em']):
        elem.unwrap()

    element = soup.find('div').next_element

    if isinstance(element, Tag):
        soup = BeautifulSoup(f'<div>{element.encode_contents().decode("utf-8")}</div>', features='html.parser')
        if len(elems := soup.find('div').find_all()) <= 1 and {tag.name for tag in elems} == {'a'}:
            return soup.find('div').text.strip()
        else:
            return soup.find('div').next_element.text.strip()

    description_parts: List[str] = [element.strip()]
    while not isinstance(element := element.next_element, Tag):
        if element.string == ' ':
            continue
        description_parts.append(element.strip())
    return emoji_strip(normalize('NFKC',' '.join(description_parts)))

def emoji_strip(description: str) -> str:
    emoji_pattern = re.compile(
        '^['
        '\U0001F600-\U0001F64F'  # Emoticons
        '\U0001F300-\U0001F5FF'  # Symbols & Pictographs
        '\U0001F680-\U0001F6FF'  # Transport & Map Symbols
        '\U0001F1E0-\U0001F1FF'  # Flags (iOS)
        '\U0001FA70-\U0001FAFF'  # Symbols and Pictographs Extended-A
        '\U00002702-\U000027B0'  # Dingbats
        '\U000024C2-\U0001F251'  # Miscellaneous Symbols and Pictographs
        r']+(\s+)?|(\s+)?['
        '\U0001F600-\U0001F64F'  # Emoticons
        '\U0001F300-\U0001F5FF'  # Symbols & Pictographs
        '\U0001F680-\U0001F6FF'  # Transport & Map Symbols
        '\U0001F1E0-\U0001F1FF'  # Flags (iOS)
        '\U0001FA70-\U0001FAFF'  # Symbols and Pictographs Extended-A
        '\U00002702-\U000027B0'  # Dingbats
        '\U000024C2-\U0001F251'  # Miscellaneous Symbols and Pictographs
        ']+$',
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', description)

def build_participants(participants: List[Person]):
    for participant in list(filter(lambda person: person.role in [*Settings.Host_Roles, *Settings.Guest_Roles], participants)):
        canonical_username = get_canonical_username(participant)
        filename = f'{canonical_username}.md'

        if participant.img:
            save_avatar_img(participant.img, canonical_username, f'images/people/{canonical_username}.{str(participant.img).split(".")[-1]}')

        PARTICIPANTS.update({
            filename: Participant(
                type='host' if participant.role in Settings.Host_Roles else 'guest',
                username=canonical_username,
                title=participant.name,
                homepage=str(participant.href) if participant.href else None,
                avatar=f'/images/people/{canonical_username}.{str(participant.img).split(".")[-1]}' if participant.img else None
            )
        })

def save_avatar_img(img_url: str, username: str, relative_filepath: str) -> None:
    """Save the avatar image only if it doesn't exist.

    Return the file path relative to the `static` folder.
    For example: "images/people/chris.jpg"
    """
    try:
        full_filepath = Path(Settings.DATA_DIR) / 'static' / relative_filepath

        # Check if file exist BEFORE the request. This is more efficient as it saves
        # time and bandwidth
        if full_filepath.exists():
            logger.warning(f"Skipping saving `{full_filepath}` as it already exists")
            return

        resp = requests.get(img_url)
        resp.raise_for_status()

        save_file(full_filepath, resp.content, mode="wb")
        logger.info(f"Saved file: {full_filepath}")

    except Exception:
        logger.exception("Failed to save avatar!\n"
                         f"  img_url: {img_url}"
                         f"  username: {username}")

def save_sponsors(executor: concurrent.futures.ThreadPoolExecutor) -> None:
    logger.info(">>> Saving the sponsors found in episodes...")
    sponsors_dir = Path(Settings.DATA_DIR) / 'content' / 'sponsors'
    futures = []
    for filename, sponsor in SPONSORS.items():
        futures.append(executor.submit(
            process_and_serialize_object,
            filename, sponsor, sponsors_dir, overwrite=Settings.Overwrite_Existing))

    # Drain all threads
    for future in concurrent.futures.as_completed(futures):
        future.result()
    logger.info(">>> Finished saving sponsors")
    SPONSORS.clear()

def save_participants(executor: concurrent.futures.ThreadPoolExecutor) -> None:
    logger.info(">>> Saving the participants found in episodes...")
    person_dir = Path(Settings.DATA_DIR) / 'content' / 'people'
    futures = []
    for filename, participant in PARTICIPANTS.items():
        futures.append(executor.submit(
            process_and_serialize_object,
            filename, participant, person_dir, overwrite=Settings.Overwrite_Existing))

    # Drain all threads
    for future in concurrent.futures.as_completed(futures):
        future.result()
    logger.info(">>> Finished saving participants")
    PARTICIPANTS.clear()

def process_and_serialize_object(filename: str, obj: Participant | Sponsor, dest_dir: Path, overwrite: bool = False) -> NoneType:
    """
    Prepares and saves the given Participant or Sponsor object to the specified file path.

    If the file already exists, for a Sponsor it checks if the current object is newer
    than the existing one (based on episode number), for a Participant it will update
    only the Avatar and Homepage attributes.

    Parameters:
        filename: The name of the file to save the object to
        obj: The Participant or Sponsor object to be saved
        dest_dir: The directory where the file should be saved
        overwrite: Whether to overwrite an existing file with the same name (default is False)

    Returns:
        None
    """
    file_path: Path = dest_dir / filename

    if file_path.exists() and filename in CONFIGURATION.data_dont_override:
        logger.warning(f"Filename `{filename}` found in `data_dont_override`! Will not save to it.")
        overwrite = False
        return


    if not file_path.exists():
        save_file(file_path, dumps(Post('',**obj.model_dump(mode='json'))), overwrite=overwrite)
        return

    with LOCK:
        with open(file_path) as file:
            post_file: Post = load(file)
            if isinstance(obj, Sponsor):
                if (file_ep := post_file.metadata.get("episode", None)) and int(file_ep) >= getattr(obj,'episode', -1):
                    logger.warning(f"Skipping saving `{file_path}` as the current file is the latest")
                    return

            if isinstance(obj, Participant):
                post_file.metadata.update({'homepage': obj.homepage, 'avatar': obj.avatar})
                obj = Participant(**post_file.metadata)

    # use json mode so URL types are converted to string for output to YAML
    save_file(file_path, dumps(Post('',**obj.model_dump(mode='json'))), overwrite=overwrite)

def save_file(file_path: Path, content: Union[bytes,str], mode: str = "w", overwrite: bool = False) -> bool:
    if not overwrite and file_path.exists():
        logger.warning(f"Skipping saving `{file_path}` as it already exists")
        return False

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, mode) as file:
        file.write(content)
    logger.info(f"Saved file: {file_path}")
    return True

def main():
    global CONFIGURATION
    with open("config.yml") as file:
        CONFIGURATION = ConfigData(**yaml.load(file, Loader=yaml.SafeLoader))

    for show, show_config in CONFIGURATION.shows.items():
        response = requests.get(show_config.show_rss)

        # Handle Fireside using the wrong Podcast Namesapce URL
        if show_config.host_platform == 'fireside':
            soup = BeautifulSoup(response.content, features='xml')
            rss_tag = soup.find('rss')
            if (ns_url := rss_tag.attrs.get('xmlns:podcast')) and ns_url != 'https://podcastindex.org/namespace/1.0':
                rss_tag.attrs['xmlns:podcast'] = 'https://podcastindex.org/namespace/1.0'
                del response
                response = SimpleNamespace(content=str(rss_tag))
        try:
            rss = Rss.from_xml(response.content)
        except ValidationError as e:
            logger.error(f'{e}\n')
            continue

        with concurrent.futures.ThreadPoolExecutor() as executor:

            futures = []
            for idx, item in enumerate(rss.channel.items):
                if Settings.LATEST_ONLY and idx >= Settings.LATEST_ONLY_EP_LIMIT:
                    logger.debug(f"Limiting scraping to only {Settings.LATEST_ONLY_EP_LIMIT} most"
                            " recent episodes")
                    break
                futures.append(executor.submit(
                    build_episode_file,
                    item,
                    show,
                    show_config))

            # Drain all threads
            for future in concurrent.futures.as_completed(futures):
                future.result()

            save_sponsors(executor)
            save_participants(executor)


if __name__ == "__main__":
    Settings = Settings()
    logger.remove()  # Remove default logger
    logger.add(sys.stderr, level=Settings.LOG_LVL)

    logger.info("🚀🚀🚀 SCRAPER STARTED! 🚀🚀🚀")
    main()
    logger.success("🔥🔥🔥 ALL DONE :) 🔥🔥🔥\n\n")
    exit(0)
