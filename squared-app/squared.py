import json
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from square.client import Client
from urllib.parse import urlencode, parse_qs

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

@app.template_filter()
def currencyFormat(value):
    value = float(value)
    return "${:,.2f}".format(value)

@app.route("/catalog/<string:location_id>", methods=["GET", "POST"])
def catalog(location_id):
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
            quantity = int(request.form[item["id"]])
            if quantity > 0:
                desired_items[item["item_data"]["variations"][0]["id"]] = request.form[item["id"]]
        desired_items["location_id"] = location_id
        encoded_order = urlencode(desired_items)
        return redirect(url_for("checkout", order_details=encoded_order))
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
                item_total_cost = float(quantity) * (float(item_price) / 100)
                formatted_total_cost = str("${:,.2f}".format(item_total_cost))
                summary_dict[item_name] = formatted_total_cost
        elif result.is_error():
            print(result.errors)
    return(jsonify(summary_dict))

@app.route("/checkout/<string:order_details>")
def checkout(order_details):
    details_dct = parse_qs(order_details)
    location_id = details_dct["location_id"][0]
    details_dct.pop("location_id", None)
    line_items = []
    for line_item_id, quantity in details_dct.items():
        line_items.append(
            {
                "quantity": quantity[0],
                "catalog_object_id": line_item_id
            }
        )
    taxes = []
    tax_result = client.catalog.list_catalog(
        types = "TAX"
    )
    if tax_result.is_success():
        for tax in tax_result.body["objects"]:
            taxes.append(
                {
                    "catalog_object_id": tax["id"],
                    "scope": "ORDER"
                }
            )
    elif tax_result.is_error():
        print(tax_result.errors)
    calculate_order_result = client.orders.calculate_order(
        body = {
            "order": {
                "location_id": location_id,
                "line_items": line_items,
                "taxes": taxes
            }
        }
    )
    if calculate_order_result.is_success():
        calculated_order = calculate_order_result.body["order"]
    elif calculate_order_result.is_error():
        print(calculate_order_result.errors)
    return(render_template("checkout.html", title="Checkout", order=calculated_order))

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")

if __name__ == '__main__':
    app.run(debug=True)
