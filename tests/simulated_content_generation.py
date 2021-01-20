#! python

import hashlib
import io
import os
import random
import zipfile
import logging

_basename_bytes_map = {}

def gen_random_byte_sequence(length):
    retval = bytearray(length)
    for i in range(0,length):
        retval[i] = random.randrange(0,256)
    return bytes(retval)

SIMULATED_CACHE_CONTENTS = {
    "cached_10k": gen_random_byte_sequence(10000),
    "cached_100k": gen_random_byte_sequence(100000),
    "cached_non_ascii_text_utf8" : bytes("Göteborg","utf-8"),
    "cached_non_ascii_text_latin1" : bytes("Göteborg","latin1"),
}

def build_cache_stream(base_cache_contents, extra_cached_content=None):
    in_memory_zip_stream = io.BytesIO()
    with zipfile.ZipFile(in_memory_zip_stream,"w") as in_memory_zip:
        for fn in base_cache_contents:
            file_contents = base_cache_contents[fn]
            logging.debug(
                "_build_cache_stream: adding object %s with length %d",
                fn, len(file_contents)
            )
            _basename_bytes_map[os.path.basename(fn)]=base_cache_contents[fn]
            in_memory_zip.writestr(fn, file_contents)
        if extra_cached_content is not None:
            extra_fn, extra_bytes = extra_cached_content
            logging.debug(
                "_build_cache_stream: adding object %s with length %d",
                extra_fn, len(extra_bytes)
            )
            extra_hash = hashlib.sha256(extra_bytes).hexdigest()
            _basename_bytes_map[os.path.basename(extra_fn)]=extra_hash
            in_memory_zip.writestr(extra_fn, extra_bytes)
    logging.debug(
        "_build_cache_stream: cache is %d bytes long",
        len(in_memory_zip_stream.read())
    )
    in_memory_zip_stream.seek(0)
    return in_memory_zip_stream

def expected_bytes_for_docpath(doc_path):
    return _basename_bytes_map.get(os.path.basename(doc_path),None)

SIMULATED_BUCKET_CONTENTS = [
    ( 
        "not_cached_10k", 
        "application/octet-stream",  
        gen_random_byte_sequence(10000) 
    ),
    ( 
        "not_cached_100k", 
        "application/octet-stream",  
        gen_random_byte_sequence(100000) 
    ),
    ( 
        "not_cached_1M", 
        "application/octet-stream",  
        gen_random_byte_sequence(1000000) 
    ),
    (
        "cache.zip",
        "application/octet-stream",
        build_cache_stream(SIMULATED_CACHE_CONTENTS).read()
    )
]

for bucket_item in SIMULATED_BUCKET_CONTENTS:
    _basename_bytes_map[
        os.path.basename(bucket_item[0])
    ]=bucket_item[2]

