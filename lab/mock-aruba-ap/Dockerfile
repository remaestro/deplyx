FROM python:3.12-slim
RUN pip install paramiko cryptography --no-cache-dir
WORKDIR /app
COPY ssh_server.py .
EXPOSE 22
CMD ["python", "-u", "ssh_server.py"]
