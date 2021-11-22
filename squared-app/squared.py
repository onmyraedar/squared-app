import datetime
import json
import os
import uuid

from dotenv import load_dotenv
from flask import flash, Flask, jsonify, redirect, render_template, request, url_for
from forms import PersonalDetailsForm, LoyaltyForm, ReferralForm
from square.client import Client
from urllib.parse import urlencode, parse_qs

app = Flask(__name__)
secret_key = os.getenv("SECRET_KEY")
app.config["SECRET_KEY"] = secret_key

load_dotenv()       # Takes environment variables from .env

access_token = os.getenv("SQUARE_ACCESS_TOKEN")
environment = os.getenv("SQ_ENVIRONMENT")
application_id = os.getenv("SANDBOX_APPLICATION_ID")
location_id = os.getenv("SANDBOX_LOCATION_ID")

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

@app.route("/checkout/<string:order_details>", methods=["GET", "POST"])
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
    form = PersonalDetailsForm()
    if form.validate_on_submit():
        e_164_phone_number = "+1" + form.phone_number.data
        print(e_164_phone_number)
        customer_result = client.customers.search_customers(
            body = {
            }
        )
        customer_id = "placeholder"
        if customer_result.is_success() and customer_result.body:
            for existing_customer in customer_result.body["customers"]:
                if existing_customer["phone_number"] == e_164_phone_number:
                    customer_id = existing_customer["id"]
                    print("Existing customer found!")
            if customer_id == "placeholder":
                new_customer = client.customers.create_customer(
                    body = {
                        "given_name": form.name.data,
                        "phone_number": e_164_phone_number
                    }
                )
                customer_id = new_customer.body["customer"]["id"]
                print("New customer created!")
        elif customer_result.is_error():
            print(customer_result.errors)
        n = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=20)
        pickup_time = n.isoformat()
        new_order = client.orders.create_order(
            body = {
                "order": {
                    "location_id": location_id,
                    "customer_id": customer_id,
                    "line_items": line_items,
                    "taxes": taxes,
                    "fulfillments": [
                        {
                            "type": "PICKUP",
                            "state": "PROPOSED",
                            "pickup_details": {
                                "recipient": {
                                    "display_name": form.name.data
                                },
                                "pickup_at": pickup_time
                            }
                        }
                    ],
                    "state": "DRAFT"
                },
                "idempotency_key": str(uuid.uuid1())
            }
        )
        order_id = new_order.body["order"]["id"]
        customer_result = client.customers.retrieve_customer(
            customer_id = customer_id
        )
        if customer_result.is_success():
            customer = customer_result.body["customer"]
            if "group_ids" in customer.keys():
                for group_id in customer["group_ids"]:
                    group_result = client.customer_groups.retrieve_customer_group(
                        group_id = group_id
                    )
                    if group_result.is_success():
                        if "Referral Group" in group_result.body["group"]["name"]:
                            name_of_group = group_result.body["group"]["name"]
                            message = f"You are in the {name_of_group}."
                    elif group_result.is_error():
                        print(group_result.errors)
                return(redirect(url_for("loyalty", order_id=order_id)))
            else:
                print("You aren't in any referral groups right now.")
                return(redirect(url_for("referrals", order_id=order_id)))
    return(render_template("checkout.html", title="Checkout", order=calculated_order, form=form))

@app.route("/loyalty/<string:order_id>", methods=["GET", "POST"])
def loyalty(order_id):
    form = LoyaltyForm()
    order_result = client.orders.retrieve_order(
        order_id = order_id
    )
    if order_result.is_success():
        order = order_result.body["order"]
    elif order_result.is_error():
        print(result.errors)
    if form.validate_on_submit():
        print("loyalty validated")
        return(redirect(url_for("payment", order_id=order_id)))
    return(render_template("loyalty.html", title="Loyalty", order=order, form=form))

