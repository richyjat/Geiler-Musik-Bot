import hashlib
import os

import bjoern
from flask import Flask, Response, redirect, request
from pymongo import MongoClient

HOST = "0.0.0.0"
PORT = 80
app = Flask(__name__)

mongo_url = os.environ.get("MONGODB_URI", "")
client = MongoClient(mongo_url)
db = client.discordbot


@app.route("/check_password", methods=["POST"])
def check_password():
    hashed = request.form["password"]
    if (
        hashed
        == hashlib.sha256(
            os.environ.get("RESTART_PASSWORD").encode()
        ).hexdigest()
    ):
        document = db.secure.find_one({"type": "restart_code"})
        return Response(document["code"])
    return Response("wrong_pw")


@app.route("/restart_token")
def restart_token():
    return Response(open("sites/password_check.html").read())


@app.route("/")
def index():
    return Response(open("sites/index.html").read())


@app.route("/response")
def response():
    return Response(open("sites/response.html").read())


@app.route("/mostplayed")
def mostplayed():
    return Response(open("sites/mostplayed.html").read())


@app.route("/http/mostplayed.js")
def mostplayedjs():
    return Response(open("scripts/mostplayed.js").read())


@app.route("/http/main.js")
def mainjs():
    return Response(open("scripts/main.js").read())


@app.route("/sha256.js")
def sha256js():
    return Response(open("scripts/sha256.js").read())


@app.route("/sjcl.js")
def sjcljs():
    return Response(open("scripts/sjcl.js").read())


@app.route("/http/chart.js")
def chartjs():
    return redirect(
        "https://github.com/chartjs/Chart.js/releases/download/v2.8.0/Chart.bundle.js",
        302,
    )


@app.route("/http/jquery.js")
def jqueryjs():
    return redirect(
        "https://ajax.googleapis.com/ajax/libs/jquery/3.4.0/jquery.min.js", 302
    )


@app.route("/http/mongo_most")
def mongo_most():
    collection = db.most_played_collection
    alfal = collection.find()
    ls = []
    for item in alfal:
        i = dict()
        i["name"] = item["name"]
        i["value"] = item["val"]
        ls.append(i)
    return Response(str(ls))


@app.route("/http/mongo_response")
def mongo_response():
    collection = db.connectiontime
    alfl = collection.find()
    ls = []
    for item in alfl:
        i = dict()
        i["x"] = item["x"]
        i["y"] = item["y"]
        ls.append(i)
    return Response(str(ls))


if __name__ == "__main__":
    bjoern.listen(host=HOST, port=PORT, wsgi_app=app)
    bjoern.run()
