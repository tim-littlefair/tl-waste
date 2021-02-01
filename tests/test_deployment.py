#! python

import io
import os
import zipfile
import time
import logging

import requests

import context

from waste.deploy.deploy_support import deploy_app
from waste.deploy.retire_support import retire_app
from waste.deploy.content_support import content_dir_to_in_memory_zip_stream

from simulated_content_generation import (
    gen_random_byte_sequence,
    SIMULATED_CACHE_CONTENTS,
    build_cache_stream,
    SIMULATED_BUCKET_CONTENTS
)

def test_simple_deployment():
    retire_app("waste-test-0")
    baseline_name, baseline_url = deploy_app("waste-test-0")
    nonexistent_response = requests.get(baseline_url+"/nonexistent.docx")
    assert 404 == nonexistent_response.status_code 
    logging.info(
        "App baseline %s deployed and accessible via URL %s",
        baseline_name, baseline_url
    )

def test_deployment_with_content():
    in_memory_zip_stream = io.BytesIO()
    with zipfile.ZipFile(in_memory_zip_stream,"w") as in_memory_zip:
        in_memory_zip.writestr("/public.html","<html>Public HTML</html>")
        in_memory_zip.writestr(
            "/public.json",
            """{ "access": "public", "format": "json" }"""
        )
        in_memory_zip.writestr("/binary.xyz","")
    retire_app("waste-test-1")
    baseline_name, baseline_url = deploy_app(
        "waste-test-1",
        content_zip_stream=in_memory_zip_stream
    )
    logging.info(
        "App baseline %s deployed and accessible via URL %s",
        baseline_name, baseline_url
    )
    public_html_response = requests.get(baseline_url+"/public.html")
    assert 200 == public_html_response.status_code
    assert "text/html" == public_html_response.headers["Content-Type"]
    public_json_response = requests.get(baseline_url+"/public.json")
    assert 200 == public_json_response.status_code
    assert "application/json" == public_json_response.headers["Content-Type"]

def test_deployment_as_website():
    sitedir = 'tests/camelid'
    in_memory_zip_stream, namelist = content_dir_to_in_memory_zip_stream(sitedir)
    retire_app("waste-test-2")
    baseline_name, baseline_url = deploy_app(
        "waste-test-2",
        content_zip_stream=in_memory_zip_stream,
        default_doc_name="index.html"
    )
    logging.info(
        "App baseline %s deployed and accessible via URL %s",
        baseline_name, baseline_url
    )
    try:
        for fn in namelist:
            logging.info("Checking that %s is available",fn)
            fbn_response = requests.get(baseline_url + "/" + fn )
            assert fbn_response.status_code == 200
    except NotImplementedError:
        print("Assertion failed attempting to get",fbn_response.url)
        raise
    empty_path_response = requests.get(baseline_url)
    assert empty_path_response.status_code == 200
    root_path_response = requests.get(baseline_url + "/")
    assert root_path_response.status_code == 200

def test_deployment_with_cache_zip():
    in_memory_zip_stream = io.BytesIO()
    with zipfile.ZipFile(in_memory_zip_stream,"w") as in_memory_zip:
        for object_key, _, object_bytes in SIMULATED_BUCKET_CONTENTS:
            in_memory_zip.writestr("/" + object_key, object_bytes)
    retire_app("waste-test-3")
    baseline_name, baseline_url = deploy_app(
        "waste-test-3",
        content_zip_stream=in_memory_zip_stream,
        cache_zip_path="/cache.zip"
    )
    logging.info(
        "App baseline %s deployed and accessible via URL %s",
        baseline_name, baseline_url
    )
    for object_key in SIMULATED_CACHE_CONTENTS:
        expected_length = len(SIMULATED_CACHE_CONTENTS[object_key])
        logging.info("Requesting %s",object_key)
        request_start_time = time.time()
        cached_object_response = requests.get(baseline_url+"/" + object_key)
        response_status_code = cached_object_response.status_code
        request_status_time = time.time()
        actual_length = len(cached_object_response.content)
        request_read_time = time.time()
        logging.info(
            "Request completed, " +
            "status after %5.3f seconds, " +
            "%d bytes read after %5.3f seconds, " +
            "%d bytes per second",
            request_status_time - request_start_time,
            actual_length,
            request_read_time - request_start_time,
            int(actual_length/(request_read_time - request_start_time))
        )
