FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir flask google-genai openai mistralai pypdfium2 Pillow

EXPOSE 5000

CMD ["python", "backend/web_designer.py"]