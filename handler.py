import json
import os
import boto3
import uuid
import requests
from decimal import Decimal
# import stripe
from datetime import datetime

# stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
dynamodb = boto3.resource("dynamodb")
affiliate_orders_table = dynamodb.Table(os.getenv("AFFILIATE_ORDERS_TABLE"))
affiliate_table = dynamodb.Table(os.getenv("AFFILIATE_TABLE"))
tenant_settings_table = dynamodb.Table(os.getenv("TENANT_SETTINGS_TABLE"))

# Commerce7 API Base URL
C7_API_BASE = "https://api.commerce7.com/v1/customer"
C7_API_KEY = os.getenv("C7_API_KEY")  # Ensure API Key is stored securely

def webhook_handler(event, context):
    """
    Handles Commerce7 webhook requests.
    Extracts order details, including affiliateId from appData, and stores valid orders in DynamoDB.
    """
    try:
        # ✅ Ensure `body` exists and is valid JSON
        if "body" not in event or not event["body"]:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"error": "Missing request body"})
            }

        body = json.loads(event["body"])

        # ✅ Validate required top-level fields
        if not isinstance(body, dict):
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"error": "Invalid request format"})
            }

        tenant_id = body.get("tenantId", None)
        user_email = body.get("user", "Unknown")  # Logging/debugging purposes

        # ✅ Extract payload safely
        payload = body.get("payload", None)
        if not payload or not isinstance(payload, dict):
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"error": "Missing or invalid payload"})
            }

        # ✅ Extract order details safely
        order_id = payload.get("id", None)
        order_number = payload.get("orderNumber", None)
        order_paid_date = payload.get("orderPaidDate", None)
        total = payload.get("totalAfterTip", 0)
        status = payload.get("paymentStatus", "Unknown")
        created_at = payload.get("createdAt", None)

        # ✅ Extract customer data safely
        customer_id = payload.get("customerId", None)
        customer_data = payload.get("customer", {})
        customer_name = f"{customer_data.get('firstName', '')} {customer_data.get('lastName', '')}".strip()

        # ✅ Extract affiliateId safely from `appData`
        app_data = payload.get("appData", {}) or {}  # Ensure appData is a dictionary
        affiliate_data = app_data.get("affiliate-marketing", {}) or {}
        affiliate_id = affiliate_data.get("affiliateId", None)

        # ✅ Validate required fields
        if not tenant_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"error": "Missing tenantId"})
            }

        if not order_id or not customer_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"error": "Missing orderId or customerId"})
            }

        # ✅ Only process orders with an affiliateId
        if not affiliate_id:
            print(f"⚠️ Order {order_id} has no affiliate associated. Skipping storage.")
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"message": "Order does not belong to an affiliate."})
            }

        # ✅ Prepare order data for DynamoDB
        order_item = {
            "tenantId": tenant_id,
            "orderId": order_id,
            "orderNumber": order_number,
            "customerId": customer_id,
            "customerName": customer_name,
            "affiliateId": affiliate_id,
            "amount": total,
            "status": status,
            "createdAt": created_at,
            "processedBy": user_email
        }

        # ✅ Store the order in DynamoDB
        affiliate_orders_table.put_item(Item=order_item)

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"message": "Order processed successfully"})
        }

    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "Invalid JSON format in request body"})
        }

    except Exception as e:
        print(f"❌ Error processing webhook: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": f"Webhook processing failed: {str(e)}"})
        }

def get_affiliate_orders(event, context):
    """
    Retrieves all orders for a given affiliate.
    Expects `tenantId` and `affiliateId` as query parameters.
    """
    try:
        # ✅ Extract query parameters safely
        params = event.get("queryStringParameters", {}) or {}

        tenant_id = params.get("tenantId", None)
        affiliate_id = params.get("affiliateId", None)

        # ✅ Validate required fields
        if not tenant_id or not affiliate_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"error": "Missing tenantId or affiliateId"})
            }

        # ✅ Query the new GSI (`TenantAffiliateIndex`)
        response = affiliate_orders_table.query(
            IndexName="TenantAffiliateIndex",  # ✅ Use GSI instead of primary index
            KeyConditionExpression="tenantId = :t AND affiliateId = :a",
            ExpressionAttributeValues={
                ":t": tenant_id,
                ":a": affiliate_id
            }
        )

        # Convert Decimal values to JSON-friendly types
        orders = convert_decimal(response.get("Items", []))

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps(orders)
        }

    except Exception as e:
        print(f"❌ Error retrieving affiliate orders: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": f"Failed to retrieve affiliate orders: {str(e)}"})
        }

