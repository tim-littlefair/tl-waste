# python3
# waste/handler/shared.py

# Copyright Tim Littlefair 2020-
# This file is open source software under the MIT license.
# For terms of this license, see the file LICENSE in the source
# code distribution or visit
# https://opensource.org/licenses/mit-license.php

# This file contains definitions which are shared between the two
# handler modules.

import base64
import io
import json
import logging
import math
import traceback

import boto3

ENVVAR_DEFAULT_DOCUMENT_NAME = "WASTE_DEFAULT_DOCUMENT_NAME"
ENVVAR_CONTENT_BUCKET_NAME = "WASTE_CONTENT_BUCKET_NAME"
ENVVAR_CACHE_OBJECT_NAME = "WASTE_CACHE_OBJECT_NAME"

# Constants associated with attributes in the header
# of the HTTPS response document
HDR_CONTENT_TYPE_KEY = 'Content-Type'
HDR_CONTENT_DISPOSITION_KEY = 'Content-Disposition'
HDR_ATTACHMENT_FILENAME_PREFIX = 'attachment;filename='

# Constants associated with attributes of the JSON documents
# which are transmitted and received as HTTPS bodies
JSON_CONTENT_TYPE_KEY = 'ContentType'

logger = logging.getLogger()
logger.setLevel(logging.INFO)

mock_s3_client = None

def get_mockable_s3_client():
    if mock_s3_client is None:
        # This code is not reachable when the handler is running under control
        # of unit tests in test_handler
        # pragma: nocover
        return boto3.client('s3', region_name='ap-southeast-2')
    else:
        debug_log("Using mock S3 client")
        return mock_s3_client

def debug_log(*vars):
    if mock_s3_client is None:
        # Running in AWS - supress log
        return
    logger.setLevel(logging.DEBUG)
    logger.log(logging.DEBUG, *vars, stacklevel=2)
    logger.setLevel(logging.INFO)

def serialize_object_for_log(name, obj):
    def json_dump_default(obj):
        return str(obj)
    logger.log(
        logging.INFO,
        "%s: %s" % (name, json.dumps(obj,default=json_dump_default)),
        stacklevel=2
    )


def serialize_exception_for_log(e):
    logging.error("Exception: %s", traceback.format_exc())


def set_mock_s3_client(new_mock_s3_client):
    global mock_s3_client
    mock_s3_client = new_mock_s3_client

_DEFAULT_MAX_BODY_LENGTH = 5000000
_active_max_body_length = _DEFAULT_MAX_BODY_LENGTH

def override_max_body_length(preferred_mbl=None):
    # This function is used in handler unit tests to allow
    # the chunking mechanism to be tested with values much 
    # smaller than the result (reduces test run time from 
    # ~18 seconds to ~3 seconds)
    global _active_max_body_length
    if preferred_mbl is not None:
        debug_log(
            "Max body length will be reduced from %d to %d for one test scenario",
            _active_max_body_length, preferred_mbl
        )
        _active_max_body_length = preferred_mbl
    else:
        debug_log(
            "Max body length reverts to default value %d",
            _DEFAULT_MAX_BODY_LENGTH
        )
        _active_max_body_length = _DEFAULT_MAX_BODY_LENGTH

def get_http_header(request_event,header_name,default_value):
    # HTTP headers are case insensitive
    # Curl sends lower case headers
    # Python requests sends camel case headers
    # This function attempts to cover both
    # providing header_name is passed in camel case
    for hn in header_name, header_name.lower():
        if hn in request_event["headers"]:
            return request_event["headers"][hn]
    # ... otherwise
    return default_value

def _parse_range_spec(range_spec):
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Range
    assert range_spec.startswith("bytes=")
    range_spec_rhs=range_spec.replace("bytes=","")
    range_string_tuple=range_spec_rhs.split("-")
    if len(range_string_tuple) != 2:
        logging.error("Multiple ranges not yet supported for range spec %s",range_spec)
        raise NotImplementedError
    elif range_string_tuple[1] != "":
        logging.error("Ranges with defined end not yet supported for range spec %s",range_spec)
        raise NotImplementedError
    debug_log(
        "range_spec:%s range_string_tuple:%s",
        range_spec, range_string_tuple
    )
    return int(range_string_tuple[0]),None

