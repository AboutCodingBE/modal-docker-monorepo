FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download nl_core_news_lg
RUN python -c "import nltk; nltk.download('stopwords')"

COPY . .

CMD ["bash", "start.sh"]
