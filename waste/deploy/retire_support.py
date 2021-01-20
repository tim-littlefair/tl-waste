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
import binascii
import time
import mimetypes
import logging

_logger = logging.getLogger()
#_handler = logging.StreamHandler(sys.stderr)
#_handler.setFormatter(logging.Formatter())
#_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

from .kit_abstract_factory import create_factory_for_kit

_factory = create_factory_for_kit()

iam_client = _factory.get_client('iam')
s3_client = _factory.get_client('s3')
lambda_client = _factory.get_client('lambda')
apiv2_client = _factory.get_client('apigatewayv2')
logs_client = _factory.get_client('logs')
region_name = _factory.get_region_name()

_CLOUDWATCH_LOGGROUP_ARN = _factory.get_arn("arn:aws:logs","log-group:/aws/lambda/")

lambda_url = None

app_name_matches = (
    lambda app_name, resource_name: resource_name.startswith(app_name)
)

_get_response_status_code = lambda x: x["ResponseMetadata"]["HTTPStatusCode"]

def delete_resources(
    app_name, type_string, candidate_list, 
    name_lambda,id_lambda,deletion_lambda
):
    for item in candidate_list:
        # _debug_dump(candidate_list)
        item_name = name_lambda(item)
        item_id = id_lambda(item)
        if app_name_matches(app_name, item_name):
            try:
                delete_response = deletion_lambda(item_name,item_id)
                # For most resoruce types, the deletion request returns status 204.
                # Log groups are different - for them the request returns status 200.
                assert delete_response["ResponseMetadata"]["HTTPStatusCode"] in ( 204, 200 )
                logging.info("Deleted %s.%s with id %s",type_string,item_name,item_id,)
            except botocore.exceptions.ClientError:
                logging.warning("Failed to delete %s.%s with id %s",type_string,item_name,item_id,)
        else:
            logging.debug("Not deleting %s.%s with id %s",type_string,item_name,item_id,) 
            pass

def delete_api_resources(app_name):
    delete_resources(
        app_name,
        "API(v2)", apiv2_client.get_apis()['Items'],
        name_lambda = lambda item: item['Name'],
        id_lambda = lambda item: item['ApiId'],
        deletion_lambda = (
            lambda item_name, item_id: 
                apiv2_client.delete_api(ApiId=item_id)
        )
    )

def delete_lambda_resources(app_name):
    delete_resources(
        app_name,
        "function", lambda_client.list_functions()['Functions'],
        name_lambda=lambda item: item['FunctionName'],
        id_lambda=lambda item: item['FunctionName'],
        deletion_lambda = (
            lambda item_name, item_id: 
                lambda_client.delete_function(FunctionName=item_id)
        )
    )

def delete_loggroup_resources(app_name):
    delete_resources(
        app_name,
        "loggroup", logs_client.describe_log_groups()['logGroups'],
        name_lambda=lambda item: item['logGroupName'].replace("/aws/lambda/",""),
        id_lambda=lambda item: item['logGroupName'],
        deletion_lambda = (
            lambda item_name, item_id: 
                logs_client.delete_log_group(logGroupName=item_id)
        )
    )

def delete_s3_resources(app_name):
    delete_objects_from_bucket = (
        lambda bucket_name:
            delete_resources(
                bucket_name,
                "s3 object",
                s3_client.list_objects_v2(Bucket=bucket_name).get("Contents",[]),
                name_lambda = lambda item: bucket_name + item["Key"],
                id_lambda = lambda item: item["Key"],
                deletion_lambda = (
                    lambda item_name, item_id:
                        (logging.debug(bucket_name, item_id,item_name) and False) or
                        s3_client.delete_object(Bucket=bucket_name, Key=item_id)
                )
            ) 
    )
    delete_resources(
        app_name,
        "bucket",
         s3_client.list_buckets()['Buckets'],
        name_lambda=lambda item: item['Name'],
        id_lambda=lambda item: item['Name'],
        deletion_lambda = (
            lambda item_id, item_name: (
                delete_objects_from_bucket(item_name) or
                s3_client.delete_bucket(Bucket=item_name)
            )
        )
    )

def delete_group_resources(app_name):
    remove_inline_policy_from_group = ( 
        lambda group_name:
            iam_client.delete_group_policy(
                GroupName = group_name,
                PolicyName = group_name
            ) 
    )
    delete_resources(
        app_name,
        "group", iam_client.list_groups()['Groups'],
        name_lambda=lambda item: item['GroupName'],
        id_lambda=lambda item: item['GroupId'],
        deletion_lambda = (
            lambda item_name, item_id: 
                remove_inline_policy_from_group(item_name) and
                iam_client.delete_group(GroupName=item_name)
        )
    )

def retire_app(app_name):
    logging.info("")
    logging.info("Deleting stale resources")
    delete_group_resources(app_name)
    delete_api_resources(app_name)
    delete_lambda_resources(app_name)
    delete_loggroup_resources(app_name)
    delete_s3_resources(app_name)

