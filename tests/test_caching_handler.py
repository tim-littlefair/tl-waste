#! python

import base64
import hashlib
import io
import logging
import os
import random
import zipfile

import requests
import pytest

import context

from mock_client import MockS3Client

import waste.handler.caching_lambda_handler
from waste.handler.shared import (
    ENVVAR_CONTENT_BUCKET_NAME, 
    ENVVAR_DEFAULT_DOCUMENT_NAME,
    ENVVAR_CACHE_OBJECT_NAME,
    serialize_object_for_log,
    override_max_body_length,
    debug_log
)

from simulated_content_generation import (
    gen_random_byte_sequence,
    SIMULATED_CACHE_CONTENTS,
    build_cache_stream,
    expected_bytes_for_docpath,
    SIMULATED_BUCKET_CONTENTS
)

def test_cache_creation():
    print("") # close the line containing the '.' emitted by pytest
    cache = waste.handler.caching_lambda_handler.Cache()
    cache.load_from_stream(
        "cache.zip",build_cache_stream(SIMULATED_CACHE_CONTENTS)
    )
    assert 10000 == len(cache.open("cached_10k").read())
    assert 100000 == len(cache.open("cached_100k").read())
    assert cache.open("cached_50k") is None

def template_test_method(
    doc_path, 
    expected_status_code, 
    expected_length = None,
    bucket_contents_for_test = SIMULATED_BUCKET_CONTENTS,
    client_truncation_bytes = 0
):
    print("") # close the line containing the '.' emitted by pytest
    doc_event = {
        "requestContext": {
            "http": { "method": "GET", "path": doc_path }
        },
        "body": "",
        "headers": {}
    }
    mock_s3_client = MockS3Client(
        simulated_bucket_contents = bucket_contents_for_test,
        envvars = { 
            ENVVAR_CONTENT_BUCKET_NAME: "test1_bucket",
            ENVVAR_CACHE_OBJECT_NAME: "cache.zip" 
        }
    )
    waste.handler.caching_lambda_handler.invalidate_cache_for_test()
    doc_response = waste.handler.caching_lambda_handler.lambda_handler(
        doc_event,context=None
    )
    expected_bytes = expected_bytes_for_docpath(doc_path)
    response_body_str = doc_response.get("body","")
    response_body_bytes = bytes()
    if doc_response.get("isBase64Encoded",False) is True:
        response_body_bytes += base64.b64decode(response_body_str)
    else:
        response_body_bytes += response_body_str.encode("utf-8")
    # If the response is partial, iterate until all fragments 
    # have been collected
    while doc_response["statusCode"]==206:
        # There is a specific client which truncates one byte
        # off every fragment received (to avoid sending a request
        # for an empty range and triggering an error)
        # parameter client_truncation_bytes is used when this
        # client needs to be emulated.
        if client_truncation_bytes>0:
            response_body_bytes = response_body_bytes[:-1*client_truncation_bytes]
        response_body_len = len(response_body_bytes)
        doc_event["headers"]["Range"]="bytes=%d-" % (response_body_len,)
        doc_response = waste.handler.caching_lambda_handler.lambda_handler(
            doc_event,context=None
        )
        assert expected_status_code == 206
        fragment_body_str = doc_response.get("body","")
        length_before_append = len(response_body_bytes)
        if doc_response.get("isBase64Encoded",False) is True:
            response_body_bytes += base64.b64decode(fragment_body_str)
        else:
            response_body_bytes += fragment_body_str.encode("utf-8")
        debug_log("expected: %s",expected_bytes[length_before_append-2:length_before_append+4])
        debug_log("retrieved: %s",response_body_bytes[length_before_append-2:length_before_append+4])
        debug_log("length before/after append: %d,%d",length_before_append,len(response_body_bytes))
        if doc_response["headers"]["Content-Range"].endswith(
            "-%d/%d" % ( expected_length-1, expected_length)
        ):
            break
    mock_s3_client.dispose()
    assert expected_status_code == doc_response["statusCode"]
    is_base64_encoded = doc_response.get("isBase64Encoded",False)
    if expected_length is None:
        assert is_base64_encoded is False
    else:
        assert bytes == type(response_body_bytes)
        assert expected_length == len(response_body_bytes)

def test_absent_document():
    template_test_method('/nonexistent.docx',404)

def test_cache_not_served_as_document():
    template_test_method('/cache.zip',404)

def test_cached_document():
    template_test_method('/cached_10k',200,10000)

def test_not_cached_document():
    template_test_method('not_cached_10k',200,10000)

def test_cached_document_with_relative_path():
    template_test_method('cached_10k',200,10000)

def test_cached_document_with_extended_path():
    template_test_method('/random/multipart/path/cached_10k',200,10000)

def test_cached_document_with_nonascii_chars_utf8():
    template_test_method('cached_non_ascii_text_utf8',200,9)

def test_cached_document_with_nonascii_chars_latin1():
    template_test_method('cached_non_ascii_text_latin1',200,8)

def test_cached_oversize_document():
    # For this test we override the default maximum fragment size
    # so that we can verify that fragmented delivery works in a 
    # test which runs reasonably quickly
    override_max_body_length(5000)
    template_test_method('/cached_10k',206,10000,SIMULATED_BUCKET_CONTENTS,0)
    override_max_body_length()

def test_cached_oversize_document_truncating_client():
    # Same as the test above, except that we are emulating the 
    # behaviour of a brain-dead client which always throws 
    # 1 byte away before requesting the next chunk of an 
    # oversize document.
    override_max_body_length(5000)
    template_test_method('/cached_10k',206,10000,SIMULATED_BUCKET_CONTENTS,1)
    override_max_body_length()

def test_cached_large_document():
    # For this test we leave the default maximum fragment size
    # unchanged and verify that fragmented delivery works for
    # a file of the size which requires it, with the brain-dead
    # client behaviour.
    # This test takes about 18 seconds to run.
    print("") # close the line containing the '.' emitted by pytest
    override_max_body_length() # In case the previous test did not reset
    test_specific_cache_stream = build_cache_stream(
        SIMULATED_CACHE_CONTENTS,
        ( "cached_10M", gen_random_byte_sequence(10000000) )
    )
    test_specific_bucket_content = SIMULATED_BUCKET_CONTENTS
    test_specific_bucket_content += [ (
        "cache.zip",        
        "application/octet-stream",  
        test_specific_cache_stream.read()
    )]
    template_test_method('cached_10M',206,10000000,test_specific_bucket_content,1)

