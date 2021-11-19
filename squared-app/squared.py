import os

from dotenv import load_dotenv
from square.client import Client

load_dotenv()       # Takes environment variables from .env

access_token = os.getenv("SQUARE_ACCESS_TOKEN")
environment = os.getenv("SQ_ENVIRONMENT")

client = Client(
    access_token=access_token,
    environment=environment
)

result = client.customers.list_customers()

if result.is_success():
  print(result.body)
elif result.is_error():
  print(result.errors)
