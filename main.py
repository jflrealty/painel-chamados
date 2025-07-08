<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <title>Painel de Chamados</title>

  <!-- Bootstrap -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css">

  <style>
    body          { background:#f8f9fa; padding:20px }
    .card-metric  { min-width:180px; cursor:pointer; text-decoration:none; color:inherit }
    table td,th   { vertical-align:middle }
    .modal-thread { display:none; position:fixed; top:10%; left:10%; width:80%; height:80%;
                    background:#fff; padding:20px; border:2px solid #444; overflow:auto; z-index:1000 }
  </style>
</head>
<body>

  <!-- Botão “Home” -->
  <div class="mb-3">
    <a class="btn btn-outline-dark" href="/painel">🏠 Home</a>
  </div>

  <h2 class="mb-4">Painel de Chamados</h2>

  <!-- ░░░ Cards Métricas ░░░ -->
  <div class="d-flex flex-wrap gap-4 mb-4">
    {% for key,label,color,qs in [
        ('total','Total','',        'page=1'),                              # total = home
        ('em_atendimento','Em Atendimento','warning','so_ema=1'),
        ('finalizados','Finalizados','success',     'so_fin=1'),
        ('fora_sla','Fora do SLA','danger',        'so_sla=1'),
        ('mudaram_tipo','Alteraram&nbsp;Tipo','info','so_mud=1')
      ] %}
      <a href="/painel?{{ qs }}" class="card card-metric shadow-sm text-center">
        <div class="card-body">
          <h6 class="card-title">{{ label|safe }}</h6>
          <p class="fs-4 text-{{ color }}">{{ metricas[key] }}</p>
        </div>
      </a>
    {% endfor %}
  </div>

  <!-- ░░░ Filtros ░░░ -->
  <form method="get" action="/painel" class="row g-3 mb-4">
    <!-- Status -->
    <div class="col-md-2">
      <label class="form-label">Status</label>
      <select name="status" class="form-select">
        {% for s in ['','Aberto','Em Atendimento','Finalizado','Cancelado'] %}
          <option value="{{ s }}" {% if filtros.status==s %}selected{% endif %}>
            {{ 'Todos' if not s else s }}
          </option>
        {% endfor %}
      </select>
    </div>
    <!-- Responsável -->
    <div class="col-md-2">
      <label class="form-label">Responsável</label>
      <select name="responsavel" class="form-select">
        <option value="">Todos</option>
        {% for r in responsaveis %}
          <option value="{{ r }}" {% if filtros.responsavel==r %}selected{% endif %}>{{ r }}</option>
        {% endfor %}
      </select>
    </div>
    <!-- Capturado por -->
    <div class="col-md-2">
      <label class="form-label">Capturado por</label>
      <select name="capturado" class="form-select">
        <option value="">Todos</option>
        {% for c in capturadores %}
          <option value="{{ c }}" {% if filtros.capturado==c %}selected{% endif %}>{{ c }}</option>
        {% endfor %}
      </select>
    </div>
    <!-- Mudou Tipo -->
    <div class="col-md-2">
      <label class="form-label">Mudou Tipo?</label>
      <select name="mudou_tipo" class="form-select">
        <option value=""    {% if not filtros.mudou_tipo %}selected{% endif %}>Todos</option>
        <option value="sim" {% if filtros.mudou_tipo=='sim' %}selected{% endif %}>Sim</option>
        <option value="nao" {% if filtros.mudou_tipo=='nao' %}selected{% endif %}>Não</option>
      </select>
    </div>
    <!-- Datas -->
    <div class="col-md-2">
      <label class="form-label">Data Início</label>
      <input type="date" name="data_ini" class="form-control" value="{{ filtros.data_ini or '' }}">
    </div>
    <div class="col-md-2">
      <label class="form-label">Data Fim</label>
      <input type="date" name="data_fim" class="form-control" value="{{ filtros.data_fim or '' }}">
    </div>
    <div class="col-12 d-flex justify-content-end">
      <button class="btn btn-primary mt-2">Filtrar</button>
    </div>
  </form>

  <!-- ░░░ Tabela ░░░ -->
  <div class="table-responsive">
    <table class="table table-bordered table-striped bg-white shadow-sm">
      <thead class="table-light">
        <tr>
          <th>ID</th><th>Tipo</th><th>Status</th><th>Responsável</th>
          <th>Abertura</th><th>Encerramento</th>
          <th>SLA</th><th>Capturado por</th><th>Δ Tipo</th><th>Ação</th>
        </tr>
      </thead>
      <tbody>
      {% for ch in chamados %}
        <tr>
          <td>{{ ch.id }}</td>
          <td>{{ ch.tipo_ticket }}</td>
          <td>{{ ch.status }}</td>
          <td>{{ ch.responsavel }}</td>
          <td>{{ ch.abertura }}</td>
          <td>{{ ch.fechamento }}</td>
          <td class="text-center">
            {% if ch.sla|lower == 'dentro do sla' %}
              <span class="badge bg-success">✔</span>
            {% elif ch.sla|lower == 'fora' or ch.sla|lower == 'fora do sla' %}
              <span class="badge bg-danger">✘</span>
            {% else %}-{% endif %}
          </td>
          <td>
            {% if ch.capturado_por == "<não capturado>" %}
              <i>&lt;não capturado&gt;</i>
            {% else %}
              {{ ch.capturado_por }}
            {% endif %}
          </td>
          <td class="text-center">
            {% if ch.mudou_tipo %}<span class="badge bg-info">⚡</span>{% else %}-{% endif %}
          </td>
          <td>
            <button class="btn btn-sm btn-outline-primary"
                    onclick="verThread('{{ ch.canal_id }}','{{ ch.thread_ts }}')">
              Ver Thread
            </button>
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Paginação -->
  {% if paginas_totais > 1 %}
  <nav class="mt-4">
    <ul class="pagination justify-content-center">
      {% for p in range(max(1, pagina_atual-2), min(paginas_totais+1, pagina_atual+3)) %}
        <li class="page-item {% if p == pagina_atual %}active{% endif %}">
          <a class="page-link" href="{{ url_paginacao }}&page={{ p }}">{{ p }}</a>
        </li>
      {% endfor %}
    </ul>
  </nav>
  {% endif %}

  <!-- ░░░ Modal Thread ░░░ -->
  <div id="modal" class="modal-thread">
    <button class="btn btn-secondary mb-2" onclick="fecharModal()">Fechar</button>
    <div id="modal-content"></div>
  </div>

  <script>
    async function verThread(canal, ts){
      const fd  = new FormData();
      fd.append("canal_id", canal);
      fd.append("thread_ts", ts);
      const rsp = await fetch("/thread", {method:"POST", body:fd});
      document.getElementById("modal-content").innerHTML = await rsp.text();
      document.getElementById("modal").style.display = "block";
    }
    function fecharModal(){ document.getElementById("modal").style.display = "none"; }
  </script>
</body>
</html>
