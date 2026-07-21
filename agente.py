import json
import os
import sqlite3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from serpapi import GoogleSearch

# 1. Carregar Configurações
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

SERPAPI_KEY = os.getenv('SERPAPI_KEY')
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

# 2. Conectar/Criar Banco de Dados SQLite
conn = sqlite3.connect('historico_precos.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS historico (
        data_consulta TEXT,
        origem TEXT,
        destino TEXT,
        preco REAL,
        link TEXT
    )
''')
conn.commit()

# 3. Consultar SerpApi (Google Flights)
params = {
    "engine": "google_flights",
    "departure_id": config["origem"],
    "arrival_id": config["destino"],
    "outbound_date": config["data_ida"],
    "return_date": config["data_volta"],
    "currency": "BRL",
    "hl": "pt",
    "api_key": SERPAPI_KEY
}

try:
    search = GoogleSearch(params)
    results = search.get_dict()

    best_flights = results.get("best_flights", [])
    if not best_flights:
        best_flights = results.get("other_flights", [])

    if best_flights:
        menor_preco = best_flights[0]["price"]
        link_compra = results.get("search_metadata", {}).get("google_flights_url", "https://www.google.com/travel/flights")
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Salvar histórico no banco SQLite
        cursor.execute('''
            INSERT INTO historico (data_consulta, origem, destino, preco, link)
            VALUES (?, ?, ?, ?, ?)
        ''', (data_atual, config["origem"], config["destino"], menor_preco, link_compra))
        conn.commit()

        # Exportar histórico em JSON para o site (GitHub Pages)
        df = pd.read_sql_query("SELECT data_consulta, preco, link FROM historico", conn)
        df.to_json('dados.json', orient='records', indent=2)

        print(f"[{data_atual}] Menor preço encontrado: R$ {menor_preco}")

        # 4. Gerar Gráfico Comparativo em Imagem
        plt.figure(figsize=(10, 5))
        plt.plot(df['data_consulta'], df['preco'], marker='o', color='#1a73e8', linewidth=2)
        plt.title(f'Evolução de Preço: {config["origem"]} ➔ {config["destino"]} ({config["data_ida"]} a {config["data_volta"]})')
        plt.xlabel('Data/Hora da Consulta')
        plt.ylabel('Preço (R$)')
        plt.xticks(rotation=45, ha='right')
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()

        grafico_path = 'grafico_precos.png'
        plt.savefig(grafico_path, dpi=150)
        plt.close()

        # 5. Enviar Alerta por E-mail
        if EMAIL_USER and EMAIL_PASS:
            msg = MIMEMultipart()
            msg['Subject'] = f'✈️ Alerta de Passagem: {config["origem"]} ➔ {config["destino"]} por R$ {menor_preco}'
            msg['From'] = EMAIL_USER
            msg['To'] = config["notificacoes"]["email_destino"]

            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Agente Autônomo de Passagens</h2>
                <p>Encontramos uma opção de voo para a sua viagem:</p>
                <ul>
                    <li><b>Rota:</b> {config["origem"]} ➔ {config["destino"]}</li>
                    <li><b>Ida:</b> {config["data_ida"]} | <b>Volta:</b> {config["data_volta"]}</li>
                </ul>
                <div style="background-color: #f1f8e9; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 16px; color: #555;">Menor preço atual:</span><br>
                    <span style="font-size: 32px; font-weight: bold; color: #2e7d32;">R$ {menor_preco}</span>
                </div>
                <p><a href="{link_compra}" style="background-color: #1a73e8; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Visualizar no Google Flights</a></p>
                <br>
                <p>O gráfico comparativo do histórico de preços segue em anexo.</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))

            if os.path.exists(grafico_path):
                with open(grafico_path, 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-Disposition', 'attachment', filename='historico_precos.png')
                    msg.attach(img)

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)
            
            print("E-mail enviado com sucesso!")

except Exception as e:
    print(f"Erro ao executar o agente: {e}")
finally:
    conn.close()
