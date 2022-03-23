# -*- coding: utf-8 -*-
"""
Classification Assistant webpage auxiliary functions
Author: Ignacio Heredia
Date: September 2017
"""

from flask import flash, Markup
import requests
import numpy as np
import os
from datetime import date, timedelta
import threading
import Queue
import json


metadata_binomial = list(np.genfromtxt(os.path.join('data', 'synsets.txt'), dtype='str', delimiter='/n'))

# Update variable assignment correspondingly to the db update executed in web.py
period = 3 * 30 * 24 * 3600 #1 month
def update_ids():
    global community_IDs
    t = threading.Timer(period, update_ids)
    t.daemon = True
    t.start()
    with open(os.path.join('data', 'community_IDs.json')) as f:
        community_IDs = json.load(f)
update_ids()
    

with open('error_messages.json') as f:
    error_dict = json.load(f)


def print_error(app, error_name):
    app.logger.error(error_name)
    error_message = '<center><b>{}</b></center>'.format(error_name)
    if error_name in error_dict.keys():
        error_message += '<br>{}'.format(error_dict[error_name])
    flash(Markup(error_message))


def find_base_url(community):
    if community == 'natusfera':
        return 'http://natusfera.gbif.es'
    if community == 'inaturalist':
        return 'https://www.inaturalist.org'


def check_credentials(community, username, password):
    url = find_base_url(community) + '/users/new_updates.json'
    r = requests.get(url, auth=(username, password))
    if r.status_code == 200:
        return 'OK'
    else:
        return 'error'


def date_to_list(date_str): 
    return [int(i) for i in date_str.split('-')] # [year, month, day]


def check_dates(start_date, end_date):
    try:
        s, e = date_to_list(start_date), date_to_list(end_date)
    except:
        return 'Invalid date format'
    try:
        start_date, end_date = date(*s), date(*e)
    except:
        return 'Invalid date value'
    if start_date > end_date:
        return 'Invalid time interval'
    elif end_date > date.today():
        return 'Invalid end date'
    else:
        return 'OK'


def download_observations(community, username, start_date, end_date,
                          photo_size='medium', max_list_size=50): #photo_size: small, medium,large
    """
    Download observations from coomunities.
    
    Parameters
    ----------
    community, username, start_date, end_date : strs
    photo_size: {'small', 'medium', 'large'}
    max_list_size: int
    """

    print 'Downloading the observations ...'
    
    results = []
    base_url =  find_base_url(community)
    observations_url = base_url + '/observations.json'
    
    s, e = date_to_list(start_date), date_to_list(end_date)
    start_date, end_date = date(*s), date(*e)
    delta = end_date - start_date # timedelta
    
    # Download observation
    done = False 
    for i in range(delta.days + 1):
        current_date = start_date + timedelta(days=i)
        print 'Date {}'.format(current_date)
        p = 1 # page counter
        
        if done:
            break
        
        while True and not done:
            print 'Page {}'.format(p)
            
            try:
    #            time.sleep(np.random.rand()*2)
                params = {'day':current_date.day, 'month':current_date.month, 'year':current_date.year,
                          'page':p, 'per_page':max_list_size, 'iconic_taxa': 'Plantae', 'has':'photos'}
                p += 1
                im_list = requests.get(observations_url, params=params).json()
                
                if im_list:
                    
                    # Filter out observations already identified
                    for obs in im_list:
                        obs_url = base_url + '/observations/{}.json'.format(obs['id'])
                        id_list = requests.get(obs_url).json()['identifications']
                        
                        append = True
                        for obs_user_id in id_list:
                            if obs_user_id['user']['login'] == username: #the user has already identified the observation
                                append = False
                                break
                            
                        if append:
                                results += [obs]

                        if len(results) > max_list_size: # we have enough observations
                            done = True
                            break
                        
                else:
                    break
                
            except Exception as e:
                print e
    
    # Keep only the essential info about observations to make the predictions                     
    filtered_results = []
    for r in results:
        
        im_list = []
        for photo in r['photos']:
            im_list.append(photo['{}_url'.format(photo_size)])
        
        taxon_id_name = r['taxon'].get('name')
        tmp_dict = {'url_link': base_url + '/observations/{}'.format(r['id']),
                    'im_list': im_list,
                    'community_id_name': taxon_id_name,
                    'obs_id': r['id']}
        
        filtered_results.append(tmp_dict)
    
    return filtered_results


def make_prediction(obs_dict, prediction_url):
    """
    Query the web API for the observation identification
    
    Returns
    -------
    The observation dict updated with the predicted labels and their respective
    probabilities.
    """
    r = requests.post(prediction_url, data={'mode':'url', 'url_list':obs_dict['im_list']})
    
    obs_dict.update({'pred_prob': r.json()['pred_prob'],
                     'pred_lab': r.json()['pred_lab'],
                     'google_images_link': r.json()['google_images_link'],
                     'wikipedia_link': r.json()['wikipedia_link']
                     })
    return obs_dict
    

def check_id_db(community, pred_lab):
    """
    Check if some label exists in the (Natusfera|iNaturalist) database
    
    Returns
    -------
    ID number or None is not existent
    """
    pred_lab_index = metadata_binomial.index(pred_lab)
    id_num = community_IDs[community][pred_lab_index]
    return id_num


def upload_obs(community, username, password, id_info):
    """
    Upload your identification to (Natusfera|iNaturalist)
    """
    url = find_base_url(community) + '/identifications.json'
    params_dict ={'identification[observation_id]': id_info['obs_id'],
                  'identification[taxon_id]': id_info['species_id']}
    requests.post(url, params=params_dict, auth=(username, password))
    
    
def buffered_gen_threaded(source_gen, buffer_size=5):
    """
    Generator that runs a slow source generator in a separate thread. Beware of the GIL!
    buffer_size: the maximal number of items to pre-generate (length of the buffer)
    Author: Benanne (github-kaggle/benanne/ndsb)
    """
    if buffer_size < 2:
        raise RuntimeError("Minimal buffer size is 2!")

    buffer = Queue.Queue(maxsize=buffer_size - 1)
    # the effective buffer size is one less, because the generation process
    # will generate one extra element and block until there is room in the buffer.

    def _buffered_generation_thread(source_gen, buffer):
        for data in source_gen:
            buffer.put(data, block=True)
        buffer.put(None)  # sentinel: signal the end of the iterator

    thread = threading.Thread(target=_buffered_generation_thread, args=(source_gen, buffer))
    thread.daemon = True
    thread.start()

    for data in iter(buffer.get, None):
        yield data


def id_queue(obs_list, prediction_url='http://plants.deep.ifca.es/api', shuffle=False):
    """
    Returns generator of identifications via buffer.
    Therefore we perform the identification query for the nxt observation
    while the user is still observing the current information.
    """
    print "Generating the identification buffer ..."
    if shuffle:
        indices = np.arange(len(obs_list))
        np.random.shuffle(indices)

    def gen(obs_list):
        for obs in obs_list:
            yield make_prediction(obs, prediction_url)

    return buffered_gen_threaded(gen(obs_list))
