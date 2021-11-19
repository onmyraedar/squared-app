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

result = client.merchants.list_merchants()

if result.is_success():
  print(result.body)
elif result.is_error():
  print(result.errors)

@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html", title="Home")

@app.route("/stores")
def stores():
    return render_template("stores.html", title="Stores")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")

if __name__ == '__main__':
    app.run(debug=True)
