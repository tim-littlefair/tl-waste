# python3
# waste/handler/caching_lambda_handler.py

# Copyright Tim Littlefair 2020-
# This file is open source software under the MIT license.
# For terms of this license, see the file LICENSE in the source
# code distribution or visit
# https://opensource.org/licenses/mit-license.php

# This file implements an alternative lambda handler which creates and
# loads a memory resident cache, and serves requests from there.

import copy
import io
import logging
import os
import pathlib
import zipfile

# sibling file shared.py contains common definitions which are
# used by both handlers
from .shared import HDR_CONTENT_TYPE_KEY, JSON_CONTENT_TYPE_KEY
from .shared import logger, debug_log, serialize_object_for_log
from .shared import serialize_exception_for_log
from .shared import get_http_header
from .shared import (
    ENVVAR_DEFAULT_DOCUMENT_NAME, 
    ENVVAR_CONTENT_BUCKET_NAME,
    ENVVAR_CACHE_OBJECT_NAME
)
from .shared import get_mockable_s3_client
from .shared import build_positive_response

from .simple_lambda_handler import lambda_handler as simple_lambda_handler

ZIP_FILE_EXT = ".zip"

class Cache:

    def __init__(self, search_subpaths=True):
        self.s3_object_name = None
        self.archive = None
        self.search_subpaths = search_subpaths

    def load_from_stream(self, cache_object_name, cache_stream):
        if cache_object_name.endswith(ZIP_FILE_EXT):
            self.archive = zipfile.ZipFile(cache_stream, "r")
        else:
            logging.error(
                "No archive type recognized for cache file name %s",
                cache_file_name
            )
            raise NotImplementedError

    def load_from_s3_object(self, bucket_name, cache_object_name):
        s3_client = get_mockable_s3_client()
        debug_log(
            "About to do %s.get_object with params bucket_name=%s, key=%s",
            type(s3_client).__name__, bucket_name, cache_object_name
        )
        s3_get_response = s3_client.get_object(
            Bucket=bucket_name, Key=cache_object_name
        )
        cache_stream = s3_get_response["Body"]
        self.load_from_stream(
            cache_object_name, 
            io.BytesIO(cache_stream.read())
        )
        self.s3_object_name = cache_object_name

    def open(self,file_name):
        if file_name in self.archive.namelist():
            return self.archive.open(file_name,"r")
        else:
            return None
    
    def search(self, requested_path):
        if requested_path in self.archive.namelist():
            return self.open(requested_path)
        elif self.search_subpaths == False:
            return None
        else:
            path_parts = pathlib.PurePosixPath(requested_path).parts
            while len(path_parts)>0:
                subpath = "/".join(path_parts)
                if subpath in self.archive.namelist():
                    return io.BytesIO(self.open(subpath).read())
                path_parts=path_parts[1:]
            return None


_cache = None

def invalidate_cache_for_test():
    global _cache
    _cache = None

def lambda_handler(event,context):
    global _cache, _cache_object_name
    if _cache is None:
        debug_log("Loading cache")
        _cache = Cache()
        _cache.load_from_s3_object(
            os.getenv(ENVVAR_CONTENT_BUCKET_NAME),
            os.getenv(ENVVAR_CACHE_OBJECT_NAME)
        )
    else:
        debug_log("Cache already loaded")
        pass
    serialize_object_for_log("request_event", event)

    if event["requestContext"]["http"]["method"] in ( "GET", "POST" ):
        requested_path = event["requestContext"]["http"]["path"]
        if requested_path == _cache.s3_object_name:
            # Return the same response the simpler handler
            # would return for an absent document
            decline_to_serve_cache_response = {
                "statusCode": 404,
                "headers":  {'Content-Type': 'text/plain'},
                "body": "document not found at path %s for method %s" % (
                    request_path, request_method
                )
            }
            return decline_to_server_cache_response
        # otherwise continue ...
        stream = _cache.search(requested_path)
        if stream is not None:
            range_spec = get_http_header(event,"Range","bytes=0-")
            cached_doc_response = build_positive_response(stream,range_spec)
            debug_log(
                "response range:%s",
                cached_doc_response["headers"].get("Content-Range","whole document")
            )
            loggable_response = copy.deepcopy(cached_doc_response)
            loggable_response["body"] = "<%d characters long>" % (len(cached_doc_response["body"]),)
            serialize_object_for_log("cached_doc_response",loggable_response)
            return cached_doc_response
    return simple_lambda_handler(event,context)
