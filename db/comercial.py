import psycopg2
import pandas as pd
import os

def get_chamados_comercial():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )
    df = pd.read_sql("SELECT * FROM ordens_servico ORDER BY data_abertura DESC", conn)
    conn.close()
    return df
