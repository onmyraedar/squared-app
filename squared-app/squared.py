import datetime
import dateutil.parser
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

def process(api_response):
    if api_response.is_success():
        print("Success")
    elif api_response.is_error():
        print(api_response.errors)

def get_order_by_id(order_id):
    order_result = client.orders.retrieve_order(
        order_id = order_id
    )
    process(order_result)
    return order_result.body["order"]

@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html", title="Home")

@app.route("/stores")
def stores():
    result = client.locations.list_locations()
    process(result)
    stores_list = result.body["locations"]
    return render_template("stores.html", title="Stores", stores_list=stores_list)

# Converts Catalog API currency: ex. 500 cents -> $5.00
@app.template_filter()
def currencyFormat(value):
    value = float(value)
    return "${:,.2f}".format(value)

@app.route("/catalog/<string:location_id>", methods=["GET", "POST"])
def catalog(location_id):
    items_result = client.catalog.list_catalog()
    process(items_result)
    catalog_items = items_result.body["objects"]
    items = [item for item in catalog_items if item["type"] == "ITEM"]
    categories = [item for item in catalog_items if item["type"] == "CATEGORY"]
    img_result = client.catalog.list_catalog(
    types = "IMAGE"
    )
    process(img_result)
    imgs = img_result.body["objects"]
    if request.method == "POST":
        shopping_cart = {}
        for item in items:
            quantity = int(request.form[item["id"]])    # How much of each item the user wants, based on form
            if quantity > 0:
                shopping_cart[item["item_data"]["variations"][0]["id"]] = request.form[item["id"]]  # Adds item to the cart
        shopping_cart["location_id"] = location_id
        encoded_order = urlencode(shopping_cart)    # Encodes shopping cart into URL
        return redirect(url_for("checkout", order_details=encoded_order))
    return render_template("catalog.html", title="Order", items=items, imgs=imgs, categories=categories)

@app.route("/_update_order_summary")
def _update_order_summary():
    # Dynamically updates the Order Summary on the side of the catalog page
    # Gets the id and quantity of each item
    quantities = request.args.get("quantities", "error", type=str)
    quantities = json.loads(quantities)
    summary_dict = {}
    for item_id in quantities["quantityDict"].keys():
        item_result = client.catalog.retrieve_catalog_object(
            object_id = item_id
        )
        process(item_result)
        item = item_result.body["object"]
        item_name = item["item_data"]["name"]
        item_quantity = float(quantities["quantityDict"][item_id])
        if item_quantity > 0:       # Multiplies cost by quantity & sends that data to the frontend
            item_price = item["item_data"]["variations"][0]["item_variation_data"]["price_money"]["amount"]
            total_cost_per_item = float(item_quantity) * (float(item_price) / 100)
            formatted_total_cost = str("${:,.2f}".format(total_cost_per_item))
            summary_dict[item_name] = formatted_total_cost
    return(jsonify(summary_dict))

