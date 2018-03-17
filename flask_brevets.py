"""
Replacement for RUSA ACP brevet time calculator
(see https://rusa.org/octime_acp.html)

"""

import flask
from flask import request, session
from pymongo import MongoClient
import arrow  # Replacement for datetime, based on moment.js
import acp_times  # Brevet time calculations
import config
import sys
import datetime

from itsdangerous import (TimedJSONWebSignatureSerializer \
                                  as Serializer, BadSignature, \
                                  SignatureExpired)

import logging
import password

from flask_wtf import Form, CSRFProtect
from wtforms import TextField, PasswordField, BooleanField, validators
from flask_login import LoginManager, UserMixin, \
                                login_required, login_user, logout_user 

###
# Globals
###

app = flask.Flask(__name__)
CONFIG = config.configuration()
app.secret_key = CONFIG.SECRET_KEY
client = MongoClient(CONFIG.MONGO_URL)
db = client.get_default_database()
collection = db['times']
usersCollection = db['users']

csrf = CSRFProtect()
csrf.init_app(app)

###
# Login stuff
###
# Lots of random basic code from https://flask-login.readthedocs.io/en/latest/

login_manager = LoginManager()

login_manager.init_app(app)


usersList = []
class User:
   def __init__(self, name, ID, auth, active, anon):
      self.username = name
      self.userID = ID
      self.is_authenticated = auth
      self.is_active = active
      self.is_anonymous = anon
      global usersList
      usersList.append(self)
   def get_id(self):
      return self.userID

@login_manager.user_loader
def load(user_id):
   global usersList
   for user in usersList:
      if user.get_id() == user_id:
         return user
   return None

def is_safe_url(url):
   if "virus" in url.lower():
      return False
   else:
      return True

# http://flask.pocoo.org/snippets/64/
class LoginForm(Form):
    username = TextField('Username', [validators.Required()])
    password = PasswordField('Password', [validators.Required()])
    remember = BooleanField('Remember Me', [validators.Required()])

    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):

        if self.username.data == None or self.password.data == None:
            return False

        data = usersCollection.find()
        userID = None
        for datum in data:
            if datum['username'] == self.username.data:
               userID = datum['_id']

        if userID is None:
            flask.flash("Unknown username")
            return False

        
        user = User(self.username.data, userID, True, True, False)

        if not verifyPassword(self.username.data, self.password.data):
            flask.flash("Invalid password")
            return False

        print("holy crap it worked", file=sys.stderr)

        self.user = user
        return True

def loginAUser(user):
   token = generate_auth_token(600, user.userID)
   session['token'] = token

@app.route('/logout')
def logout():
   global usersList
   if (session['token'] == None) or (len(usersList) == 0):
       return flask.jsonify(result={"message":"Not logged in currently, so can't log out"})
   else:
       session['token'] = None
       message = "Successfully logged out of " + usersList[len(usersList) - 1].username
       usersList = []
       return flask.jsonify(result={"message":message})

@app.route('/login', methods=['GET', 'POST'])
def login():

    session['token'] = 'DUMMY'
    
    form = LoginForm()
    if form.validate():
        
        loginAUser(form.user)

        flask.flash('Logged in successfully as ' + form.user.username  + '.')
        
        nextPage = flask.request.args.get('next')

        if nextPage == None:
           if not form.remember.data:
               return flask.render_template('calc.html')
           else:
               # Cookies: https://www.tutorialspoint.com/flask/flask_cookies.htm
               resp = flask.make_response(flask.render_template('calc.html'))
               resp.set_cookie('token', session['token'])
               return resp
        if not is_safe_url(nextPage):
            return flask.abort(400)
        else:
           return flask.redirect(nextPage)
         
    return flask.render_template('login.html', form=form)

###
# Verification Functions
###

def generate_auth_token(expiration, userID):
   s = Serializer(app.secret_key, expires_in=expiration)
   return s.dumps({'id': str(userID)})

def verify_auth_token(token):
    s = Serializer(app.secret_key)
    try:
        data = s.loads(token)
    except SignatureExpired:
        return None    # valid token, but expired
    except BadSignature:
        return None    # invalid token
    return "Success"

def verifyPassword(username, passwordRAW):
    if len(usersList) > 0 and session['token'] != None: # Using token auth
          verify_auth_token(session['token'])
    pwHASH = None
    data = usersCollection.find()
    for datum in data:
        if datum['username'] == username:
            pwHASH = datum['password']
    if pwHASH == None:
        return False
    if password.verify_password(passwordRAW, pwHASH):
        return True
    else:
        return False

###
# Pages
###