def encode_body_bytes(body_bytes,force_base64=False):
    # Content always comes back from an S3 object or a 
    # zipfile S3 cache as a stream of bytes.
    # It must be rendered as a valid UTF-8 string before it 
    # can be passed back to the API gateway, either with or
    # without base64 encoding
    stream_length = len(body_bytes)
    body_str = None
    body_is_base64 = None
    try:
        if force_base64 is True:
            # This is a fragment of a body which 
            # required base64 encoding.
            # Even if the fragment contained only valid
            # UTF-8, we want to encode it consistently
            # with the rest of the body.
            raise UnicodeDecodeError(
                'utf-8',body_bytes, 0, 0, "force_base64==True"
            )
        body_str = body_bytes.decode('utf-8')
        body_is_base64 = False
    except UnicodeDecodeError:
        body_str = base64.b64encode(body_bytes).decode('utf-8')
        body_is_base64 = True
    return body_str, body_is_base64

def build_positive_response(stream, range_spec):
    doc_bytes = stream.read()
    doc_len = len(doc_bytes)
    # Lambda has a maximum response length of 6MBytes so
    # if the document requested (after base64 encoded if 
    # required) exceeds this size, it will be broken into 
    # smaller chunks.
    # The maximum chunk size is a multiple of 4 so 
    # that, when base64-encoded data is broken up, 
    # each fragment contains a whole number of 
    # 4 base64 character/3 encoded byte units.
    body_length_limit = 4 * math.floor(_active_max_body_length/4)
    response = { "headers" : {
            "Accept-Ranges": "bytes",
    } } 
    range_start, range_end = _parse_range_spec(range_spec)
    assert range_end is None # guaranteed by _parse_range_spec
    debug_log("range_start:%d",range_start)
    body_str, body_is_base64 = encode_body_bytes(doc_bytes)
    overall_body_len = len(body_str)
    body_start, body_end = None, None
    if body_is_base64 is False:
        body_start = range_start
        response["headers"][HDR_CONTENT_TYPE_KEY] = "text/plain"           
    elif range_start % 3 == 0:
        body_start = int((range_start*4)/3)
        response["headers"][HDR_CONTENT_TYPE_KEY] = "application/octet-stream"
        response["isBase64Encoded"] = True       
    else:
        # Warn about brain-dead client behaviour
        logging.warning("Range start is not a multiple of 3 (problematic for for base64 reasons) for range spec %s",range_spec)
        # Because the request starts at a byte which is not on a 
        # 3 byte boundary of a base64 group, we need to re-encode the
        # body so that alignment is restored
        body_str, body_is_base64 = encode_body_bytes(doc_bytes[range_start:],force_base64=True)
        debug_log(
            "re-encoded stream: len(body_str):%d body_is_base64:%s",
            len(body_str), body_is_base64
        )
        body_start = 0
        response["headers"][HDR_CONTENT_TYPE_KEY] = "application/octet-stream"
        response["isBase64Encoded"] = True       
    body_fragment = body_str[body_start:]
    debug_log(
        "Before truncation: range_start:%d body_start:%d body_length:%d body_length_limit:%d fragment_len:%d ",
        range_start, body_start, len(body_str), body_length_limit, len(body_fragment)
    )
    if len(body_fragment) > body_length_limit:
        body_fragment=body_fragment[
            0:body_length_limit
        ]
        debug_log(
            "After truncation: fragment_len:%d ",
            len(body_fragment)
        )
    else:
        debug_log("Truncation not required")
    if body_is_base64 is False:
        range_end = range_start + len(body_fragment)
    else:
        range_end = range_start + len(base64.b64decode(body_fragment))
    if len(body_fragment)==overall_body_len:
        # The whole document has been served in a single request
        response["statusCode"]=200
    else:
        response["statusCode"]=206
        response["headers"]["Content-Range"] = "bytes %d-%d/%d" %(
            range_start, 
            range_end - 1, 
            doc_len
        )
    response["body"] = body_fragment
    response["headers"]["Content-Length"] = len(body_fragment)
    return response

