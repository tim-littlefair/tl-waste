#! python

import sys
import os
import io
import zipfile
import logging

def content_dir_to_in_memory_zip_stream(content_dir):
    namelist = None
    in_memory_zip_stream = io.BytesIO()
    with zipfile.ZipFile(in_memory_zip_stream,"w") as in_memory_zip:
        for walk_path, subdir_names, file_basenames in os.walk(content_dir):
            walk_path = walk_path.replace("\\","/")
            for fbn in file_basenames:
                file_relpath = "/".join([walk_path,fbn]).replace(content_dir+"/","")
                logging.info("Adding %s to zip",file_relpath)
                in_memory_zip.write(
                    "/".join([content_dir, file_relpath]),
                    arcname = "/" + file_relpath
            )
        namelist = in_memory_zip.namelist()
        logging.info("Zipfile contents: %s",namelist)
    return in_memory_zip_stream, namelist