def create_affiliate(event, context):
    """
    Creates a new affiliate if one does not exist for the given customerId.
    If an affiliate already exists, it returns the existing record instead.
    Also updates Commerce7 customer's `appData` with the `affiliateId`.
    """
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    customer_id = body.get("customerId")  # Commerce7 Customer ID
    name = body.get("name")

    if not tenant_id or not customer_id or not name:
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "tenantId, customerId, and name are required"})
        }

    try:
        # 🔍 Check if an affiliate already exists for this customerId
        response = affiliate_table.query(
            IndexName="CustomerIdIndex",
            KeyConditionExpression="customerId = :c AND tenantId = :t",
            ExpressionAttributeValues={
                ":c": customer_id,
                ":t": tenant_id
            }
        )
        
        existing_affiliates = response.get("Items", [])

        if existing_affiliates:
            # ✅ Affiliate already exists, return the existing record
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps(existing_affiliates[0])  # Return the first found affiliate
            }

        # 🆕 No existing affiliate found, proceed with creation
        affiliate_id = f"AFF{uuid.uuid4().hex[:10].upper()}"
        created_at = body.get("createdAt", datetime.utcnow().isoformat())
        affiliate_status = "Active"

        new_affiliate = {
            "tenantId": tenant_id,
            "affiliateId": affiliate_id,
            "customerId": customer_id,
            "name": name,
            "status": affiliate_status,  # ✅ New field for status
            "createdAt": created_at
        }

        # Save new affiliate to DynamoDB
        affiliate_table.put_item(Item=new_affiliate)

        # ✅ Update Commerce7 Customer's `appData`
        commerce7_update_success = update_commerce7_customer(tenant_id, customer_id, affiliate_id, affiliate_status)

        if not commerce7_update_success:
            # Rollback: Remove the affiliate from DynamoDB
            affiliate_table.delete_item(
                Key={"tenantId": tenant_id, "affiliateId": affiliate_id}
            )
            
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({
                    "error": "Affiliate created, but failed to update Commerce7 customer"
                })
            }

        return {
            "statusCode": 201,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps(new_affiliate)  # Return the newly created item
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": f"Failed to create affiliate: {str(e)}"})
        }

def get_affiliates(event, context):
    """
    Retrieves affiliates based on `tenantId`, optionally filtered by `customerId` and/or `status`.
    """
    print(event)
    params = event.get("queryStringParameters", {}) or {}

    tenant_id = params.get("tenantId")
    customer_id = params.get("customerId")  # Optional
    status_filter = params.get("status")  # Optional

    if not tenant_id:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "tenantId is required"})
        }

    try:
        # ✅ Query with CustomerId if provided
        if customer_id:
            response = affiliate_table.query(
                IndexName="CustomerIdIndex",
                KeyConditionExpression="customerId = :c AND tenantId = :t",
                ExpressionAttributeValues={
                    ":c": customer_id,
                    ":t": tenant_id
                }
            )
        else:
            response = affiliate_table.query(
                KeyConditionExpression="tenantId = :t",
                ExpressionAttributeValues={":t": tenant_id}
            )

        affiliates = response.get("Items", [])

        # ✅ Apply status filter if provided
        if status_filter:
            affiliates = [a for a in affiliates if a.get("status") == status_filter]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps(affiliates)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": str(e)})
        }

def delete_affiliate(event, context):
    """
    Instead of deleting the affiliate, this function updates the `status` field to `Deleted`.
    """
    params = event.get("queryStringParameters", {})
    tenant_id = params.get("tenantId")
    affiliate_id = event["pathParameters"]["id"]

    if not tenant_id or not affiliate_id:
        return {"statusCode": 400, "body": json.dumps({"error": "tenantId and affiliateId are required"})}

    try:
        # Check if the affiliate exists
        response = affiliate_table.get_item(
            Key={"tenantId": tenant_id, "affiliateId": affiliate_id}
        )

        if "Item" not in response:
            return {"statusCode": 404, "body": json.dumps({"error": "Affiliate not found"})}

        # ✅ Instead of deleting, set status to "Deleted"
        affiliate_table.update_item(
            Key={"tenantId": tenant_id, "affiliateId": affiliate_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "Deleted"}
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"message": "Affiliate marked as Deleted"})
        }
    
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def process_payout(event, context):
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    affiliate_id = body.get("affiliateId")
    amount = int(body.get("amount") * 100)  # Convert to cents
    stripe_account_id = body.get("stripeAccountId")
    
    return {"statusCode": 200, "body": json.dumps({"message": "Payout successful", "payoutId": 1})}

    # if not tenant_id or not affiliate_id:
    #     return {"statusCode": 400, "body": json.dumps({"error": "tenantId and affiliateId are required"})}

    # try:
    #     payout = stripe.Transfer.create(
    #         amount=amount,
    #         currency="usd",
    #         destination=stripe_account_id
    #     )
    #     return {"statusCode": 200, "body": json.dumps({"message": "Payout successful", "payoutId": payout.id})}
    # except stripe.error.StripeError as e:
    #     return {"statusCode": 400, "body": json.dumps({"error": str(e)})}

