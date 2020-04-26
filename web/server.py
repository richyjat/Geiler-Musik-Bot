"""
Server
"""
import hashlib
import os

from pymongo import MongoClient

import bjoern
from flask import Flask, Response, redirect, request

HOST = "0.0.0.0"
PORT = 80
APP = Flask(__name__)

MONGO_URL = os.environ.get("MONGODB_URI", "")
CLIENT = MongoClient(MONGO_URL)
DB = CLIENT.discordbot


@APP.route("/check_password", methods=["POST"])
def check_password() -> Response:
    """
    Check the password
    @return:
    """
    hashed = request.form["password"]
    if (
        hashed
        == hashlib.sha256(
            os.environ.get("RESTART_PASSWORD").encode()
        ).hexdigest()
    ):
        document = DB.secure.find_one({"type": "restart_code"})
        return Response(document["code"])
    return Response("wrong_pw")


@APP.route("/restart_token")
def restart_token() -> Response:
    """
    Provide the restart token page
    @return:
    """
    return Response(open("sites/password_check.html").read())


@APP.route("/")
def index() -> Response:
    """
    Provide Index
    @return:
    """
    return Response(open("sites/index.html").read())


@APP.route("/response")
def response() -> Response:
    """
    Provide Response
    @return:
    """
    return Response(open("sites/response.html").read())


@APP.route("/mostplayed")
def mostplayed() -> Response:
    """
    Provide Most Played
    @return:
    """
    return Response(open("sites/mostplayed.html").read())


@APP.route("/http/mostplayed.js")
def mostplayedjs() -> Response:
    """
    Provide Most Played JS
    @return:
    """
    return Response(open("scripts/mostplayed.js").read())


@APP.route("/http/main.js")
def mainjs() -> Response:
    """

    @return:
    """
    return Response(open("scripts/main.js").read())


@APP.route("/sha256.js")
def sha256js() -> Response:
    """

    @return:
    """
    return Response(open("scripts/sha256.js").read())


@APP.route("/sjcl.js")
def sjcljs() -> Response:
    """

    @return:
    """
    return Response(open("scripts/sjcl.js").read())


@APP.route("/http/chart.js")
def chartjs() -> Response:
    """

    @return:
    """
    return redirect(
        "https://github.com/chartjs/Chart.js/releases/download/v2.8.0/Chart.bundle.js",
        302,
    )


@APP.route("/http/jquery.js")
def jqueryjs() -> Response:
    """

    @return:
    """
    return redirect(
        "https://ajax.googleapis.com/ajax/libs/jquery/3.4.0/jquery.min.js", 302
    )


@APP.route("/http/mongo_most")
def mongo_most() -> Response:
    """

    @return:
    """
    collection = DB.most_played_collection
    alfal = collection.find()
    _list = []
    for item in alfal:
        i = dict()
        i["name"] = item["name"]
        i["value"] = item["val"]
        _list.append(i)
    return Response(str(_list))


@APP.route("/http/mongo_response")
def mongo_response() -> Response:
    """
    @return:
    """
    collection = DB.connectiontime
    alfl = collection.find()
    _list = []
    for item in alfl:
        i = dict()
        i["x"] = item["x"]
        i["y"] = item["y"]
        _list.append(i)
    return Response(str(_list))


if __name__ == "__main__":
    bjoern.listen(host=HOST, port=PORT, wsgi_app=APP)
    bjoern.run()
