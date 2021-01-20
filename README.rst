tl-waste 
========

Tim Littlefair's Web Application Serverless Transition Environment
------------------------------------------------------------------

This repository contains package of python scripts which can be used to build a 
serverless application using the following AWS services:
- API Gateway;
- Lambda; and
- S3.

At its simplest, this package can be used to create a simple static website
backed by an AWS S3 bucket.  The capabilities of this website are similar to 
those obtainable from an S3 static website(as described on 
https://docs.aws.amazon.com/AmazonS3/latest/dev/WebsiteHosting.html)
except that no-HTTPS limitation mentioned in this document for S3-hosted
websites without CloudFront does not apply.



