import json
import os
import boto3
import requests
import decimal
from botocore.exceptions import BotoCoreError, ClientError

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
commission_table = os.environ.get("COMMISSION_TABLE")
c7_api_base = "https://api.commerce7.com/v1/product"
c7_api_key = os.environ.get("C7_API_KEY")  # Ensure API Key is stored securely

headers = lambda tenant_id: {
    "Authorization": f"Bearer {c7_api_key}",
    "tenant": tenant_id,  # ✅ Add tenantId here
    "Content-Type": "application/json"
}

# 1. Save tenant's commission program selection
def save_commission_program(event, context):
    """Save or update a tenant's commission program settings"""
    try:
        body = json.loads(event["body"])
        tenant_id = body.get("tenantId")
        commission_type = body.get("commissionType")  # 'default' or 'per_product'
        default_rate = convert_to_decimal(body.get("defaultRate", 0))

        if not tenant_id or not commission_type:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing required fields"})}

        table = dynamodb.Table(commission_table)

        # Check if commission settings already exist
        existing_item = table.get_item(Key={"tenantId": tenant_id, "id": "commission_program"})
        if "Item" in existing_item:
            current_commission_type = existing_item["Item"].get("commissionType")
            current_default_rate = existing_item["Item"].get("defaultRate", 0)
            
            # Update only if the commissionType or defaultRate has changed
            if current_commission_type != commission_type or current_default_rate != default_rate:
                table.update_item(
                    Key={"tenantId": tenant_id, "id": "commission_program"},
                    UpdateExpression="SET commissionType = :c, defaultRate = :r",
                    ExpressionAttributeValues={":c": commission_type, ":r": default_rate}
                )
                return {"statusCode": 200, "body": json.dumps({"message": "Commission program updated successfully!"})}
            else:
                return {"statusCode": 200, "body": json.dumps({"message": "No changes detected in commission program."})}
        
        # If no existing commission settings, create a new one
        item = {
            "tenantId": tenant_id,
            "id": "commission_program",
            "commissionType": commission_type,
            "defaultRate": default_rate
        }
        table.put_item(Item=item)

        return {"statusCode": 200, "body": json.dumps({"message": "Commission program saved successfully!"})}
    except (BotoCoreError, ClientError) as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# 2. Retrieve existing commission program
def get_commission_program(event, context):
    """Retrieve a tenant's commission program settings"""
    try:
        tenant_id = event.get("queryStringParameters", {}).get("tenantId")

        if not tenant_id:
            return {"statusCode": 400, "body": json.dumps({"error": "tenantId is required"})}

        table = dynamodb.Table(commission_table)
        response = table.get_item(Key={"tenantId": tenant_id, "id": "commission_program"})

        if "Item" not in response:
            return {"statusCode": 404, "body": json.dumps({"error": "No commission program found for this tenant"})}

        return {"statusCode": 200, "body": json.dumps(response["Item"], default=decimal_default)}
    
    except (BotoCoreError, ClientError) as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# 3. Retrieve all products from Commerce7 using pagination
def get_products(event, context):
    """Retrieve all products from Commerce7 using cursor-based pagination"""
    try:
        tenant_id = event["queryStringParameters"].get("tenantId")
        if not tenant_id:
            return {"statusCode": 400, "body": json.dumps({"error": "tenantId is required"})}

        products = []
        cursor = "start"

        while cursor:
            requestUrl = f"{c7_api_base}?adminStatus=Available&cursor={cursor}"
            print(requestUrl)
            response = requests.get(
                requestUrl, 
                headers=headers(tenant_id)
            )
            if response.status_code != 200:
                return {"statusCode": response.status_code, "body": json.dumps(response.json())}

            data = response.json()
            products.extend(data.get("products", []))

            # Get next cursor or stop if no more pages
            cursor = data.get("cursor", None)  # Fix: Get correct cursor

        return {"statusCode": 200, "body": json.dumps({"products": products})}
    
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# 4. Search for products with type-ahead functionality
def search_products(event, context):
    """Search for specific products in Commerce7 using type-ahead functionality"""
    try:
        params = event.get("queryStringParameters", {})
        tenant_id = params.get("tenantId")
        search_query = params.get("query", "").strip()

        if not tenant_id or not search_query:
            return {"statusCode": 400, "body": json.dumps({"error": "tenantId and query are required"})}

        # Make request to Commerce7 API
        response = requests.get(
            f"{c7_api_base}?q={search_query}", 
            headers=headers(tenant_id)
        )
        if response.status_code != 200:
            return {"statusCode": response.status_code, "body": json.dumps(response.json())}

        data = response.json()
        return {"statusCode": 200, "body": json.dumps({"products": data.get("products", [])})}
    
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# 5. Save commission rate for a product using Commerce7 Custom Fields
def save_product_commission(event, context):
    try:
        body = json.loads(event["body"])
        tenant_id = body.get("tenantId")
        product_id = body.get("productId")
        commission_type = body.get("commissionType")  # 'percentage' or 'fixed'
        commission_value = body.get("commissionValue")

        if not tenant_id or not product_id or not commission_type or commission_value is None:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing required fields"})}

        payload = {
            "customFields": {
                "commissionType": commission_type,
                "commissionValue": commission_value
            }
        }

        response = requests.put(
            f"{c7_api_base}/{product_id}", 
            headers=headers(tenant_id), 
            json=payload
        )
        if response.status_code != 200:
            return {"statusCode": response.status_code, "body": json.dumps(response.json())}

        return {"statusCode": 200, "body": json.dumps({"message": "Commission settings updated successfully!"})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# helper function
def decimal_default(obj):
    """Convert Decimal to int or float for JSON serialization"""
    if isinstance(obj, decimal.Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def convert_to_decimal(value):
    """Convert float values to Decimal for DynamoDB"""
    if isinstance(value, float):
        return decimal.Decimal(str(value))  # Convert float to Decimal
    return value