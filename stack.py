from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    RemovalPolicy,
    Duration
)
from constructs import Construct
import os
import boto3
from botocore.exceptions import ClientError


class DamageDetectionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        bucket_name = "wamy-dataset"

        # Use boto3 to check if the bucket exists
        s3_client = boto3.client("s3")
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            # If the call succeeds, the bucket exists
            print(f"Bucket '{bucket_name}' exists. Referencing it.")
            bucket = s3.Bucket.from_bucket_name(self, "ExistingWamyBucket", bucket_name)
        except ClientError as e:
            # Bucket does not exist or is not accessible
            print(f"Bucket '{bucket_name}' not found. Creating it.")
            bucket = s3.Bucket(self, "WamyDatasetBucket",
                               bucket_name=bucket_name,
                               removal_policy=RemovalPolicy.DESTROY,
                               block_public_access=s3.BlockPublicAccess(
                                   block_public_acls=False,
                                   block_public_policy=False,
                                   ignore_public_acls=False,
                                   restrict_public_buckets=False
                               ),
                               public_read_access=True)

        # Lambda Function
        fn = _lambda.Function(
            self, "DamageDetectorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            environment={
                "BUCKET_NAME": bucket.bucket_name
            },
            timeout=Duration.seconds(30),
            memory_size=256
        )

        # IAM permissions for Lambda
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["rekognition:DetectLabels"],
            resources=["*"]
        ))

        bucket.grant_read(fn)

        # API Gateway
        api = apigw.LambdaRestApi(
            self, "DamageDetectorAPI",
            handler=fn,
            proxy=False,
            rest_api_name="WindDamageDetectionAPI",
        )

        items = api.root.add_resource("aggregate")
        items.add_method("POST")
