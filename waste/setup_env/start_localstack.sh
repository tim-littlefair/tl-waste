#!/bin/sh

script_dir=`dirname $0`
. $script_dir/setup_venv.sh

# localstack environment (see: https://github.com/localstack/localstack)
#LOCALSTACK_SERVICES="apigateway lambda s3"
#LOCALSTACK_LAMBDA_EXECUTOR=local
#export LOCALSTACK_SERVICES LOCALSTACK_LAMBDA_EXECUTOR

export DEFAULT_REGION="ap-southeast-2"
rm -rf /tmp/localstack

localstack infra start

