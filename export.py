# export.py – rotas de exportação CSV / XLSX
import io, pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from utils.db_helpers import carregar_chamados   # <- sem loop!

export_router = APIRouter()

@export_router.get("/exportar", response_class=HTMLResponse)
async def exportar(request: Request, tipo: str = "xlsx", **filtros):
    # mesmo conjunto de filtros do painel
    chamados = carregar_chamados(
        status      = filtros.get("status"),
        resp_nome   = filtros.get("responsavel"),
        d_ini       = filtros.get("data_ini"),
        d_fim       = filtros.get("data_fim"),
        capturado   = filtros.get("capturado"),
        mudou_tipo  = filtros.get("mudou_tipo"),
        sla         = filtros.get("sla"),
    )
    if not chamados:
        return HTMLResponse("<h4>Sem chamados para exportar.</h4>")

    df = (pd.DataFrame(chamados)
            .rename(columns={
                "id":"ID","tipo_ticket":"Tipo","status":"Status",
                "responsavel":"Responsável", "abertura":"Abertura",
                "fechamento":"Encerramento", "sla":"SLA",
                "capturado_por":"Capturado por", "mudou_tipo":"Mudou Tipo?"
            }))
    df["Mudou Tipo?"] = df["Mudou Tipo?"].map({True:"Sim", False:"Não"})

    if tipo.lower() == "csv":
        buf = io.StringIO(); df.to_csv(buf, sep=";", index=False); buf.seek(0)
        return StreamingResponse(buf, media_type="text/csv",
            headers={"Content-Disposition":"attachment; filename=chamados.csv"})
    # default xlsx
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as wr:
        df.to_excel(wr, index=False, sheet_name="Chamados")
    buf.seek(0)
    return StreamingResponse(buf,
        media_type=("application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"),
        headers={"Content-Disposition":"attachment; filename=chamados.xlsx"})