def generate_affiliate_link(event, context):
    """
    Generates an affiliate tracking link using the tenant's base URL and affiliateId.
    """
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    affiliate_id = body.get("affiliateId")

    if not tenant_id or not affiliate_id:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "tenantId and affiliateId are required"})
        }

    # ✅ Fetch the base URL for the tenant
    response = tenant_settings_table.get_item(Key={"tenantId": tenant_id})
    tenant_settings = response.get("Item")

    if not tenant_settings or "baseUrl" not in tenant_settings:
        return {
            "statusCode": 404,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": f"Base URL not found for tenantId: {tenant_id}"})
        }

    base_url = tenant_settings["baseUrl"]

    # ✅ Construct the tracking link using `affiliateId`
    tracking_link = f"{base_url}?ref={affiliate_id}"

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
        },
        "body": json.dumps({"trackingLink": tracking_link})
    }

def update_affiliate_status(event, context):
    """
    Updates the status of an affiliate after checking if the affiliate exists.
    """
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    affiliate_id = body.get("affiliateId")
    status = body.get("status")  # "Active", "Inactive", "Deleted"

    if not tenant_id or not affiliate_id or not status:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "tenantId, affiliateId, and status are required"})
        }

    # ✅ Check if the affiliate exists
    response = affiliate_table.get_item(Key={"tenantId": tenant_id, "affiliateId": affiliate_id})

    if "Item" not in response:
        return {
            "statusCode": 404,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "Affiliate not found"})
        }
    
    affiliate = response.get("Item")
    oldStatus = affiliate.get("status")
    customer_id = affiliate.get("customerId")

    # ✅ Update the status if the affiliate exists
    affiliate_table.update_item(
        Key={"tenantId": tenant_id, "affiliateId": affiliate_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status}
    )

    # ✅ Update Commerce7 Customer's `appData`
    commerce7_update_success = update_commerce7_customer(tenant_id, customer_id, affiliate_id, status)
    if not commerce7_update_success:
        # Rollback: Remove the affiliate from DynamoDB
        affiliate_table.update_item(
            Key={"tenantId": tenant_id, "affiliateId": affiliate_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": oldStatus}
        )
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({
                "error": "Affiliate updated, but failed to update Commerce7 customer"
            })
        }

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
        },
        "body": json.dumps({"message": f"Affiliate status updated to {status}"})
    }

def set_tenant_base_url(event, context):
    """
    Stores or updates a tenant's base URL in the TenantSettings table.
    """
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    new_base_url = body.get("baseUrl")

    if not tenant_id or not new_base_url:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
            },
            "body": json.dumps({"error": "tenantId and baseUrl are required"})
        }

    # ✅ Retrieve existing record for the tenant
    response = tenant_settings_table.get_item(Key={"tenantId": tenant_id})
    existing_entry = response.get("Item")

    if existing_entry:
        existing_base_url = existing_entry.get("baseUrl")
        
        # ✅ If the baseUrl has changed, update it
        if existing_base_url != new_base_url:
            tenant_settings_table.update_item(
                Key={"tenantId": tenant_id},
                UpdateExpression="SET baseUrl = :b",
                ExpressionAttributeValues={":b": new_base_url}
            )
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"message": f"Base URL updated for {tenant_id}"})
            }
        else:
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
                },
                "body": json.dumps({"message": f"Base URL for {tenant_id} is already up to date."})
            }

    # ✅ If no record exists, create a new one
    tenant_settings_table.put_item(Item={"tenantId": tenant_id, "baseUrl": new_base_url})

    return {
        "statusCode": 201,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE"
        },
        "body": json.dumps({"message": f"Base URL set for {tenant_id}"})
    }

# Headers for Commerce7 API Requests
def c7_headers(tenant_id):
    return {
        "Authorization": f"Basic {C7_API_KEY}",
        "tenant": tenant_id,
        "Content-Type": "application/json",
        "Accept": "application/atom+xml"
    }
    
def update_commerce7_customer(tenant_id, customer_id, affiliate_id, affiliate_status):
    """
    Updates the Commerce7 customer's `appData` to include the new `affiliateId`.
    """
    try:
        url = f"{C7_API_BASE}/{customer_id}"
        
        payload = {
            "appData": {
                "affiliateId": affiliate_id,
                "affiliateStatus": affiliate_status
            }
        }
        
        response = requests.put(url, headers=c7_headers(tenant_id), json=payload)

        if response.status_code == 200:
            return True  # ✅ Successfully updated customer
        else:
            print(f"⚠️ Failed to update Commerce7 customer: {response.text}")
            return False

    except requests.RequestException as e:
        print(f"⚠️ Exception updating Commerce7 customer: {str(e)}")
        return False
    
# Helper function to convert DynamoDB Decimals to standard Python types
def convert_decimal(obj):
    """Recursively converts DynamoDB Decimal values to int or float for JSON serialization."""
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)  # Convert to int if whole number, else float
    return obj
