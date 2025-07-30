pip install -r requirements-cdk.txt

cdk destroy
cdk bootstrap
cdk deploy

aws s3 cp ./images s3://wamy-dataset/ --recursive