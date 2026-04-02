import boto3
import os
import re
import zipfile
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
FUNCTION_NAME = "GraphQL-FastAPI"
REGION = os.getenv("AWS_REGION", "us-east-1")
ROLE_ARN = os.getenv("AWS_LAMBDA_ROLE_ARN")
API_GATEWAY_ARN = os.getenv("API_GATEWAY_ARN", "")
ZIP_PATH = "./deployment.zip"
HANDLER = "main.handler"
RUNTIME = "python3.10"
TIMEOUT = 30
MEMORY = 512
ENV_VARS = {
    "MONGODB_URI": os.getenv("MONGODB_URI", "")
}

lambda_client = boto3.client("lambda", region_name=REGION)
apigw_client = boto3.client("apigateway", region_name=REGION)


def build_zip():
    package_dir = os.path.join(os.path.dirname(__file__), "package")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(package_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, package_dir)
                zf.write(full_path, arcname)
    print(f"Built {ZIP_PATH} from package/")


def create_or_update():
    with open(ZIP_PATH, "rb") as f:
        zip_bytes = f.read()

    # Check if function already exists
    try:
        lambda_client.get_function(FunctionName=FUNCTION_NAME)
        function_exists = True
    except lambda_client.exceptions.ResourceNotFoundException:
        function_exists = False

    if function_exists:
        print(f"Updating existing function: {FUNCTION_NAME}")

        lambda_client.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=zip_bytes,
        )

        # Wait for code update to complete before updating config
        waiter = lambda_client.get_waiter("function_updated")
        waiter.wait(FunctionName=FUNCTION_NAME)

        lambda_client.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Handler=HANDLER,
            Runtime=RUNTIME,
            Timeout=TIMEOUT,
            MemorySize=MEMORY,
            Environment={"Variables": ENV_VARS},
        )

        print("Function updated successfully.")

    else:
        print(f"Creating new function: {FUNCTION_NAME}")

        response = lambda_client.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime=RUNTIME,
            Role=ROLE_ARN,
            Handler=HANDLER,
            Code={"ZipFile": zip_bytes},
            Timeout=TIMEOUT,
            MemorySize=MEMORY,
            Environment={"Variables": ENV_VARS},
        )

        print(f"Function created: {response['FunctionArn']}")

    lambda_arn = lambda_client.get_function(FunctionName=FUNCTION_NAME)["Configuration"]["FunctionArn"]

    # Create or reuse API Gateway
    new_api_gateway_arn = ensure_api_gateway(lambda_arn)

    # Update .env with the new ARN
    update_env_file("API_GATEWAY_ARN", new_api_gateway_arn)

    # Remove stale permission then re-add with correct ARN
    try:
        lambda_client.remove_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="api-gateway-invoke",
        )
        print("Removed old API Gateway invoke permission.")
    except lambda_client.exceptions.ResourceNotFoundException:
        pass

    lambda_client.add_permission(
        FunctionName=FUNCTION_NAME,
        StatementId="api-gateway-invoke",
        Action="lambda:InvokeFunction",
        Principal="apigateway.amazonaws.com",
        SourceArn=new_api_gateway_arn,
    )
    print("API Gateway invoke permission added.")


def ensure_api_gateway(lambda_arn: str) -> str:
    """Find an existing REST API for this Lambda or create a new one. Returns the source ARN."""
    account_id = lambda_arn.split(":")[4]

    # Try to find an existing REST API named after the function
    try:
        apis = apigw_client.get_rest_apis().get("items", [])
        for api in apis:
            if api.get("name") == FUNCTION_NAME:
                api_id = api["id"]
                print(f"Found existing REST API Gateway: {api_id}")
                return f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/*/GraphQL-FastAPI*"
    except Exception as e:
        print(f"Could not list REST APIs: {e}")

    # Create a new REST API
    print("Creating new REST API Gateway...")
    api_resp = apigw_client.create_rest_api(
        name=FUNCTION_NAME,
        endpointConfiguration={"types": ["REGIONAL"]},
    )
    api_id = api_resp["id"]

    # Get root resource id
    resources = apigw_client.get_resources(restApiId=api_id)["items"]
    root_id = next(r["id"] for r in resources if r["path"] == "/")

    # Create /{proxy+} resource
    proxy_resource = apigw_client.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="{proxy+}",
    )
    proxy_id = proxy_resource["id"]

    # Create ANY method on /{proxy+}
    apigw_client.put_method(
        restApiId=api_id,
        resourceId=proxy_id,
        httpMethod="ANY",
        authorizationType="NONE",
    )

    # Integrate with Lambda
    apigw_client.put_integration(
        restApiId=api_id,
        resourceId=proxy_id,
        httpMethod="ANY",
        type="AWS_PROXY",
        integrationHttpMethod="POST",
        uri=f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations",
    )

    # Deploy to 'default' stage (matches api_gateway_base_path in package/main.py)
    apigw_client.create_deployment(
        restApiId=api_id,
        stageName="default",
    )

    endpoint = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/default/{FUNCTION_NAME}/graphql"
    print(f"REST API Gateway created: {api_id}")
    print(f"Endpoint: {endpoint}")
    return f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/*/GraphQL-FastAPI*"


def update_env_file(key: str, value: str):
    """Update or insert a key in the .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            content = f.read()
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
        else:
            content += f"\n{key}={value}\n"
        with open(env_path, "w") as f:
            f.write(content)
        print(f".env updated: {key}={value}")


if __name__ == "__main__":
    if not ROLE_ARN:
        raise ValueError("AWS_LAMBDA_ROLE_ARN is not set in your .env file")
    build_zip()
    create_or_update()
        raise ValueError("AWS_LAMBDA_ROLE_ARN is not set in your .env file")
    create_or_update()
