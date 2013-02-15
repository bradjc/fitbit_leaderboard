from __future__ import with_statement
from contextlib import closing
from datetime import datetime, date
import oauth2 as oauth
import sqlite3
import json 

from flask import Flask, render_template, request, g, make_response, jsonify
import fitbit

#config 
DATABASE = 'fitbit.db'
DEBUG = True
SECRET_KEY = 'dev key'
USERNAME = 'admin'
PASSWORD = 'sharedspace'
consumer_key = '4f0defd304af44e9a6790b0087070313'
consumer_secret = '737d767bf5024fda928ea039d77e1098'

day_converter = {
	0: 'm', 
	1: 't', 
	2: 'w',
	3: 'th',
	4: 'f',
	5: 's', 
	6: 'sun'
}

app = Flask(__name__)
app.config.from_object(__name__)

uauth_client = fitbit.Fitbit('4f0defd304af44e9a6790b0087070313', ' 737d767bf5024fda928ea039d77e1098 ')

def connect_db():
	return sqlite3.connect(app.config['DATABASE'])

def init_db():
	with closing(connect_db()) as db:
		with app.open_resource('schema.sql') as f:
			db.cursor().executescript(f.read())
		db.commit()

def query_db(query, args=(), one=False):
	cur = g.db.execute(query, args)
	rv = [dict((cur.description[idx][0], value)
			for idx, value in enumerate(row)) for row in cur.fetchall()]
	return (rv[0] if rv else None) if one else rv

# Right now just returns all user step info for the last week. Needs to filter by group (4908, cse, etc)
def get_group_info(): 
	user_cur = g.db.execute('select username, fitbit_user_key, fitbit_user_secret from user order by user_id desc')
	users = [dict(username=row[0], fitbit_user_key=row[1], fitbit_user_secret=row[2]) for row in user_cur.fetchall()]
	data = []
	for user in users: 
		oauth_fitbit = fitbit.Fitbit(consumer_key, consumer_secret, user_key=user['fitbit_user_key'], user_secret=user['fitbit_user_secret'])
		step_response = oauth_fitbit.time_series('activities/steps', period='1w')
		user_info = {}
		user_info['username'] = user['username'].encode('ascii')
		user_info['total_steps'] = 0
		user_info['step_counts'] = []
		for day in step_response['activities-steps']:
			mdate = datetime.strptime(day['dateTime'], "%Y-%m-%d")
			mweekday = day_converter[mdate.weekday()]
			user_info['step_counts'].append( { 'day':mweekday, 'steps':int(day['value']) } )
			user_info['total_steps'] += int(day['value'])
		data.append(user_info)

	data = sorted(data, key=lambda user_info: user_info['total_steps'], reverse=True)
	return data


@app.before_request
def before_request():
	g.db = connect_db()

@app.teardown_request
def teardown_request(exception):
	if hasattr(g, 'db'):
		g.db.close()

@app.route('/')
def home(): 
	return render_template('home.html')

@app.route('/register')
def register(): 
	request_token = uauth_client.client.fetch_request_token()
	fitbit_auth_url = uauth_client.client.authorize_token_url(request_token)
	response = make_response( render_template('register.html', fitbit_auth_url=fitbit_auth_url) )
	response.set_cookie('request_token_key', request_token.key)
	response.set_cookie('request_token_secret', request_token.secret)
	return response

@app.route("/registered", methods=["GET", "POST"])
def registered():
	if request.method == "POST":
		if not request.form['username']:
			return 'You must enter a username'
		elif not request.form['fitbit_verifier']:
			return 'You must enter a fitbit verifier'
		elif not request.cookies.get('request_token_key'):
			return "No request token key"
		elif not request.cookies.get('request_token_secret'):
			return "No request token secret"
		else:
			request_token = oauth.Token(request.cookies.get('request_token_key'), request.cookies.get('request_token_secret'))
			user_token = uauth_client.client.fetch_access_token(request_token, request.form['fitbit_verifier'])
			g.db.execute('insert into user (username, fitbit_verifier, fitbit_user_key, fitbit_user_secret) values (?, ?, ?, ?)', [request.form['username'], request.form['fitbit_verifier'], user_token.key, user_token.secret])
			g.db.commit()
		return render_template('registered.html')
	else: 
		return "Method error" 

@app.route("/show_users") 
def show_users():
	cur = g.db.execute('select username, fitbit_verifier, fitbit_user_key, fitbit_user_secret from user order by user_id desc')
	users = [dict(username=row[0], fitbit_verifier=row[1], fitbit_user_key=row[2], fitbit_user_secret=row[3]) for row in cur.fetchall()]
	return render_template('show_users.html', users=users)

@app.route("/group_info")
def group_info(): 
	data = get_group_info()
	return json.dumps(data)

@app.route("/leaderboard")
def leaderboard():
	data = get_group_info()
	return render_template('leaderboard.html', data=data)

if __name__ == '__main__':
	app.run(debug=True)
