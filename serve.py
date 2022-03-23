#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Interactive Natusfera Assistant

Author: Ignacio Heredia
Date: September 2017

Description:
    This script queries (Natusfera|iNaturalist) for observations in their database. 
    For each image we query an image classification API (deep.ifca.es) and show 
    the predictions to the user.
    If the user agrees the identification is uploaded to that community.

Tip:
To host the app in a subpath through a proxy_pass with nginx check Ross's anwer in [1].
Redirections must then be made with either:
* redirect(url_for('intmain', _external=True))    
* redirect('./')

References:
[1] https://stackoverflow.com/questions/25962224/running-a-flask-application-at-a-url-that-is-not-the-domain-root
"""
import os
import random, string
from flask import Flask, render_template, request, redirect, url_for, session
from webpage_utils import (print_error, download_observations, id_queue, check_id_db,
                           upload_obs, check_credentials, check_dates)
from data_utils import periodical_db_update


# Run a separate thread to update periodically the ID database
period = 3 * 30 * 24 * 3600 # 6 months in seconds
delay = 1 * 30 * 24 * 3600	# wait 1 months before first update   
periodical_db_update(period, delay)

app = Flask(__name__)
user_db = {}

if os.path.isfile('secret_key.txt'):
    app.secret_key = open('secret_key.txt', 'r').read()
else:
    app.secret_key = 'devkey, should be in a file'


@app.route('/')
def intmain():
    return render_template("index.html")


@app.route('/presubmit', methods=['POST'])
def presubmit():
    global user_db
       
    # Collect form info
    community = request.form['community']
    username = request.form['username']
    password = request.form['password']    
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    cutoff = float(request.form['cutoff'])
    
    print start_date, end_date
    
    # Check missing form
    if (not community) or (not start_date) or (not end_date) or (not cutoff) or (not username) or (not password):
        print_error(app, 'Incomplete form')
        return redirect(url_for('intmain', _external=True))  
    
    # Check validity of inputs
    if check_credentials(community, username, password) == 'error':
        print_error(app, 'Invalid credentials')
        return redirect(url_for('intmain', _external=True))
    
    m = check_dates(start_date, end_date)
    if m != 'OK':
        print_error(app, m)
        return redirect(url_for('intmain', _external=True))
    
    # Store info
    user_id = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(20)) # random ID
    session['userID'] = user_id
    user_info = {'community': community, 
                 'username': username,
                 'password': password,
                 'start_date': start_date,
                 'end_date': end_date,
                 'cutoff': cutoff}
    user_db[user_id] = user_info
   
    # Query for prediction list
    try:
        obs_list = download_observations(community, username, start_date, end_date)
    except:
        print_error(app, 'Portal error')
        return redirect(url_for('intmain', _external=True))
    try:
        id_list = id_queue(obs_list, prediction_url='http://plants.deep.ifca.es/api')
        user_db[user_id]['id_list'] = id_list
    except:
        print_error(app, 'Classification API error')
        return redirect(url_for('intmain', _external=True))

    # Return any classificarion above cutoff
    try:
        while True:
            current_obs = next(id_list)
            if current_obs['pred_prob'][0] > cutoff:
                break
            else:
                print 'Discard: probability did not met the cutoff'
        user_db[user_id]['current_obs'] = current_obs
    except:
        user_db.pop(session['userID'], None)
        return render_template("end.html")
    
    return render_template("results.html", predictions=current_obs)


@app.route('/decision', methods=['POST'])
def decision():
    global user_db
       
    # Recall variables
    user_id = session['userID']
    community = user_db[user_id]['community']
    username = user_db[user_id]['username']
    password = user_db[user_id]['password']    
    cutoff = user_db[user_id]['cutoff']
    current_obs = user_db[user_id]['current_obs']
    id_list = user_db[user_id]['id_list']
    
    # Submit observation
    if request.form['button'] == 'submit':
        pred_num = int(request.form['prediction_number'])
        label = current_obs['pred_lab'][pred_num]
        id_num = check_id_db(community, label)
        
        # Check if label is present in Natusfera database
        if id_num == 'None':
            print_error(app, 'Nonexistent ID')
            return render_template("results.html", predictions=current_obs)
        
        else:
            print 'Identification uploaded'
            id_info = {'obs_id': current_obs['obs_id'],
                       'species_id': int(id_num)}
            upload_obs(community, username, password, id_info)

    # Discard observation
    elif request.form['button'] == 'discard':
        print 'Identification discarded'
    
    # Return any classificarion above cutoff
    try:
        while True:
            current_obs = next(id_list)
            if current_obs['pred_prob'][0] > cutoff:
                break
            else:
                print 'Discard: probability did not met the cutoff'
        user_db[user_id]['current_obs'] = current_obs
    except:
        user_db.pop(session['userID'], None)
        return render_template("end.html")
        
    return render_template("results.html", predictions=current_obs)


if __name__ == '__main__':
    app.debug = False
    app.run()
    
