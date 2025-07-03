# Imagem base oficial do Python
FROM python:3.12-slim

# Define diretório de trabalho no container
WORKDIR /app

# Copia arquivos do projeto
COPY . .

# Instala as dependências
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expõe a porta 8080 exigida pelo Railway
EXPOSE 8080

# Comando para iniciar o FastAPI com Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