@app.route("/checkout/<string:order_details>", methods=["GET", "POST"])
def checkout(order_details):
    details_dct = parse_qs(order_details)
    location_id = details_dct["location_id"][0]
    details_dct.pop("location_id", None)
    # Getting ready for the create order call by compiling line_items, taxes, etc.
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
    process(tax_result)
    for tax in tax_result.body["objects"]:
        taxes.append(
            {
                "catalog_object_id": tax["id"],
                "scope": "ORDER"
            }
        )
    compute_order_cost = client.orders.calculate_order(
        body = {
            "order": {
                "location_id": location_id,
                "line_items": line_items,
                "taxes": taxes
            }
        }
    )
    process(compute_order_cost)
    computed_order = compute_order_cost.body["order"]
    form = PersonalDetailsForm()    # Name and phone number
    if form.validate_on_submit():
        e_164_phone_number = "+1" + form.phone_number.data
        print(e_164_phone_number)
        customer_result = client.customers.search_customers(
            body = {
            }
        )
        process(customer_result)
        customer_id = "placeholder"
        if customer_result.body:
            for existing_customer in customer_result.body["customers"]:
                if existing_customer["phone_number"] == e_164_phone_number:
                    customer_id = existing_customer["id"]
                    print("Existing customer found!")
                    break
            if customer_id == "placeholder":        # If we don't match the phone # to an existing customer, we create a new one
                new_customer = client.customers.create_customer(
                    body = {
                        "given_name": form.name.data,
                        "phone_number": e_164_phone_number
                    }
                )
                customer_id = new_customer.body["customer"]["id"]
                print("New customer created!")
                print(customer_id)
        n = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=20)      #Order pickup time
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
                    "state": "OPEN"
                },
                "idempotency_key": str(uuid.uuid1())
            }
        )
        order_id = new_order.body["order"]["id"]
        customer_result = client.customers.retrieve_customer(
            customer_id = customer_id
        )
        process(customer_result)
        current_customer = customer_result.body["customer"]
        if "group_ids" in current_customer.keys():      # If current customer is part of a referral group, redirect them to their existing loyalty dashboard
            for group_id in current_customer["group_ids"]:
                group_result = client.customer_groups.retrieve_customer_group(
                    group_id = group_id
                )
                process(group_result)
                name_of_group = group_result.body["group"]["name"]
                if "Referral Group" in name_of_group:
                    print(f"You are in the {name_of_group}.")
            return(redirect(url_for("loyalty", order_id=order_id)))
        else:
            print("You aren't in any referral groups right now.")       # If not, redirect them to enter a referral code
            return(redirect(url_for("referrals", order_id=order_id)))
    return(render_template("checkout.html", title="Checkout", order=computed_order, form=form))

@app.route("/loyalty/<string:order_id>", methods=["GET", "POST"])
def loyalty(order_id):
    form = LoyaltyForm()
    order = get_order_by_id(order_id)
    loyalty_result = client.loyalty.retrieve_loyalty_program(
        program_id = "main"
    )
    if loyalty_result.is_success():
        loyalty_program = loyalty_result.body["program"]
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
    if form.validate_on_submit():
        print("Existing loyalty validated!")
        return(redirect(url_for("payment", order_id=order_id)))
    return(render_template("loyalty.html", title="Loyalty", order=order, form=form, points=points))

@app.route("/referrals/<string:order_id>", methods=["GET", "POST"])
def referrals(order_id):
    form = ReferralForm()
    order = get_order_by_id(order_id)
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
            process(verification_result)
            ambassador = verification_result.body["customers"][0]       # Finds the person who gave out the referral code
            for id in ambassador["group_ids"]:
                group_result = client.customer_groups.retrieve_customer_group(
                    group_id = id
                )
                process(group_result)
                group = group_result.body["group"]
                if referral_code in group["name"]:                      # Finds the correct referral group and adds the current customer to it
                    print(group["name"])
                    add_current_customer_to_group = client.customers.add_group_to_customer(
                        customer_id = order["customer_id"],
                        group_id = id
                    )
                    print(order["customer_id"])
                    print("Customer successfully added to group!")
                    ambassador_loyalty_result = client.loyalty.search_loyalty_accounts(
                      body = {
                        "query": {
                          "customer_ids": [
                            ambassador["id"]
                          ]
                        }
                      }
                    )
                    ambassador_loyalty_id = ambassador_loyalty_result.body["loyalty_accounts"][0]["id"]
                    referral_bonus_result = client.loyalty.adjust_loyalty_points(
                      account_id = ambassador_loyalty_id,
                      body = {
                        "idempotency_key": str(uuid.uuid1()),
                        "adjust_points": {
                          "points": 800,
                          "reason": "Referral bonus!"
                        }
                      }
                    )
                    break
            loyalty_result = client.loyalty.retrieve_loyalty_program(
                program_id = "main"
            )
            process(loyalty_result)
            loyalty_program = loyalty_result.body["program"]            # Finds the store's loyalty program and adds the customer to it
            print(loyalty_program["id"])
            customer_result = client.customers.retrieve_customer(
                customer_id = order["customer_id"]
            )
            process(customer_result)
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
            process(loyalty_add)
            print("Successfully added to loyalty program!")
            print("Referrals validated!")
            return(redirect(url_for("loyalty", order_id=order_id)))
        else:
            return(redirect(url_for("payment", order_id=order_id)))
    return(render_template("referrals.html", title="Referrals", order=order, form=form))

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
    process(verification_result)
    if not verification_result.body:
        data["result"] = "Sorry, this referral code code wasn't in the system. Please try again."
    else:
        referrer = verification_result.body["customers"][0]["given_name"]
        data["result"] = f"Congratulations, you've been successfully referred by {referrer}! {referrer} will receive a reward for inviting you."
    print(data)
    return jsonify(data)

