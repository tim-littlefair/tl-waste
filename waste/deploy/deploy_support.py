import boto3
import json
import zipfile
import tarfile
import os
import json
import subprocess
import botocore.exceptions
import botocore
import sys
import traceback
import base64
import time
import mimetypes
import logging
import copy

_logger = logging.getLogger()
#_handler = logging.StreamHandler(sys.stderr)
#_handler.setFormatter(logging.Formatter())
#_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

_APIGW_LOG_FORMAT_JSON = """{
    "requestId":"$context.requestId",
    "ip": "$context.identity.sourceIp",
    "requestTime":"$context.requestTime",
    "httpMethod":"$context.httpMethod",
    "routeKey":"$context.routeKey",
    "status":"$context.status",
    "protocol":"$context.protocol",
    "responseLength":"$context.responseLength",
    "integrationError":"$context.integration.error",
    "errorMessage":"$context.error.message"
}""".replace("\n"," ")

TEST_EVENT_FOR_AUTHFN = {
    "event": "abc",
    "context": "xyz"
}

TEST_EVENT_FOR_HANDLER = {
    "requestContext": {
        "http": { "method": "GET", "path": "" }
    },
    "body": ""
}

from .kit_abstract_factory import create_factory_for_kit

#TODO: Find a way of making a single definition span here and the handler
ENVVAR_DEFAULT_DOCUMENT_NAME = "WASTE_DEFAULT_DOCUMENT_NAME"
ENVVAR_CONTENT_BUCKET_NAME = "WASTE_CONTENT_BUCKET_NAME"
ENVVAR_CACHE_OBJECT_NAME = "WASTE_CACHE_OBJECT_NAME"

_factory = create_factory_for_kit()


iam_client = _factory.get_client('iam')
s3_client = _factory.get_client('s3')
lambda_client = _factory.get_client('lambda')
apiv2_client = _factory.get_client('apigatewayv2')
logs_client = _factory.get_client('logs')
region_name = _factory.get_region_name()

lambda_url = None

app_name_matches = (
    lambda app_name, resource_name: 
        app_name is None or resource_name.startswith(app_name)
)

_get_response_status_code = lambda x: x["ResponseMetadata"]["HTTPStatusCode"]

# Logic to build a .zip file for lambda and upload it is copied from
# https://codeburst.io/aws-lambda-functions-made-easy-1fae0feeab27
def create_function(
    app_baseline_name='waste', 
    default_doc_name=None, 
    cache_zip_path=None,
    do_test_invocation=True 
):
    retval = {}
    _lambda_zip_name = app_baseline_name + ".zip"
    lambda_zip = zipfile.ZipFile(_lambda_zip_name, mode='w')
    for d in ("../handler","./handler","./waste/handler"):
        basedir = os.path.split(d)[1]
        try:
            for f in os.listdir(d):
                lambda_zip.write(
                    os.path.join(d,f),
                    arcname=os.path.join(basedir,f)
                )
        except FileNotFoundError:
            pass
    lambda_zip.close()
    _LAMBDA_ROLE_NAME = "LambdaBasicExecution"
    # For the moment, a hand-created role is in use
    role_arn = _factory.get_arn("arn:aws:iam","role/"+_LAMBDA_ROLE_NAME,include_region=False)
    which_handler = 'handler.simple_lambda_handler.lambda_handler'
    fn_env_vars = { ENVVAR_CONTENT_BUCKET_NAME: app_baseline_name }
    if default_doc_name is not None:
        fn_env_vars[ENVVAR_DEFAULT_DOCUMENT_NAME] = default_doc_name
    if cache_zip_path is not None:
        fn_env_vars[ENVVAR_CACHE_OBJECT_NAME] = cache_zip_path
        which_handler = 'handler.caching_lambda_handler.lambda_handler'
    create_fn_response = lambda_client.create_function(
        FunctionName=app_baseline_name,
        Runtime='python3.8',
        Role=role_arn,
        Handler=which_handler,
        Code=dict(ZipFile=open(_lambda_zip_name,"rb").read()),
        Timeout=120, 
        Environment={ "Variables" : fn_env_vars },
        MemorySize=256,
    )
    create_authfn_response = lambda_client.create_function(
        FunctionName=app_baseline_name+'_authfn',
        Runtime='python3.8',
        Role=role_arn,
        Handler='handler.authorizer.lambda_handler',
        Code=dict(ZipFile=open(_lambda_zip_name,"rb").read()),
        Timeout=120, 
        Environment={ "Variables" : fn_env_vars },
        MemorySize=256,
    )
    os.unlink(_lambda_zip_name)

    # At the moment, test invocation is mandatory because we are 
    # choosing for the API gateway to log to the same CloudWatch
    # log group - if the test invocation does not run the log group
    # is not created and the API gateway steps fail.
    logging.info("Starting lambda test invocation")
    test_auth_response = lambda_client.invoke(
        FunctionName=app_baseline_name + "_authfn",
        LogType='Tail',
        Payload=json.dumps(TEST_EVENT_FOR_AUTHFN)
    )
    test_invocation_response = lambda_client.invoke(
        FunctionName=app_baseline_name,
        LogType='Tail',
        Payload=json.dumps(TEST_EVENT_FOR_HANDLER)
    )
    logging.info("Finished lambda test invocation")
    for _ in range(0,10): #pragma: no branch
        loggroupName = '/aws/lambda/'+app_baseline_name
        logging.info("Waiting for AWS to create log group " + loggroupName)
        desc_logs_response = logs_client.describe_log_groups(
            logGroupNamePrefix=loggroupName
        )
        if len(desc_logs_response['logGroups'])>0:
            retval["loggroup_arn"] = desc_logs_response['logGroups'][0]['arn']
            break
        time.sleep(1)
    return retval

