from frontmatter import load
from pytest import fixture

from models.config import ConfigData
from models.participant import Participant
from scraper import process_and_serialize_object


@fixture(autouse=True)
def configuration(mocker):
    return mocker.patch('scraper.CONFIGURATION', ConfigData(**{'shows': {}, 'data_dont_override': set(), 'usernames_map': {}}))


def test_rescrape_keeps_is_hidden_and_active(tmp_path):
    (tmp_path / 'friends.md').write_text('---\ntype: host\nusername: friends\ntitle: Friends\nis_hidden: true\nactive: false\n---\n')
    process_and_serialize_object('friends.md', Participant(type='host', username='friends', title='Friends',
                                                           avatar='/images/people/friends.png'), tmp_path, overwrite=True)
    metadata = load(tmp_path / 'friends.md').metadata
    assert metadata['is_hidden'] is True
    assert metadata['active'] is False
    assert metadata['avatar'] == '/images/people/friends.png'
