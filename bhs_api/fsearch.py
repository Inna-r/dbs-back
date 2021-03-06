import logging
import re

from flask import abort, current_app
from bhs_api import phonetic

MAX_RESULTS=30 # aka chunk size

ARGS_TO_INDEX = {'first_name':       'name_lc.0',
                 'last_name':        'name_lc.1',
                 'sex':              'sex',
                 'birth_place':      'BIRT_PLAC_lc',
                 'marriage_place':   'MARR_PLAC_lc',
                 'tree_number':      'tree_num',
                 'death_place':      'DEAT_PLAC_lc',
                 'place':            'filler_lc', # a dummy field name
                 }

PROJECTION = {'name': 1,
              'parents': 1,
              'partners': 1,
              'siblings': 1,
              'tree_num': 1,
              'id': 1,
              'sex': 1,
              'tree_version': 1,
                }

def _generate_year_range(year, fudge_factor=0):
    maximum = int(str(year + fudge_factor) + '9999')
    minimum = int(str(year - fudge_factor) + '0000')
    return {'min': minimum, 'max': maximum}


def build_query(search_dict):
    ''' build a mongo search query based on the search_dict '''
    names_and_places = {}
    years = {}
    # Set up optional queries
    sex = None
    individual_id = None

    # Sort all the arguments to those with name or place and those with year
    for k, v in search_dict.items():
        if k.endswith('name') or k.endswith('place'):
            # The search is case insensitive
            names_and_places[k] = v.lower()
        elif '_year' in k:
            years[k] = v
        elif k == 'sex':
            if search_dict[k].lower() in ['m', 'f']:
                sex = v.upper()
        elif k == 'individual_id':
            individual_id = v

    # Build a dict of all the names_and_places queries
    for search_arg in names_and_places:
        field_name = ARGS_TO_INDEX[search_arg]
        split_arg = names_and_places[search_arg].split(';')
        search_str = split_arg[0]
        # No modifications are supported for first names because
        # firstname DMS (Soundex) values are not stored in the BHP database.
        if search_arg == 'first_name':
            qf = {field_name: search_str}
            names_and_places[search_arg] = qf
            continue
        if len(split_arg) > 1:
            if split_arg[1] == 'prefix':
                q = re.compile('^{}'.format(search_str))
                qf = {field_name: q}
            elif split_arg[1] == 'phonetic':
                q = phonetic.get_bhp_soundex(search_str)
                case_sensitive_fn = field_name.split('_lc')[0]
                field_name = case_sensitive_fn + 'S'
                qf = {field_name: q}
            # Drop wrong instructions - don't treat the part after semicolon
            else:
                qf = {field_name: search_str}
        else:
            # There is a simple string search
            qf = {field_name: search_str}

        names_and_places[search_arg] = qf

    # Build a dict of all the year queries
    for search_arg in years:
        if ':' in years[search_arg]:
            split_arg = years[search_arg].split(':')
            try:
                year = int(split_arg[0])
                fudge_factor = int(split_arg[1])
            except ValueError:
                abort(400, 'Year and fudge factor must be integers')
            years[search_arg] = _generate_year_range(year, fudge_factor)
        else:
            try:
                year = int(years[search_arg])
                years[search_arg] = year
            except ValueError:
                abort(400, 'Year must be an integer')
            years[search_arg] = _generate_year_range(year)

    year_ranges = {'birth_year': ['BSD', 'BED'],
                   'death_year': ['DSD', 'DED']}

    # Build gentree search query from all the subqueries
    search_query = {'archived': {'$exists': False}}

    for item in years:
        if item == 'marriage_year':
            # Look in the MSD array
            search_query['MSD'] = {'$elemMatch': {'$gte': years[item]['min'], '$lte': years[item]['max']}} 
            continue
        start, end = year_ranges[item]
        search_query[start] = {'$gte': years[item]['min']}
        search_query[end] = {'$lte': years[item]['max']}

    if sex:
        search_query['sex'] = sex
    
    for param, item in names_and_places.items():
        for k, v in item.items():
            # place is an or of all place fields
            if param == 'place':
                if k.endswith('S'):
                    s = 'S'
                else:
                    s = '_lc'
                search_query['$or'] = [{'BIRT_PLAC' + s: v},
                                       {'MARR_PLAC' + s: v},
                                       {'DEAT_PLAC' + s: v}]

            else:
                search_query[k] = v

    if 'tree_number' in search_dict:
        try:
            search_query['tree_num'] = int(search_dict['tree_number'])
            # WARNING: Discarding all the other search qeuries if looking for GTN and II
            if individual_id:
                search_query['id'] = individual_id
        except ValueError:
            abort(400, 'Tree number must be an integer')

    return search_query


def fsearch(max_results=15, db=None, **kwargs):
    '''
    Search in the genTreeIindividuals table.
    Names and places could be matched exactly, by the prefix match
    or phonetically:
    The query "first_name=yeh;prefix" will match "yehuda" and "yehoshua", while
    the query "first_name=yeh;phonetic" will match "yayeh" and "ben jau".
    Years could be specified with a fudge factor - 1907~2 will match
    1905, 1906, 1907, 1908 and 1909.
    If `tree_number` kwarg is present, return only the results from this tree.
    Return up to `MAX_RESULTS` starting with the `start` argument
    '''
    if db:
        collection = db['persons']
    else:
        collection = current_app.data_db['persons']
    search_dict = {}
    for key, value in kwargs.items():
        search_dict[key] = value[0]
        if not value[0]:
            abort(400, "{} argument couldn't be empty".format(key))


    search_query = build_query(search_dict)

    results = collection.find(search_query, {
              'name': 1,
              'parents': 1,
              'partners': 1,
              'siblings': 1,
              'tree_num': 1,
              'id': 1,
              'sex': 1,
              'tree_version': 1,
              'Slug': 1,
              'birth_year': 1,
              'death_year': 1,
              'BIRT_PLAC': 1,
              'DEAT_PLAC': 1,
              'deceased': 1,
                })
    total = results.count()

    if 'start' in search_dict:
        results = results.skip(int(search_dict['start']))
    results = results.limit(MAX_RESULTS)
    logging.debug('FSearch query:\n{} returning {} results'.format(
                    search_query, results.count()))
    return total, map(clean_person, results)


def clean_person(person):

    # mongo's id
    del person['_id']

    # translating gedcom names
    for db_key, api_key in (('BIRT_PLAC', 'birth_place'),
                     ('DEAT_PLAC', 'death_place'),
                     ('MARR_PLAC', 'marriage_place'),
                     ('MARR_DATE', 'marriage_date'),
                     ('OCCU', 'occupation'),
                     ('NOTE', 'bio'),
                     ):
        try:
            person[api_key] = person.pop(db_key)
        except KeyError:
            pass

    # remove the details of the living
    if not person['deceased']:
        for key in person.keys():
            if key in ['birth_year', 'death_year', 'birth_place',
                       'death_place', 'marriage_place', 'marriage_date',
                       'occupation', 'bio',
                      ]:
                del person[key]
    return person
