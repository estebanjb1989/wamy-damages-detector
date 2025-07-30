FROM public.ecr.aws/lambda/python:3.11

RUN yum -y install gcc gcc-c++ make libjpeg-turbo-devel zlib-devel && yum clean all


COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY lambda ./lambda

CMD ["lambda.handler.lambda_handler"]
