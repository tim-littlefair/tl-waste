# python3 
# waste/cli.py 

# Copyright Tim Littlefair 2020-
# This file is open source software under the MIT license.
# For terms of this license, see the file LICENSE in the source 
# code distribution or visit 
# https://opensource.org/licenses/mit-license.php

# This file defines the command line interface of the package

import argparse
import logging
import sys
import traceback

import botocore

# Logging needs to be enabled before some of the 
# following imports as they can throw errors
_logger = logging.getLogger()
_logger.setLevel(logging.INFO)

try:
    from .deploy.deploy_support import deploy_app
    from .deploy.retire_support import retire_app
    from .deploy.content_support import content_dir_to_in_memory_zip_stream
    from .handler.shared import serialize_exception_for_log
except botocore.exceptions.ClientError as e:
    if "InvalidClientTokenId" in str(e):
        logging.error("Environment does not contain a valid AWS token")
        sys.exit(2)
    else:
        raise

_ACTION_DEPLOY="deploy"
_ACTION_RETIRE="retire"

class ArgParser(argparse.ArgumentParser):
    def __init__(self):
        super().__init__()
        self.add_argument(
            "action", type=str, choices=[_ACTION_DEPLOY,_ACTION_RETIRE],
            help="Operation to be performed"
        )
        self.add_argument(
            "app_name", type=str, 
            help="Name of application to be deployed"
        )
        self.add_argument(
            "--content-dir", type=str, action="store", 
            help="Directory containing content to be served"
                " (ignored if action=" + _ACTION_RETIRE + ")"
        )
        self.add_argument(
            "--index-doc", type=str, action="store", 
            default="index.html",
            help="Default document name if path matches a folder"
                " (ignored if action=" + _ACTION_RETIRE + ")"
        )
        self.add_argument(
            "--cache-zip-path", type=str, action="store", default=None,
            help="Zipfile path under content_dir containing files to be cached in memory"
                " (ignored if action=" + _ACTION_RETIRE + ")"
        )
        self.add_argument(
            "--preserve-outdated", action="store_true", 
            help="Suppress retirement of previously deployed baselines of the same app"
                " (ignored if action=" + _ACTION_RETIRE + ")"
        )
        self.add_argument(
            "--create-iam-groups", action="store_true",
            help="Create IAM groups which can be used to assign AWS console users rights"
            " to view the app, edit storage content, and edit lambdas"
        )
        self.add_argument(
            "--api-key", 
            default = None,
            help = "API key for the app,"
            " or '*' for an API key to be generated, or None for no API key"
        )

arg_parser = ArgParser()
args = arg_parser.parse_args()
try:
    if args.action==_ACTION_DEPLOY:
        content_zip_stream = None
        if args.content_dir is not None:
            content_zip_stream, _ = content_dir_to_in_memory_zip_stream(
                args.content_dir
            )
        deploy_app(
            args.app_name, content_zip_stream, 
            default_doc_name = args.index_doc, 
            cache_zip_path = args.cache_zip_path,
            create_groups = args.create_iam_groups
        )
    elif args.action==_ACTION_RETIRE:
        retire_app(args.app_name)
    else:
        print("Unsupported action",args.action)
        arg_parser.print_help()
        sys.exit(1)
#except SystemExit:
#    raise
#except NotImplementedError:
#    pass
except botocore.exceptions.ClientError as e:
    if "InvalidClientTokenId" in str(e):
        logging.error("Environment does not contain a valid AWS token")
        sys.exit(2)
    else:
        pass
except:
    serialize_exception_for_log(e)
    sys.exit(3)