@app.route("/referrals/<string:order_id>", methods=["GET", "POST"])
def referrals(order_id):
    form = ReferralForm()
    order_result = client.orders.retrieve_order(
        order_id = order_id
    )
    if order_result.is_success():
        order = order_result.body["order"]
    elif order_result.is_error():
        print(result.errors)
    if form.validate_on_submit():
        referral_code = form.referral_code.data
        if form.has_referral_code.data == "Yes" and form.wants_referral_group.data == "Yes":
            verification_result = client.customers.search_customers(
                body = {
                    "query": {
                        "filter": {
                            "reference_id": {
                                "exact": referral_code
                            }
                        }
                    }
                }
            )
            if verification_result.is_success():
                referrer = verification_result.body["customers"][0]
                for one_group_id in referrer["group_ids"]:
                    group_result = client.customer_groups.retrieve_customer_group(
                        group_id = one_group_id
                    )
                    if group_result.is_success():
                        group = group_result.body["group"]
                        if referral_code in group["name"]:
                            print(group["name"])
                            result = client.customers.add_group_to_customer(
                                customer_id = order["customer_id"],
                                group_id = one_group_id
                            )
                            print(order["customer_id"])
                            print("successfully added to group!")
            elif verification_result.is_error():
                print(verification_result.errors)
            loyalty_result = client.loyalty.retrieve_loyalty_program(
                program_id = "main"
            )
            if loyalty_result.is_success():
                loyalty_program = loyalty_result.body["program"]
                print(loyalty_program["id"])
                customer_result = client.customers.retrieve_customer(
                    customer_id = order["customer_id"]
                )
                if customer_result.is_success():
                    customer = customer_result.body["customer"]
                    print(customer["id"])
                    loyalty_add = client.loyalty.create_loyalty_account(
                        body = {
                            "loyalty_account": {
                                "program_id": loyalty_program["id"],
                                "customer_id": customer["id"],
                                "mapping": {
                                    "phone_number": customer["phone_number"]
                                }
                            },
                            "idempotency_key": str(uuid.uuid1())
                        }
                    )
                    print("successfully added to loyalty program!")
        print("referrals validated")
    return(redirect(url_for("loyalty", order_id=order_id)))

@app.route("/_verify_referral")
def _verify_referral():
    referral_code = request.args.get("code", "", type=str)
    data = {}
    if not referral_code:
        data["result"] = "Please enter a referral code in order to verify."
        return(jsonify(data))
    verification_result = client.customers.search_customers(
        body = {
            "query": {
                "filter": {
                    "reference_id": {
                        "exact": referral_code
                    }
                }
            }
        }
    )
    if verification_result.is_success():
        if not verification_result.body:
            data["result"] = "Sorry, this verification code wasn't in the system. Please try again."
        else:
            referrer = verification_result.body["customers"][0]["given_name"]
            data["result"] = f"Congratulations, you've been successfully referred by {referrer}! {referrer} will receive a reward for inviting you."
        print(data)
    elif verification_result.is_error():
        print(verification_result.errors)
    return jsonify(data)

@app.route("/payment/<string:order_id>")
def payment(order_id):
    order_result = client.orders.retrieve_order(
        order_id = order_id
    )
    if order_result.is_success():
        order = order_result.body["order"]
    elif order_result.is_error():
        print(order_result.errors)
    return(render_template("payment.html", title="Payment", order=order, application_id=application_id, location_id=location_id))

@app.route("/payment_handler", methods=["GET", "POST"])
def payment_handler():
    content = request.get_json(silent=True)
    order_result = client.orders.retrieve_order(
        order_id = content["orderId"]
    )
    if order_result.is_success():
        order = order_result.body["order"]
    elif order_result.is_error():
        print(result.errors)
    new_payment = {
        "idempotency_key": str(uuid.uuid1()),
        "location_id": content["locationId"],
        "source_id": content["sourceId"],
        "customer_id": order["customer_id"],
        "amount_money": order["total_money"]
    }
    result = client.payments.create_payment(
        new_payment
    )
    print(result)
    if result.is_success():
        payment = result.body["payment"]
        response = {
            "success": True,
            "payment": {
              "id": payment["id"],
              "status": payment["status"],
              "receiptUrl": payment["receipt_url"],
              "orderId": payment["order_id"]
              }
        }
        loyalty_result = client.loyalty.retrieve_loyalty_program(
            program_id = "main"
        )
        if loyalty_result.is_success():
            loyalty_program = loyalty_result.body["program"]
            print(loyalty_program["id"])
            calc_result = client.loyalty.calculate_loyalty_points(
                program_id = loyalty_program["id"],
                body = {
                    "transaction_amount_money": {
                        "amount": order["total_money"]["amount"],
                        "currency": order["total_money"]["currency"]
                    }
                }
            )
            points = calc_result.body["points"]
            print(points)
            loyalty_account_result = client.loyalty.search_loyalty_accounts(
                body = {
                    "query": {
                        "customer_ids": [
                            order["customer_id"]
                        ]
                    }
                }
            )
            loyalty_account_id = loyalty_account_result.body["loyalty_accounts"][0]["id"]
            print(loyalty_account_id)
            add_points_result = client.loyalty.accumulate_loyalty_points(
                account_id = loyalty_account_id,
                body = {
                    "accumulate_points": {
                        "points": points
                    },
                    "idempotency_key": str(uuid.uuid1()),
                    "location_id": order["location_id"]
                }
            )
            print(add_points_result)
        return(jsonify(response))

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")

if __name__ == '__main__':
    app.run(debug=True)
