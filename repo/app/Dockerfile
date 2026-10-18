FROM python:3.12-slim
RUN apt-get update -qq && apt-get upgrade -y -qq && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir PyMySQL==1.1.1
WORKDIR /app
COPY --chmod=0644 shop.py .
USER 10001
CMD ["python", "-u", "shop.py"]
