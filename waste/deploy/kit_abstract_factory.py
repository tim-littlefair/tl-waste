import os
import sys
import botocore

from .deploy_kit_aws import Factory as AwsFactory

_DEFAULT_REGION_NAME='ap-southeast-2'

def create_factory_for_kit(
    region_name=_DEFAULT_REGION_NAME,
):
    _ls_ipv4_address = os.environ.get("_LS_HOST",None)
    if _ls_ipv4_address is None:
        try:
            return AwsFactory(region_name)
        except botocore.exceptions.NoCredentialsError as e:
            print("Unable to locate AWS credentials",file=sys.stderr)
        sys.exit(1)
    else: # pragma: no cover
        # In order to get high test coverage, we avoid importing
        # the localstack kit unless we are going to use it.
        import deploy_kit_localstack
        if _ls_ipv4_address == "LOCALSTACK":
            _ls_ipv4_address = None
        return deploy_kit_localstack.Factory(
            region_name,_ls_ipv4_address
        )

