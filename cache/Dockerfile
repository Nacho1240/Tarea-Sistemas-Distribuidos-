FROM ubuntu:latest

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip

RUN pip install pymongo requests redis --break-system-packages

#CMD ["tail", "-f"]
CMD ["python3", "-u", "main.py"]
