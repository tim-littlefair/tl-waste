import boto3

class Factory:
    def __init__( self, region_name ):
        self.aws_account_id = boto3.client('sts').get_caller_identity().get('Account')
        self.region_name = region_name
        self.clients = { }
        self._create_client("iam")
        self._create_client("s3")
        self._create_client("lambda")
        #self._create_client("apigateway")
        self._create_client("apigatewayv2")
        self._create_client("logs")
    
    def _create_client(self,aws_service_name):
        client = boto3.client(
            aws_service_name,
            region_name=self.region_name
        )
        self.clients[aws_service_name] = client
        return client

    def get_client(self,service_name):
        return self.clients.get(service_name)

    def get_region_name(self):
        return self.region_name
        
    def get_account_id(self):
        return self.aws_account_id

    def get_integration_arn(self,fn_arn):
     return ":".join([
        "arn:aws:apigateway",
        self.region_name,
        "lambda:path/2015-03-31/functions/"
    ]) + fn_arn + "/invocations"

    def get_arn(self,prefix,suffix,include_region=True):
        if include_region is True:
            return "%s:%s:%s:%s" % ( prefix, self.region_name, self.aws_account_id,suffix )
        else:
            return "%s::%s:%s" % ( prefix, self.aws_account_id, suffix )

    def get_s3_bucket_policy(self,app_bucket_name):
        return """{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowLambdaToCreateAndAccessBucket",
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": [
                            "arn:aws:iam::%s:role/LambdaBasicExecution"
                        ]
                    },
                    "Action": [
                        "s3:PutObject",
                        "s3:PutObjectAcl",
                        "s3:GetObject"
                    ],
                    "Resource": [
                        "arn:aws:s3:::%s/*"
                    ]
                }
            ]
        }"""  % ( self.aws_account_id,app_bucket_name)          
            


