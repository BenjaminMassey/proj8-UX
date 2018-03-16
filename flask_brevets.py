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


###
# Verification Functions
###

def generate_auth_token(expiration, userID):
   s = Serializer(app.secret_key, expires_in=expiration)
   #s = Serializer('test1234@#$', expires_in=expiration)
   # pass index of user
   #return s.dumps({'id': 1})
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
    username = request.args.get('username', "", type=str)
    token = session['token']
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
    username = request.args.get('username', "", type=str)
    token = session['token']
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
    username = request.args.get('username', "", type=str)
    token = session['token']
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
    username = request.args.get('username', "", type=str)
    token = session['token']
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
    username = request.args.get('username', "", type=str)
    token = session['token']
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
    username = request.args.get('username', "", type=str)
    token = session['token']
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
            print("ruh roh", file=sys.stderr)
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