@app.route("/")
@app.route("/index")
def index():
    session['token'] = 'DUMMY'
    app.logger.debug("Main page entry")
    return flask.render_template('calc.html')


@app.errorhandler(404)
def page_not_found(error):
    app.logger.debug("Page not found")
    flask.session['linkback'] = flask.url_for("index")
    return flask.render_template('404.html'), 404


###############
#
# AJAX request handlers
#   These return JSON, rather than rendering pages.
#
###############
@app.route("/_calc_times")
def _calc_times():
    """
    Calculates open/close times from miles, using rules
    described at https://rusa.org/octime_alg.html.
    Expects one URL-encoded argument, the number of miles.
    """
    app.logger.debug("Got a JSON request")
    notes = ""
    km = request.args.get('km', 0, type=float)
    brevet = request.args.get('brevet', 200, type=int)
    if km > brevet:
        if brevet * 1.2 < km:
            notes = "Distance much longer than brevet - an accident?"
        else:
            notes = "Distance a bit longer than brevet, so used brevet"
    if km < 15:
        notes = "Distance a bit small - might cause weirdness"
    beginDate = request.args.get('beginDate', "2017-01-01", type=str)
    beginTime = request.args.get('beginTime', "00:00", type=str)
    splitBeginDate = beginDate.split("-")
    beginYear = splitBeginDate[0]
    beginMonth = splitBeginDate[1]
    beginDay = splitBeginDate[2]
    splitBeginTime = beginTime.split(":")
    beginHour = splitBeginTime[0]
    beginMin = splitBeginTime[1]
    beginTimeFinal = beginYear+"-"+beginMonth+"-"+beginDay+"T"+beginHour+":"+beginMin
    app.logger.debug("km={}".format(km))
    app.logger.debug("brevet={}".format(brevet))
    app.logger.debug("request.args: {}".format(request.args))
    open_time = acp_times.open_time(km, brevet, beginTimeFinal)
    close_time = acp_times.close_time(km, brevet, beginTimeFinal)
    result = {"open": open_time, "close": close_time, "notes": notes}
    return flask.jsonify(result=result)


@app.route("/_submit_DB")
def _submit_DB():
    collection.delete_many({}) # Clear entire collection
    kms = request.args.get('kms', "", type=str).split("~")
    opens = request.args.get('opens', "", type=str).split("~")
    closes = request.args.get('closes', "", type=str).split("~")
    noteses = request.args.get('noteses', "", type=str).split("~")
    username = request.args.get('username', "", type=str)
    rawPassword = request.args.get('password', "", type=str)
    verified = verifyPassword(username, rawPassword)
    if verified:
        for i in range(len(kms)-1):
            collection.insert({"km": str(kms[i]), "open": opens[i], "close": closes[i], "notes": noteses[i], "username":username})
        result = {"message":"Successfully pushed to database!"}
        return flask.jsonify(result=result)
    else:
        result = {"message":"Failed to push to database - wrong credentials"}
        return flask.jsonify(result=result)
    

@app.route("/_load_DB")
def _load_DB():
    username = request.args.get('username', "", type=str)
    rawPassword = request.args.get('password', "", type=str)
    verified = verifyPassword(username, rawPassword)
    if not verified:
        result = {"kms":[], "miles":[], "opens":[], "closes":[], "noteses":[],"message":"Could not verify user credentials..."}
        return flask.jsonify(result=result)
    data = collection.find()
    kms = []
    miles = []
    opens = []
    closes = []
    noteses = []
    for datum in data:
        if len(datum['km']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
            kms.append(str(int(round(float(datum['km']), 0))))
            miles.append(str(round(float(datum['km']) * 0.621371, 1)))
            opens.append(datum['open'])
            closes.append(datum['close'])
            noteses.append(datum['notes'])
    result = {"kms": kms, "miles": miles, "opens": opens, "closes": closes, "noteses": noteses,"message":"Successfully loaded from the database!"}
    return flask.jsonify(result=result)

@app.route("/listAll/json")
@app.route("/listAll")
def listAll():
    if len(usersList) == 0:
        username = request.args.get('username', "", type=str)
    else:
        username = usersList[len(usersList) - 1].username
    token = session['token']
    if token == None:
        # Handles remember me with cookies, or else it breaks
        cookie = request.cookies.get('token')
        if cookie == None:
            return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})
        else:
            token = cookie
    verified = verify_auth_token(token);
    if verified == "Success":
        data = collection.find()
        opens = []
        closes = []
        for datum in data:
            if len(datum['open']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
                opens.append(datum['open'])
                closes.append(datum['close'])
        html = "<html><body><p>{</br></br>"
        for i in range(len(opens)):
            if i < len(opens) - 1:
                html += '&emsp;{</br>&emsp;&emsp;"open": "' + opens[i] + '",</br>&emsp;&emsp;"close": "' + closes[i] + '"</br>&emsp;},</br></br>'
            else:
                html += '&emsp;{</br>&emsp;&emsp;"open": "' + opens[i] + '",</br>&emsp;&emsp;"close": "' + closes[i] + '"</br>&emsp;}</br></br>'
        html += "}</p></body></html>"
        return flask.jsonify(result={"result":html})
    else:
        return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})