def create_bucket(app_bucket_name, content_zip_stream=None):
    create_bucket_response = s3_client.create_bucket(
        Bucket=app_bucket_name,
        ACL = 'private',
        CreateBucketConfiguration = {
            'LocationConstraint' : region_name,
        }
    )
    s3_client.put_public_access_block(
        Bucket=app_bucket_name,
        PublicAccessBlockConfiguration = {
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True        
        }
    )
    bucket_policy = _factory.get_s3_bucket_policy( app_bucket_name, )
    # logging.info(bucket_policy)
    s3_client.put_bucket_policy(
        Bucket=app_bucket_name,
        Policy=bucket_policy,
    )

    # Populate the bucket (if content is provided)
    if content_zip_stream is not None:
        last_bucket_key = None
        with zipfile.ZipFile(content_zip_stream) as content_zip_file:
            for object_name in content_zip_file.namelist():
                _logger.info("Adding %s",object_name)
                bucket_key = object_name
                if bucket_key.startswith("/") == False:
                    bucket_key = "/" + bucket_key
                content_type, _  = mimetypes.guess_type(object_name,strict=True)
                if content_type is None or "/" not in content_type: #pragma: nocover
                    content_type = "application/octet-stream"
                s3_client.put_object(
                    Bucket = app_bucket_name,
                    Key = bucket_key,
                    Body = content_zip_file.read(object_name),
                    ContentType =  content_type
                )
                last_bucket_key = bucket_key
        # Loop until the last object created is retrievable
        logging.info("Waiting for last uploaded object to be retrievable")
        get_last_object_response = s3_client.get_object(
            Bucket = app_bucket_name,
            Key = last_bucket_key
        )

def deploy_api(app_baseline_name,lambda_deployment_result, api_key):
    get_fn_response = lambda_client.get_function(FunctionName=app_baseline_name)
    fn_arn = get_fn_response["Configuration"]["FunctionArn"]
    integration_arn = _factory.get_integration_arn(fn_arn)

    api_details = apiv2_client.create_api(
        Name=app_baseline_name, 
        ProtocolType='HTTP',
        Target=fn_arn # or integration_arn ?
    )
    assert _get_response_status_code(api_details) == 201
    api_id = api_details["ApiId"]
    api_endpoint = api_details["ApiEndpoint"]
    logging.info("API endpoint: %s", api_endpoint)
    #logging.info("api_details:",api_details)

    get_integrations_response = apiv2_client.get_integrations( 
        ApiId = api_id 
    )
    [[ integration_details ]] = [ get_integrations_response["Items"] ]
    integration_uri = integration_details['IntegrationUri']
    #logging.info(integration_uri)
    source_arn = copy.deepcopy(integration_uri)
    source_arn = source_arn.replace(":lambda:",":execute-api:") 
    source_arn = source_arn.replace(":function:",":")
    source_arn = source_arn.replace(app_baseline_name,api_id)
    source_arn += "/*/$default"
    #logging.info(integration_uri)
    #logging.info(source_arn)

    add_permission_response = lambda_client.add_permission(
        FunctionName = fn_arn,
        StatementId = app_baseline_name + "-permit_api_to_run_function",
        Action = "lambda:InvokeFunction",
        Principal = "apigateway.amazonaws.com",
        SourceArn = source_arn
    )
    #logging.info(add_permission_response)
    assert _get_response_status_code(add_permission_response) == 201

    # If API key protection is required, set up an authorizer
    stage_variables = None
    if api_key is not None:
        stage_variables =  { "WASTE_API_KEY": api_key }
        get_auth_fn_response = lambda_client.get_function(FunctionName=app_baseline_name)
        auth_fn_arn = get_auth_fn_response["Configuration"]["FunctionArn"]
        add_permission_response = lambda_client.add_permission(
            FunctionName = auth_fn_arn,
            StatementId = app_baseline_name + "-permit_api_to_run_auth_function",
            Action = "lambda:InvokeFunction",
            Principal = "apigateway.amazonaws.com",
            SourceArn = source_arn
        )
        assert _get_response_status_code(add_permission_response) == 201
        authorizer_uri = (
            "arn:aws:apigateway:" + 
            region_name + 
            ":lambda:path/2015-03-31/functions/" +
            integration_uri + 
            "/invocations"
        )
        logging.info(authorizer_uri)
        apiv2_client.create_authorizer(
            ApiId = api_id,
            AuthorizerPayloadFormatVersion = "2.0",
            AuthorizerResultTtlInSeconds = 300,
            AuthorizerType = 'REQUEST',
            AuthorizerUri = authorizer_uri,
            EnableSimpleResponses=True,
            IdentitySource = [ 
                '$request.header.x-api-key','$stageVariables.WASTE_API_KEY',
            ],
            Name = 'lambda-authorizer',
        )

        access_log_settings = {
            "DestinationArn": lambda_deployment_result["loggroup_arn"],
            "Format": '{ "requestId":"$context.requestId", "status":"$context.status" }'
        },
        update_stage_response = apiv2_client.update_stage(
            ApiId = api_id,
            StageName = '$default',
            DefaultRouteSettings = {
                "DetailedMetricsEnabled": True,
                "ThrottlingBurstLimit": 10,
                "ThrottlingRateLimit": 10.0,
            },
            AccessLogSettings = access_log_settings, 
            StageVariables = stage_variables
        )
        logging.info(update_stage_response)
        assert _get_response_status_code(update_stage_response) == 200
    return api_details

