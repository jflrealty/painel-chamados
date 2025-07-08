# =======================
# 📁 export.py – Exportação do Painel
# =======================
import os
from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from utils.export_helpers import gerar_pdf, gerar_csv, gerar_xlsx
from utils.db_helpers import carregar_chamados

export_router = APIRouter()

@export_router.get("/exportar")
async def exportar(request: Request, tipo: str, formato: str,
                   status: str | None = None,
                   responsavel: str | None = None,
                   data_ini: str | None = None,
                   data_fim: str | None = None,
                   capturado: str | None = None,
                   mudou_tipo: str | None = None,
                   sla: str | None = None):

    base_filtros = dict(
        status=status,
        resp=responsavel,
        d_ini=data_ini,
        d_fim=data_fim,
        capturado=capturado,
        mudou_tipo=mudou_tipo,
        sla=sla,
    )
    chamados = carregar_chamados(**base_filtros)

    filename = f"export_{tipo}.{formato}"
    caminho = f"tmp/{filename}"

    os.makedirs("tmp", exist_ok=True)
    if formato == "pdf":
        gerar_pdf(chamados, caminho, titulo="Relatório de Chamados")
    elif formato == "csv":
        gerar_csv(chamados, caminho)
    elif formato == "xlsx":
        gerar_xlsx(chamados, caminho)
    else:
        return Response("Formato inválido", status_code=400)

    return FileResponse(caminho, filename=filename, media_type="application/octet-stream")