@app.route("/listOpenOnly/json")
@app.route("/listOpenOnly")
def listOpenOnly():
    if len(usersList) == 0:
        username = request.args.get('username', "", type=str)
    else:
        username = usersList[len(usersList) - 1].username
    token = session['token']
    if token == None:
        # Handles remember me with cookies, or else it breaks
        cookie = request.cookies.get('token')
        if cookie == None:
            return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})
        else:
            token = cookie
    verified = verify_auth_token(token);
    if verified == "Success":
        k = request.args.get('top', default = "999", type = str)
        if len(k) > 0:
            k = int(k)
        else:
            k = 999
        data = collection.find()
        opens = []
        for datum in data:
            if len(datum['open']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
                opens.append(datum['open'])
        if k != 999:
            opens.sort(key=lambda x: datetime.datetime.strptime(x, '%a %m/%d %H:%M'))
            # https://stackoverflow.com/a/2589484
        html = "<html><body><p>{</br></br>"
        for i in range(len(opens)):
            if k == i:
                break
            if i < len(opens) - 1:
                html += '&emsp;{</br>&emsp;&emsp;"open": "' + opens[i] + '"</br>&emsp;},</br></br>'
            else:
                html += '&emsp;{</br>&emsp;&emsp;"open": "' + opens[i] + '"</br>&emsp;}</br></br>'
        html += "}</p></body></html>"
        return flask.jsonify(result={"result":html})
    else:
        return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})

@app.route("/listCloseOnly/json")
@app.route("/listCloseOnly")
def listCloseOnly():
    if len(usersList) == 0:
        username = request.args.get('username', "", type=str)
    else:
        username = usersList[len(usersList) - 1].username
    token = session['token']
    if token == None:
        # Handles remember me with cookies, or else it breaks
        cookie = request.cookies.get('token')
        if cookie == None:
            return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})
        else:
            token = cookie
    verified = verify_auth_token(token);
    if verified == "Success":
        k = request.args.get('top', default = "999", type = str)
        if len(k) > 0:
            k = int(k)
        else:
            k = 999
        data = collection.find()
        closes = []
        for datum in data:
            if len(datum['close']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
                closes.append(datum['close'])
        if k != 999:
            closes.sort(key=lambda x: datetime.datetime.strptime(x, '%a %m/%d %H:%M'))
            # https://stackoverflow.com/a/2589484
        html = "<html><body><p>{</br></br>"
        for i in range(len(closes)):
            if k == i:
                break
            if i < len(closes) - 1:
                html += '&emsp;{</br>&emsp;&emsp;"close": "' + closes[i] + '"</br>&emsp;},</br></br>'
            else:
                html += '&emsp;{</br>&emsp;&emsp;"close": "' + closes[i] + '"</br>&emsp;}</br></br>'
        html += "}</p></body></html>"
        return flask.jsonify(result={"result":html})
    else:
        return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})

@app.route("/listAll/csv")
def listAllCSV():
    if len(usersList) == 0:
        username = request.args.get('username', "", type=str)
    else:
        username = usersList[len(usersList) - 1].username
    token = session['token']
    if token == None:
        # Handles remember me with cookies, or else it breaks
        cookie = request.cookies.get('token')
        if cookie == None:
            return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})
        else:
            token = cookie
    verified = verify_auth_token(token);
    if verified == "Success":
        data = collection.find()
        opens = []
        closes = []
        for datum in data:
            if len(datum['open']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
                opens.append(datum['open'])
                closes.append(datum['close'])
        html = "<html><body><p>Open, Close</br>"
        for i in range(len(opens)):
            html += opens[i] + ", " + closes[i] + "</br>"
        html += "</p></body></html>"
        return flask.jsonify(result={"result":html})
    else:
        return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})