def deploy_bucket(app_baseline_name,initial_bucket_content_zip=None):
    return create_bucket(app_baseline_name,initial_bucket_content_zip)

def deploy_lambda(
    app_baseline_name, 
    default_doc_name, 
    cache_zip_path=None
):
    return create_function(
        app_baseline_name, 
        default_doc_name, 
        cache_zip_path
    )

def generate_random_api_key():
    securely_randomized_bytes = os.urandom(24)
    return str(base64.urlsafe_b64encode(securely_randomized_bytes),'utf-8').strip()

def deploy_app(
    app_name,content_zip_stream=None,
    default_doc_name=None, 
    cache_zip_path=None,
    create_groups=True,
    api_key=None
):
    logging.info("")

    app_baseline_name = app_name + "-" + str(int(time.time()))
    logging.info("app_baseline_name: %s",app_baseline_name)

    # Create a default content bucket for the app
    deploy_bucket_result = deploy_bucket(app_baseline_name,content_zip_stream)

    logging.info("Deploying lambda")
    lambda_deployment_result = deploy_lambda(
        app_baseline_name,
        default_doc_name,
        cache_zip_path
    )
    logging.info("Deploying API")
    if api_key == "*":
        api_key = generate_random_api_key()
        logging.info("Random generated API key is %s"%(api_key,))
    api_details = deploy_api(
        app_baseline_name, 
        lambda_deployment_result,
        api_key
    )
    url1 = api_details["ApiEndpoint"]
    # Insert a short delay to ensure that the API is accessible
    time.sleep(3)
    if create_groups == False:
        logging.info("Creation of AIM security groups has been disabled")
    else:
        _GROUP_SUFFIX_VIEWER = "logviewer"
        _GROUP_SUFFIX_EDITOR = "bucketeditor"
        _GROUP_SUFFIX_LAMBDA = "lambdaeditor"
        _GROUP_POLICY_TEMPLATES = {
            _GROUP_SUFFIX_VIEWER: _factory.get_log_viewer_policy(_GROUP_SUFFIX_VIEWER, app_baseline_name),
            _GROUP_SUFFIX_EDITOR: _factory.get_s3_editor_policy(_GROUP_SUFFIX_EDITOR, app_baseline_name),
            _GROUP_SUFFIX_LAMBDA: _factory.get_s3_editor_policy(_GROUP_SUFFIX_LAMBDA, app_baseline_name),
        }
        for group_suffix in _GROUP_POLICY_TEMPLATES.keys():
            group_name = app_baseline_name+"-" + group_suffix
            iam_client.create_group(GroupName=group_name)
            iam_client.put_group_policy(
                GroupName=group_name, 
                PolicyName=group_name,
                PolicyDocument=_GROUP_POLICY_TEMPLATES[group_suffix]
            )
            logging.info("AIM security group %s has been created"%(group_name,))
    return app_baseline_name, url1

