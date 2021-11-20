import os

from dotenv import load_dotenv
from flask import Flask, render_template, url_for
from square.client import Client

app = Flask(__name__)
secret_key = os.getenv("SECRET_KEY")
app.config["SECRET_KEY"] = secret_key

load_dotenv()       # Takes environment variables from .env

access_token = os.getenv("SQUARE_ACCESS_TOKEN")
environment = os.getenv("SQ_ENVIRONMENT")

client = Client(
    access_token=access_token,
    environment=environment
)

@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html", title="Home")

@app.route("/stores")
def stores():
    result = client.locations.list_locations()
    if result.is_success():
        stores_list = result.body["locations"]
    elif result.is_error():
        print(result.errors)
    return render_template("stores.html", title="Stores", stores_list=stores_list)

@app.route("/catalog", methods=["GET", "POST"])
def catalog():
    items_result = client.catalog.list_catalog(
    types = "ITEM"
    )
    if items_result.is_success():
        items_list = items_result.body["objects"]
    elif items_result.is_error():
        print(items_result.errors)
    imgs_result = client.catalog.list_catalog(
    types = "IMAGE"
    )
    if imgs_result.is_success():
        imgs_list = imgs_result.body["objects"]
    elif imgs_result.is_error():
        print(imgs_result.errors)
    return render_template("catalog.html", title="Order", items_list=items_list, imgs_list=imgs_list)

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")

if __name__ == '__main__':
    app.run(debug=True)
