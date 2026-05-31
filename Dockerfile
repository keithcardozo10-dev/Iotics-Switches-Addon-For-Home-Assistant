ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

RUN pip3 install --no-cache-dir \
    paho-mqtt \
    websockets

COPY run.sh /
COPY bridge.py /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
