import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, url_for
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
    items_result = client.catalog.list_catalog()
    if items_result.is_success():
        items_list = [item for item in items_result.body["objects"] if item["type"] == "ITEM"]
        categories_list = [item for item in items_result.body["objects"] if item["type"] == "CATEGORY"]
    elif items_result.is_error():
        print(items_result.errors)
        print(categories_result.errors)
    imgs_result = client.catalog.list_catalog(
    types = "IMAGE"
    )
    if imgs_result.is_success():
        imgs_list = imgs_result.body["objects"]
    elif imgs_result.is_error():
        print(imgs_result.errors)
    if request.method == "POST":
        desired_items = {}
        for item in items_list:
            desired_items[item["item_data"]["name"]] = request.form[item["id"]]
        print(desired_items)
        return jsonify(desired_items)
    return render_template("catalog.html", title="Order", items_list=items_list, imgs_list=imgs_list, categories_list=categories_list)

@app.route("/_update_order_summary")
def _update_order_summary():
    quantities = request.args.get("quantities", "error", type=str)
    quantities = json.loads(quantities)
    summary_dict = {}
    for item_id in quantities["quantityDict"].keys():
        item_result = client.catalog.retrieve_catalog_object(
            object_id = item_id
        )
        if item_result.is_success():
            item_name = item_result.body["object"]["item_data"]["name"]
            quantity = float(quantities["quantityDict"][item_id])
            if quantity != 0:
                item_price = item_result.body["object"]["item_data"]["variations"][0]["item_variation_data"]["price_money"]["amount"]
                summary_dict[item_name] = str(float(quantity) * (float(item_price) / 100))
        elif result.is_error():
            print(result.errors)
        print(summary_dict)
        print(jsonify(summary_dict))
    return(jsonify(summary_dict))

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")

if __name__ == '__main__':
    app.run(debug=True)