@app.route("/listOpenOnly/csv")
def listOpenOnlyCSV():
    if len(usersList) == 0:
        username = request.args.get('username', "", type=str)
    else:
        username = usersList[len(usersList) - 1].username
    token = session['token']
    if token == None:
        # Handles remember me with cookies, or else it breaks
        cookie = request.cookies.get('token')
        if cookie == None:
            return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})
        else:
            token = cookie
    verified = verify_auth_token(token);
    if verified == "Success":
        k = request.args.get('top', default = "999", type = str)
        if len(k) > 0:
            k = int(k)
        else:
            k = 999
        data = collection.find()
        opens = []
        for datum in data:
            if len(datum['open']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
                opens.append(datum['open'])
        if k != 999:
            opens.sort(key=lambda x: datetime.datetime.strptime(x, '%a %m/%d %H:%M'))
            # https://stackoverflow.com/a/2589484
        html = "<html><body><p>Open</br>"
        for i in range(len(opens)):
            if k == i:
                break
            html += opens[i] + "</br>"
        html += "</p></body></html>"
        return flask.jsonify(result={"result":html})
    else:
        return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})

@app.route("/listCloseOnly/csv")
def listCloseOnlyCSV():
    if len(usersList) == 0:
        username = request.args.get('username', "", type=str)
    else:
        username = usersList[len(usersList) - 1].username
    token = session['token']
    if token == None:
        # Handles remember me with cookies, or else it breaks
        cookie = request.cookies.get('token')
        if cookie == None:
            return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})
        else:
            token = cookie
    verified = verify_auth_token(token);
    if verified == "Success":
        k = request.args.get('top', default = "999", type = str)
        if len(k) > 0:
            k = int(k)
        else:
            k = 999
        data = collection.find()
        closes = []
        for datum in data:
            if len(datum['close']) > 0 and datum['username'] == username: # Ignore it if it's a blank one
                closes.append(datum['close'])
        if k != 999:
            closes.sort(key=lambda x: datetime.datetime.strptime(x, '%a %m/%d %H:%M'))
            # https://stackoverflow.com/a/2589484
        html = "<html><body><p>Close</br>"
        for i in range(len(closes)):
            if k == i:
                break
            html += closes[i] + "</br>"
        html += "</p></body></html>"
        return flask.jsonify(result={"result":html})
    else:
        return flask.jsonify(result={"result":"<html>401: Cannot verify your credentials, please try again!</html>"})


@app.route("/api/register")
def registerUser():
    un = request.args.get('username', default = "", type = str)
    pwRAW = request.args.get('password', default = "", type = str)
    data = usersCollection.find()
    for datum in data:
        if datum['username'] == un:
            result = {"location": "", "username": "", "password": "", "message": "400: Username '"+un+"' is already taken."}
            return flask.jsonify(result=result)#, 400
    pw = password.hash_password(pwRAW)
    usersCollection.insert({"username":un, "password":pw})
    ids = []
    data = usersCollection.find()
    for datum in data:
        ids.append(datum['_id'])
    location = str(ids[len(ids) - 1])
    token = generate_auth_token(600, location)
    session['token'] = token
    result = {"location": location, "username": un, "password": pw, "message": ""}
    return flask.jsonify(result=result), 201

@app.route("/api/token")
def testAuthToken():
    un = request.args.get('username', default = "", type = str)
    pwRAW = request.args.get('password', default = "", type = str)
    verified = verifyPassword(un, pwRAW)
    if verified:
        dur = 600
        token = generate_auth_token(600, "dummy")
        if verify_auth_token(token) == "Success":
            result = {"token": str(token), "duration": str(dur), "message": ""}
            return flask.jsonify(result=result), 201
        else:
            result = {"token": "", "duration": "", "message": "401: Sorry, but the token failed to verify!"}
            return flask.jsonify(result=result)#, 401
    else:
        result = {"token": "", "duration": "", "message": "401: Sorry, but that password is wrong!"}
        return flask.jsonify(result=result)#, 401

@app.route("/api/token/receive")
def getToken():
    if len(usersList) > 0: # Already have a token set
        return flask.jsonify(result={"success":"yes"})
    un = request.args.get('username', default = "", type = str)
    pwRAW = request.args.get('password', default = "", type = str)
    verified = verifyPassword(un, pwRAW)
    if verified:
        userID = ""
        data = usersCollection.find()
        for datum in data:
            if datum['username'] == un:
                userID = datum['_id']
        if userID == "":
            result = {"success":"no"}
        else:
            token = generate_auth_token(600, userID)
            session['token'] = token
            result = {"success":"yes"}
    else:
        result = {"success":"no"}
    return flask.jsonify(result=result)

#############

app.debug = CONFIG.DEBUG
if app.debug:
    app.logger.setLevel(logging.DEBUG)

if __name__ == "__main__":
    print("Opening for global access on port {}".format(CONFIG.PORT))
    app.run(port=CONFIG.PORT, host="0.0.0.0")
