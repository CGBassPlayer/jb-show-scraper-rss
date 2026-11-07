from models.participant import Participant


def test_hand_maintained_front_matter_survives_round_trip():
    metadata = {'type': 'host', 'username': 'chris', 'title': 'Chris Fisher',
                'mastodon': 'https://podcastindex.social/@ChrisLAS', 'is_hidden': True, 'active': False}
    dumped = Participant(**metadata).model_dump(mode='json')
    assert dumped['mastodon'] == metadata['mastodon']
    assert dumped['is_hidden'] is True
    assert dumped['active'] is False


def test_new_participants_get_no_extra_keys():
    dumped = Participant(type='guest', username='x', title='X').model_dump(mode='json')
    assert 'is_hidden' not in dumped
    assert 'active' not in dumped
