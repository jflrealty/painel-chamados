# routes_export.py
import os, io
import pandas as pd
from fastapi import Request, APIRouter
from fastapi.responses import StreamingResponse, HTMLResponse
from utils.slack_helpers import get_real_name
from main import carregar_chamados

export_router = APIRouter()

@export_router.get("/exportar", response_class=HTMLResponse)
async def exportar(request: Request, tipo: str = "xlsx", **filtros):
    chamados = carregar_chamados(
        status=filtros.get("status"),
        resp_nome=filtros.get("responsavel"),
        d_ini=filtros.get("data_ini"),
        d_fim=filtros.get("data_fim"),
        capturado=filtros.get("capturado"),
        mudou_tipo=filtros.get("mudou_tipo"),
        sla=filtros.get("sla")
    )

    if not chamados:
        return HTMLResponse("<h4>Sem chamados para exportar.</h4>")

    df = pd.DataFrame(chamados)
    df = df.rename(columns={
        "id": "ID",
        "tipo_ticket": "Tipo",
        "status": "Status",
        "responsavel": "Responsável",
        "abertura": "Abertura",
        "fechamento": "Encerramento",
        "sla": "SLA",
        "capturado_por": "Capturado por",
        "mudou_tipo": "Mudou Tipo?"
    })
    df["Mudou Tipo?"] = df["Mudou Tipo?"].apply(lambda x: "Sim" if x else "Não")

    if tipo == "csv":
        buffer = io.StringIO()
        df.to_csv(buffer, sep=";", index=False)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={
            "Content-Disposition": "attachment; filename=chamados.csv"
        })

    else:  # XLSX
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Chamados")
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
            "Content-Disposition": "attachment; filename=chamados.xlsx"
        })
