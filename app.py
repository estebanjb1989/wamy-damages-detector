#!/usr/bin/env python3
from aws_cdk import (
    Environment,
    App
)
from stack import DamageDetectionStack

app = App()
DamageDetectionStack(app, "DamageDetectionStack", env=Environment(region="us-east-2"))
app.synth()
