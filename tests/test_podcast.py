from models.podcast import Block, Guid, Episode, SocialInteract
from uuid import UUID
from pydantic import ValidationError
import pytest

def test_podcast_guid():
    assert Guid(root='daddde30-f61d-47d2-9f59-a8fcc4d2e68d').root == UUID('daddde30-f61d-47d2-9f59-a8fcc4d2e68d')
    assert Guid(root='11ccb502-6a54-46a5-8e40-5226b495de04').root == UUID('11ccb502-6a54-46a5-8e40-5226b495de04')
    assert Guid(root='11ccb502-6a54-46a5-8e40-5226b495de04').to_xml() == b'<podcast:guid xmlns:podcast="https://podcastindex.org/namespace/1.0">11ccb502-6a54-46a5-8e40-5226b495de04</podcast:guid>'
    assert Guid.from_xml(b'<podcast:guid xmlns:podcast="https://podcastindex.org/namespace/1.0">11ccb502-6a54-46a5-8e40-5226b495de04</podcast:guid>') == Guid(root='11ccb502-6a54-46a5-8e40-5226b495de04')

def test_podcast_episode():
    assert Episode(display='ep1', episode='1').episode == '1'
    assert Episode(display='ep1', episode='1').display == 'ep1'
    assert Episode(display='ep1', episode='1').to_xml() == b'<podcast:episode xmlns:podcast="https://podcastindex.org/namespace/1.0" display="ep1">1</podcast:episode>'
    assert Episode.from_xml(b'<podcast:episode xmlns:podcast="https://podcastindex.org/namespace/1.0" display="ep1">1</podcast:episode>') == Episode(display='ep1', episode='1')

def test_podcast_socialInteract():
    assert SocialInteract(protocol='disabled', uri='https://podcastindex.social/web/@dave/108013847520053258', accountId='@dave').to_xml() == b'<podcast:socialInteract xmlns:podcast="https://podcastindex.org/namespace/1.0" protocol="disabled"/>'
    assert SocialInteract(protocol='activitypub', uri='https://podcastindex.social/web/@dave/108013847520053258', accountId='@dave').to_xml() == b'<podcast:socialInteract xmlns:podcast="https://podcastindex.org/namespace/1.0" protocol="activitypub" uri="https://podcastindex.social/web/@dave/108013847520053258" accountId="@dave"/>'
    assert SocialInteract.from_xml(b'<podcast:socialInteract xmlns:podcast="https://podcastindex.org/namespace/1.0" priority="1" protocol="activitypub" uri="https://podcastindex.social/web/@dave/108013847520053258" accountId="@dave" accountUrl="https://podcastindex.social/web/@dave"/>') == SocialInteract(protocol='activitypub', uri='https://podcastindex.social/web/@dave/108013847520053258', accountId='@dave', accountUrl='https://podcastindex.social/web/@dave', priority=1)

def test_podcast_block():
    assert Block(block="yes").block == 'yes'
    assert Block(block="yes").to_xml() == b'<podcast:block xmlns:podcast="https://podcastindex.org/namespace/1.0">yes</podcast:block>'
    assert Block(block="yes",id='youtube').to_xml() == b'<podcast:block xmlns:podcast="https://podcastindex.org/namespace/1.0" id="youtube">yes</podcast:block>'
    assert Block.from_xml(b'<podcast:block xmlns:podcast="https://podcastindex.org/namespace/1.0" id="blubrry">yes</podcast:block>') == Block(block="yes",id='blubrry')
    assert Block.from_xml(b'<podcast:block xmlns:podcast="https://podcastindex.org/namespace/1.0">yes</podcast:block>') == Block(block="yes")
    with pytest.raises(ValidationError):
        assert Block.from_xml(b'<podcast:block xmlns:podcast="https://podcastindex.org/namespace/1.0" id="invalid">yes</podcast:block>') == Block(block="yes",id='invalid')