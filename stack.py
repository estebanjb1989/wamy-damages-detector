from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
)
from constructs import Construct
import os

class DamageDetectionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket
        bucket = s3.Bucket(self, "WamyDatasetBucket",
                           bucket_name="wamy-dataset",
                           removal_policy=cdk.RemovalPolicy.DESTROY,
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
            timeout=cdk.Duration.seconds(30),
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

        items = api.root.add_resource("detect")
        items.add_method("POST")  # POST /detect
