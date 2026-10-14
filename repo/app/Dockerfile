FROM python:3.12-slim
RUN pip install --no-cache-dir PyMySQL==1.1.1
WORKDIR /app
COPY --chmod=0644 shop.py .
USER 10001
CMD ["python", "-u", "shop.py"]
