#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Data utils of the webpage.

Author: Ignacio Heredia
Date: October 2017
"""

import os
import requests
from bs4 import BeautifulSoup
import numpy as np
import json
import time, threading
from webpage_utils import find_base_url


plantnet_synsets = np.genfromtxt(os.path.join('data', 'synsets.txt'), dtype='str', delimiter=';')

def update_community_id(community):
    """
    Function to find the (Natusfera|iNaturalist) IDs of the species in our 
    database (synsets) and write them to the ID database
    
    Parameters
    ----------
    community : str {'natusfera', 'inaturalist'}
    """
    print 'Updating {} ID database ...'.format(community)
    base_url = find_base_url(community)
    id_list = []
    for spe in plantnet_synsets:
        url = base_url + '/taxa/search?'
        response = requests.get(url, params={'q': spe})
        
        # Find taxa element in html
        soup = BeautifulSoup(response.content, 'lxml')
        i = soup.find("a", {"class":"name sciname"})
        if i is None:
            i = soup.find("a", {"class":"name comname"})
    
        #Extract taxa name and taxa ID
        if i is not None:
            taxon_id = i['href'].split('/taxa/')[1].split('-')[0]
            #taxon_name = i.find('span', {'class':'sciname'}).contents[0]
            id_list.append(taxon_id)              
        else:       
            id_list.append('None')
    
    # Write results to database
    with open(os.path.join('data', 'community_IDs.json')) as f:
        community_IDs = json.load(f)
    community_IDs[community] = id_list
    with open(os.path.join('data', 'community_IDs.json'), 'w') as f:
        json.dump(community_IDs, f)


def update_db(period, delay):
    """
    This creates a separate thread that will periodically update the ID database
    after initially waiting an inital delay time
    """
    time.sleep(delay)
    t = threading.Timer(period - delay, update_db)
    t.daemon = True
    t.start()
    update_community_id('natusfera')
    update_community_id('inaturalist')


def periodical_db_update(period, delay):
    """
    Instead of launching the update_db thread we have to launch it throught this
    mother thread.
    This trick is so that we can correctly delay the update and meanwhile 
    launch the webpage.
    """
    print "Launching the db update thread..."
    assert period > delay
    t = threading.Thread(target=update_db, args=(period, delay))
    t.daemon = True
    t.start()
    