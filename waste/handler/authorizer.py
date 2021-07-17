# Adapted from:
# https://github.com/awslabs/aws-apigateway-lambda-authorizer-blueprints/blob/master/blueprints/python/api-gateway-authorizer-python.py
# and
# https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-use-lambda-authorizer.html
import logging

def lambda_handler(event, context):
    # AWS APIGatewayV2 service does not support the simple 
    # API key concept, this handler fakes it using the 
    # simple response format.
    logging.info(event)
    logging.info(context)
    is_authorized = True  # TODO change to false when tested
    #if event.stageVariables["WASTE_API_KEY"] == event.request.headers["x-api-id"]:
    #    is_authorized = True
    return { "isAuthorized": is_authorized }