@app.route("/payment/<string:order_id>")
def payment(order_id):
    order = get_order_by_id(order_id)
    return(render_template("payment.html", title="Payment", order=order, application_id=application_id, location_id=location_id))

@app.route("/payment_handler", methods=["GET", "POST"])
def payment_handler():
    content = request.get_json(silent=True)
    order = get_order_by_id(content["orderId"])
    new_payment = {
        "idempotency_key": str(uuid.uuid1()),
        "location_id": content["locationId"],
        "source_id": content["sourceId"],
        "order_id": content["orderId"],
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
            if loyalty_account_result.body:
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

def gather_referral_stats(referral_group):
    events_lst = []
    points = {}
    creation_datetime = dateutil.parser.isoparse(str(referral_group["created_at"]))
    customers_result = client.customers.search_customers(
      body = {
        "query": {
          "filter": {
            "group_ids": {
              "all": [
                referral_group["id"]
              ]
            }
          }
        }
      }
    )
    customers = customers_result.body["customers"]
    for customer in customers:
        loyalty_account_result = client.loyalty.search_loyalty_accounts(
            body = {
                "query": {
                    "customer_ids": [
                        customer["id"]
                    ]
                }
            }
        )
        loyalty_account = loyalty_account_result.body["loyalty_accounts"][0]
        loyalty_events_result = client.loyalty.search_loyalty_events(
          body = {
            "query": {
              "filter": {
                "loyalty_account_filter": {
                  "loyalty_account_id": loyalty_account["id"]
                }
              }
            }
          }
        )
        loyalty_events = loyalty_events_result.body["events"]
        for event in loyalty_events:
            time = dateutil.parser.isoparse(str(event["created_at"]))
            time = "{:%Y-%m-%d %H:%M}".format(time)
            print(time)
            if event["type"] == "ACCUMULATE_POINTS":
                events_lst.append(
                {time:
                [customer["given_name"],
                event["accumulate_points"]["points"],
                "Order"]
                })
                points[customer["given_name"]] = points.get(customer["given_name"], 0) + event["accumulate_points"]["points"]
            elif event["type"] == "ADJUST_POINTS":
                events_lst.append(
                {time:
                [customer["given_name"],
                event["adjust_points"]["points"],
                event["adjust_points"]["reason"]]
                })
                points[customer["given_name"]] = points.get(customer["given_name"], 0) + event["adjust_points"]["points"]
    return(events_lst, points)

@app.route("/dashboard")
def dashboard():
    customer_id = "TP92W688BRYSB0W87V1WBKJA50"
    customer_result = client.customers.retrieve_customer(
        customer_id = customer_id
    )
    process(customer_result)
    customer = customer_result.body["customer"]
    if "group_ids" in customer.keys():
        for group_id in customer["group_ids"]:
            group_result = client.customer_groups.retrieve_customer_group(
                group_id = group_id
            )
            if "Referral Group" in group_result.body["group"]["name"]:
                referral_group = group_result.body["group"]
                name_of_group = referral_group["name"]
                referral_code = name_of_group.split(" ")[0]
                ambassador_result = client.customers.search_customers(
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
                ambassador_name = ambassador_result.body["customers"][0]["given_name"]
                events, points = gather_referral_stats(referral_group)
                print(points)
                total_points = sum(points.values())
                percent = (total_points / 20000) * 100
            else:
                ambassador_name=""
    else:
        ambassador_name=""
    return render_template("dashboard.html", title="Dashboard",
    ambassador_name=ambassador_name, referral_code=referral_code,
    events=events, percent=percent)

if __name__ == '__main__':
    app.run(debug=True)
