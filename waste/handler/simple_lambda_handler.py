# python3
# waste/handler/shared.py

# Copyright Tim Littlefair 2020-
# This file is open source software under the MIT license.
# For terms of this license, see the file LICENSE in the source
# code distribution or visit
# https://opensource.org/licenses/mit-license.php

# This file implements a simple AWS lambda hander function which
# maps the paths of URLs as S3 bucket object keys.

import os
import json
import base64
import logging

import boto3
import botocore.exceptions

# sibling file shared.py contains common definitions which are
# used by both handlers
from .shared import HDR_CONTENT_TYPE_KEY, JSON_CONTENT_TYPE_KEY
from .shared import ENVVAR_DEFAULT_DOCUMENT_NAME, ENVVAR_CONTENT_BUCKET_NAME
from .shared import logger, debug_log, serialize_object_for_log
from .shared import serialize_exception_for_log
from .shared import get_mockable_s3_client
from .shared import encode_body_bytes

def _build_response_from_s3_object(
    key,
    bucket_name,
    default_doc_name=None,
    bucket_key_prefix=None,
    pylambda_list=[]
):
    # assert len(key) > 0
    s3_client = get_mockable_s3_client()

    if bucket_key_prefix is None:
        pass
    elif bucket_key_prefix.endswith("/") or key.startswith("/"):
        key = bucket_key_prefix + key
    else:
        key = bucket_key_prefix + "/" + key

    keys_to_try = [key]
    if default_doc_name is not None:
        default_doc_key = (key + "/" + default_doc_name).replace("//", "/")
        keys_to_try += [default_doc_key]
    debug_log({ "keys_to_try": keys_to_try} )
    s3_get_response = None
    responseStatusCode = None
    response = None
    for candidate_key in keys_to_try:
        response = {}
        logging.info(
            "About to do %s.get_object with params bucket_name=%s, key=%s",
            type(s3_client).__name__, bucket_name, candidate_key
        )
        try:
            s3_get_response = s3_client.get_object(
                Bucket=bucket_name, Key=candidate_key
            )
            responseStatusCode = (
                s3_get_response["ResponseMetadata"]["HTTPStatusCode"]
            )
            # serialize_object_for_log("s3_get_response", s3_get_response)
            response["statusCode"] = responseStatusCode
            if responseStatusCode == 200:
                response["headers"] = {
                    HDR_CONTENT_TYPE_KEY:
                        s3_get_response[JSON_CONTENT_TYPE_KEY]
                }
                raw_body_stream = s3_get_response["Body"]
                raw_body_bytes = raw_body_stream.read()
                body_str, body_str_is_base64 = encode_body_bytes(raw_body_bytes)
                if len(pylambda_list) == 0:
                    pass
                elif body_str_is_base64 is True:
                    # Need to run the lambdas then re-encode the body
                    for pylambda in pylambda_list:
                        raw_body_bytes = pylambda(raw_body_bytes)
                    body_str, body_str_is_base64 = encode_body_bytes(raw_body_bytes)
                else:
                    for pylambda in pylambda_list:
                        body_str = pylambda(body_str)
                response["body"] = body_str
                response["isBase64Encoded"] = body_str_is_base64
                break
        except botocore.exceptions.ClientError:
            pass

    return response



def _save_event_to_s3_object(
    event,
    context,
    bucket_name
):
    s3_client = get_mockable_s3_client()
    req_id = context.get("aws_request_id")
    s3_put_response = s3_client.put_object(
        Bucket=bucket_name,
        Key=req_id,
        Body=json.dumps(event, indent=4)
    )
    serialize_object_for_log("s3_put_response", s3_put_response)
    return {"bucket_name": bucket_name, "event_key": req_id}


def respond_on_exception_in_handler(e, request_path, request_method):
    serialize_exception_for_log(e)
    return {
        "statusCode": 500,
        "headers":  {'Content-Type': 'application/json'},
        "body": bytes(
            "internal error handling path %s for method %s" % (
                request_path, request_method,
            ), "utf-8"
        )
    }


def lambda_handler(event, context):
    logger.setLevel(logging.INFO)
    # For unit tests, we supply a mock s3 client object which accepts
    # the same messages as the real client and gives approximately
    # the same responses.
    # If s3_client is populated on entry to this handler, it is
    # such a mock
    s3_client = get_mockable_s3_client()
    try:
        default_doc_name = os.environ.get(ENVVAR_DEFAULT_DOCUMENT_NAME, None)
        content_bucket_name = os.environ.get(ENVVAR_CONTENT_BUCKET_NAME, "")
        if len(content_bucket_name) == 0:
            content_bucket_name = "dummy"
        # If there is an environment variable which defines a send bucket,
        # object in the S3 emulation bucket which
        # matches the path of the request, return it.
        response = None

        request_path = event["requestContext"]["http"]["path"]
        # If the path is an empty string, replace it with the root path
        if len(request_path) == 0:
            request_path = "/"

        request_method = event["requestContext"]["http"]["method"]

        if "GET" == request_method:
            # For security we send the same document not found
            # response whether or a content bucket is not deployed
            # in this integration, or whether one is deployed but
            # the lookup into it fails.
            not_found_response = {
                "statusCode": 404,
                "headers":  {'Content-Type': 'text/plain'},
                "body": "document not found at path %s for method %s" % (
                    request_path, request_method
                )
            }
            if content_bucket_name is None:
                response = not_found_response
            else:
                try:
                    content_bucket_response = _build_response_from_s3_object(
                        key=request_path,
                        bucket_name=content_bucket_name,
                        default_doc_name=default_doc_name
                    )
                    response = content_bucket_response
                    #debug_log({"content_bucket_response":str(content_bucket_response)})
                    if response.get("statusCode", -1) != 200:
                        response = not_found_response
                except botocore.exceptions.ClientError as e:
                    if str(e).endswith('Access Denied') is False:
                        raise
                    response = not_found_response

        else:
            forbidden_response = {
                "statusCode": 403,
                "headers":  {'Content-Type': 'application/json'},
                "body": "path %s is not supported for %s request" % (
                    request_path, request_method,
                )
            }
            response = forbidden_response
    except Exception as e:
        response = respond_on_exception_in_handler(
            e, request_path, request_method
        )

    try:
        if response is None:
            error_response = {
                "statusCode": 500,
                "headers":  {'Content-Type': 'application/json'},
                "body": "no supported handler for path %s for method %s" % (
                    request_path, request_method,
                )
            }
            response = error_response

        if "body" in response:
            # assert isinstance(response["body"], str)
            pass
            
        request_log_object = {
            "AWS_EVENT": event,
            "RESPONSE": response
        }

        # serialize_object_for_log("request_log_object", request_log_object)
        s3_client = None
    except Exception as e:
        response = respond_on_exception_in_handler(
            e, request_path, request_method
        )
    logger.setLevel(logging.INFO)
    return response
