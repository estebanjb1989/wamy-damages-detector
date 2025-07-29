#!/usr/bin/env python3
import aws_cdk as cdk
from stack import DamageDetectionStack

app = cdk.App()
DamageDetectionStack(app, "DamageDetectionStack", env=cdk.Environment(region="us-east-2"))
app.synth()
