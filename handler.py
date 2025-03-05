import json
import os
import boto3
import uuid
# import stripe
from datetime import datetime

# stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
dynamodb = boto3.resource("dynamodb")
affiliate_orders_table = dynamodb.Table(os.getenv("AFFILIATE_ORDERS_TABLE"))
affiliate_table = dynamodb.Table(os.getenv("AFFILIATE_TABLE"))
tenant_settings_table = dynamodb.Table(os.getenv("TENANT_SETTINGS_TABLE"))

def webhook_handler(event, context):
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    order_id = body.get("data", {}).get("id")
    affiliate_id = body.get("data", {}).get("meta", {}).get("affiliateId")

    if not tenant_id or not affiliate_id:
        return {"statusCode": 400, "body": json.dumps({"error": "tenantId and affiliateId are required"})}

    affiliate_orders_table.put_item(
        Item={
            "tenantId": tenant_id,
            "orderId": order_id,
            "affiliateId": affiliate_id,
            "amount": body["data"]["total"],
            "status": body["data"]["status"],
            "createdAt": body["data"]["createdAt"],
        }
    )
    return {"statusCode": 200, "body": json.dumps({"message": "Order processed"})}

def create_affiliate(event, context):
    """
    Creates a new affiliate if one does not exist for the given customerId.
    If an affiliate already exists, it returns the existing record instead.
    """
    body = json.loads(event["body"])
    tenant_id = body.get("tenantId")
    customer_id = body.get("customerId")  # Commerce7 Customer ID
    name = body.get("name")

    if not tenant_id or not customer_id or not name:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "tenantId, customerId, and name are required"}),
            "headers": {"Content-Type": "application/json"}
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
                "body": json.dumps(existing_affiliates[0]),  # Return the first found affiliate
                "headers": {"Content-Type": "application/json"}
            }

        # 🆕 No existing affiliate found, proceed with creation
        affiliate_id = f"AFF{uuid.uuid4().hex[:10].upper()}"
        created_at = body.get("createdAt", datetime.utcnow().isoformat())

        new_affiliate = {
            "tenantId": tenant_id,
            "affiliateId": affiliate_id,
            "customerId": customer_id,
            "name": name,
            "status": "Active",  # ✅ New field for status
            "createdAt": created_at
        }

        # Save new affiliate to DynamoDB
        affiliate_table.put_item(Item=new_affiliate)

        return {
            "statusCode": 201,
            "body": json.dumps(new_affiliate),  # Return the newly created item
            "headers": {"Content-Type": "application/json"}
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed to create affiliate: {str(e)}"}),
            "headers": {"Content-Type": "application/json"}
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
        return {"statusCode": 400, "body": json.dumps({"error": "tenantId is required"})}

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
            "body": json.dumps(affiliates),
            "headers": {"Content-Type": "application/json"}
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"}
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
            "body": json.dumps({"error": "tenantId and affiliateId are required"}),
            "headers": {"Content-Type": "application/json"}
        }

    # ✅ Fetch the base URL for the tenant
    response = tenant_settings_table.get_item(Key={"tenantId": tenant_id})
    tenant_settings = response.get("Item")

    if not tenant_settings or "baseUrl" not in tenant_settings:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": f"Base URL not found for tenantId: {tenant_id}"}),
            "headers": {"Content-Type": "application/json"}
        }

    base_url = tenant_settings["baseUrl"]

    # ✅ Construct the tracking link using `affiliateId`
    tracking_link = f"{base_url}?ref={affiliate_id}"

    return {
        "statusCode": 200,
        "body": json.dumps({"trackingLink": tracking_link}),
        "headers": {"Content-Type": "application/json"}
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
            "body": json.dumps({"error": "tenantId, affiliateId, and status are required"}),
            "headers": {"Content-Type": "application/json"}
        }

    # ✅ Check if the affiliate exists
    response = affiliate_table.get_item(Key={"tenantId": tenant_id, "affiliateId": affiliate_id})

    if "Item" not in response:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Affiliate not found"}),
            "headers": {"Content-Type": "application/json"}
        }

    # ✅ Update the status if the affiliate exists
    affiliate_table.update_item(
        Key={"tenantId": tenant_id, "affiliateId": affiliate_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status}
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"message": f"Affiliate status updated to {status}"}),
        "headers": {"Content-Type": "application/json"}
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
            "body": json.dumps({"error": "tenantId and baseUrl are required"}),
            "headers": {"Content-Type": "application/json"}
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
                "body": json.dumps({"message": f"Base URL updated for {tenant_id}"}),
                "headers": {"Content-Type": "application/json"}
            }
        else:
            return {
                "statusCode": 200,
                "body": json.dumps({"message": f"Base URL for {tenant_id} is already up to date."}),
                "headers": {"Content-Type": "application/json"}
            }

    # ✅ If no record exists, create a new one
    tenant_settings_table.put_item(Item={"tenantId": tenant_id, "baseUrl": new_base_url})

    return {
        "statusCode": 201,
        "body": json.dumps({"message": f"Base URL set for {tenant_id}"}),
        "headers": {"Content-Type": "application/json"}
    }
