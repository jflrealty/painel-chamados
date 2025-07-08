# export.py – /exportar?tipo=csv|xlsx&...filtros
import io, pandas as pd
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from utils.db_helpers import carregar_chamados

export_router = APIRouter()

@export_router.get("/exportar", response_class=HTMLResponse)
async def exportar(
    request:      Request,
    tipo:         str  = Query("xlsx", pattern="^(xlsx|csv)$"),
    status:       Optional[str] = None,
    responsavel:  Optional[str] = None,
    data_ini:     Optional[str] = None,
    data_fim:     Optional[str] = None,
    capturado:    Optional[str] = None,
    mudou_tipo:   Optional[str] = None,
    sla:          Optional[str] = None,
):
    dados = carregar_chamados(
        status=status, resp=responsavel,
        d_ini=data_ini, d_fim=data_fim,
        capturado=capturado, mudou_tipo=mudou_tipo, sla=sla
    )
    if not dados:
        return HTMLResponse("<h4>Sem chamados para exportar.</h4>")

    df = pd.DataFrame(dados).rename(columns={
        "id":"ID","tipo_ticket":"Tipo","status":"Status",
        "responsavel":"Responsável","abertura":"Abertura",
        "fechamento":"Encerramento","sla":"SLA",
        "capturado_por":"Capturado por","mudou_tipo":"Mudou Tipo?"
    })
    df["Mudou Tipo?"] = df["Mudou Tipo?"].map({True:"Sim", False:"Não"})

    if tipo == "csv":
        buf = io.StringIO(); df.to_csv(buf, sep=";", index=False); buf.seek(0)
        return StreamingResponse(buf, media_type="text/csv",
            headers={"Content-Disposition":"attachment; filename=chamados.csv"})
    # default XLSX
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as wr:
        df.to_excel(wr, index=False, sheet_name="Chamados")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=chamados.xlsx"}
    )
