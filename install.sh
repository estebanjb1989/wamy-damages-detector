pip install -r requirements.txt

cdk bootstrap
cdk deploy

aws s3 cp ./images s3://wamy-dataset/ --recursive