#! python

import logging
import os

from io import BytesIO

import context

from collections import namedtuple
from waste.handler.shared import (
    serialize_object_for_log,
    set_mock_s3_client,
    ENVVAR_CONTENT_BUCKET_NAME,
    JSON_CONTENT_TYPE_KEY
)

from botocore.exceptions import ClientError as BotocoreClientError

MockClientInstruction = namedtuple('MockClientInstruction', 'op_name outcome extra')

class MockClient:
    def __init__(self):
        self.instructions = []
    def add_instruction(self, op_name, outcome, extra):
        self.instructions += [ MockClientInstruction(op_name, outcome, extra)]
    def set_envvar(self,name,value):
        if value is not None:
            os.environ[name] = value
        else:
            del os.environ[name]
    def dispose(self):
        assert len(self.instructions) == 0
        pass


class MockS3Client(MockClient):
    def __init__(self, simulated_bucket_contents = [],envvars={}):
        super().__init__()
        self.bucket_sim = { }        
        set_mock_s3_client(self)
        for content_item in simulated_bucket_contents:
            self.mock_put_object(*content_item)
        for envvar_key in envvars:
            self.set_envvar(envvar_key,envvars[envvar_key])
    def dispose(self):
        set_mock_s3_client(None)
        super().dispose()
    def mock_put_object(self, key, content_type, body ):
        self.bucket_sim[key] = ( content_type, body )
    def get_object(self,Bucket,Key):
        if len(self.instructions) > 0:
            op_name, outcome, extra = self.instructions.pop(0)
            assert op_name == "get_object"
            assert outcome == "raise_client_error"
            error_response = { "Error": { "Message": extra } }
            raise BotocoreClientError(error_response,"get_object")
        elif Key in self.bucket_sim:
            response_details = self.bucket_sim[Key]
            return {
                "ResponseMetadata": { "HTTPStatusCode": 200 },
                JSON_CONTENT_TYPE_KEY: response_details[0],
                "Body" : BytesIO(response_details[1])
            }
        elif True:
            return { "ResponseMetadata": { "HTTPStatusCode": 403 } }
        else:
            logging.info("MockS3Object.get_object: Failed to find object with key %s",Key)
            error_response = { "Error": { "Message": "Access Denied" }, "statusCode": 403 }
            return error_response
            # raise BotocoreClientError(error_response,"get_object")
