#! python

import io
import os
import zipfile
import logging

import requests

import context

from mock_client import MockS3Client


from waste.handler.simple_lambda_handler import (
    lambda_handler,
    ENVVAR_CONTENT_BUCKET_NAME, 
    ENVVAR_DEFAULT_DOCUMENT_NAME
)

_SIMULATED_BUCKET_CONTENTS = (
    ( "/public.html", "text/html", bytes("<html>Public HTML</html>","utf-8") ),
    ( 
        "/public.json", "application/json", 
        bytes("""{ "access": "public", "format": "json" }""","utf-8" ) 
    ),
    ( "/index.html", "text/html", bytes("<html>Public HTML</html>","utf-8") ),
    ( "/subdir/index.html", "text/html", bytes("<html>Public HTML</html>","utf-8") ),
)

def test_forbidden_method():
    forbidden_event = {
        "requestContext": {
            "http": { "method": "POST", "path": "/trails" }
        },
        "body": ""
    }
    mock_s3_client = MockS3Client()
    forbidden_response = lambda_handler(forbidden_event,context=None)
    mock_s3_client.dispose()
    assert 403 == forbidden_response["statusCode"]   

def test_not_found_document_no_bucket():
    not_found_event = {
        "requestContext": {
            "http": { "method": "GET", "path": "/nonexistent.docx" }
        },
        "body": ""
    }
    mock_s3_client = MockS3Client()
    not_found_response = lambda_handler(not_found_event,context=None)
    mock_s3_client.dispose()
    assert 404 == not_found_response["statusCode"]   

def test_not_found_document_not_in_bucket():
    not_found_event = {
        "requestContext": {
            "http": { "method": "GET", "path": "/nonexistent.docx" }
        },
        "body": ""
    }
    mock_s3_client = MockS3Client()
    mock_s3_client.add_instruction("get_object","raise_client_error","Access Denied")
    not_found_response = lambda_handler(not_found_event,context=None)
    mock_s3_client.dispose()
    assert 404 == not_found_response["statusCode"]

def test_html_document():
    html_doc_event = {
        "requestContext": {
            "http": { "method": "GET", "path": "/public.html" }
        },
        "body": ""
    }
    mock_s3_client = MockS3Client(_SIMULATED_BUCKET_CONTENTS)
    html_doc_response = lambda_handler(html_doc_event,context=None)
    mock_s3_client.dispose()
    assert 200 == html_doc_response["statusCode"]

def test_default_document():
    _DEFAULTABLE_DOC_PATHS = ( "/", "/subdir", "/subdir/","")
    for path in _DEFAULTABLE_DOC_PATHS:
        defaultable_request_event = {
            "requestContext": {
                "http": { "method": "GET", "path": path }
            },
            "body": ""
        }
        # If we do not enable default document to be served, 
        # all of the paths above should result in a not found response
        mock_s3_client = MockS3Client(_SIMULATED_BUCKET_CONTENTS)
        defaultable_doc_response = lambda_handler(defaultable_request_event,context=None)
        mock_s3_client.dispose()
        assert 404 == defaultable_doc_response["statusCode"],"path="+path   

        # If we do enable default document to be served, 
        # all of the paths above should result in a 200 response
        mock_s3_client = MockS3Client(_SIMULATED_BUCKET_CONTENTS)
        mock_s3_client.set_envvar(ENVVAR_DEFAULT_DOCUMENT_NAME,"index.html")
        defaultable_doc_response = lambda_handler(defaultable_request_event,context=None)
        mock_s3_client.set_envvar(ENVVAR_DEFAULT_DOCUMENT_NAME,None)
        mock_s3_client.dispose()
        assert 200 == defaultable_doc_response["statusCode"],"path="+path
        assert type(defaultable_doc_response["body"]) == str

