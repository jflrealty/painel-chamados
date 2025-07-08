# export.py – rotas de exportação CSV / XLSX
import io
import pandas as pd
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from utils.db_helpers import carregar_chamados
from typing import Optional

export_router = APIRouter()

@export_router.get("/exportar", response_class=HTMLResponse)
async def exportar(
    request: Request,
    tipo: str = "xlsx",
    status: Optional[str] = Query(None),
    responsavel: Optional[str] = Query(None),
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    capturado: Optional[str] = Query(None),
    mudou_tipo: Optional[str] = Query(None),
    sla: Optional[str] = Query(None),
):
    chamados = carregar_chamados(
        status=status,
        resp=responsavel,
        d_ini=data_ini,
        d_fim=data_fim,
        capturado=capturado,
        mudou_tipo=mudou_tipo,
        sla=sla
    )

    if not chamados:
        return HTMLResponse("<h4>Sem chamados para exportar.</h4>")

    df = pd.DataFrame(chamados).rename(columns={
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
    df["Mudou Tipo?"] = df["Mudou Tipo?"].map({True: "Sim", False: "Não"})

    if tipo.lower() == "csv":
        buf = io.StringIO()
        df.to_csv(buf, sep=";", index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=chamados.csv"}
        )

    # XLSX (default)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Chamados")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=chamados.xlsx"}
    )
