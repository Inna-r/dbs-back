# -*- coding: utf-8 -*-
''' Testing items' Slugs
    ===================
    The documentation for client is at http://werkzeug.pocoo.org/docs/0.9/test/

    The documentation for advanced pytest fixtures use is at
    http://pytest.org/latest/fixture.html#fixture
'''
import urllib2

import mongomock

from pytest_flask.plugin import client, config

from bhs_api.item import fetch_items

def test_single_collection(client, mock_db):
    res = fetch_items(['personality_tester'], mock_db)
    assert res[0]['Slug']['En'] == 'personality_tester'
    res = fetch_items([u'אישיות_בודק'], mock_db)
    assert res[0]['Slug']['En'] == 'personality_tester'

    res = fetch_items(['personality_tester','personality_another-tester'], mock_db)
    assert len(res) == 2
    assert res[1]['error_code'] == 403

    res = fetch_items(['personality_no-one'], mock_db)
    assert res[0]['error_code'] == 404

    res = fetch_items(['unknown_unknown'], mock_db)
    assert res[0]['error_code'] == 404

    res = fetch_items(['hello'], mock_db)
    assert res[0]['error_code'] == 404

def test_person_collection(client):

    items = [{'GTN': 1,
              'II': 'I2',
              'StatusDesc': 'Completed',
              'RightsDesc': 'Full',
              'DisplayStatusDesc':  'free',
              'Name': {'En': 'tester',
                            'He': 'בודק',
                      },
              'tree': 'filler',
             }]
    db = mongomock.MongoClient().db
    persons = db.create_collection('genTreeIndividuals')
    for item in items:
        item['_id'] = persons.insert(item)

    res = fetch_items(['person_1.I2'], db)
    assert res[0]['Name']['En'] == 'tester'

    res = fetch_items(['person_1'], db)
    assert res[0]['error_code'] == 404

def test_multi_collections(client):
    pass
