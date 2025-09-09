<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <title>Dashboards</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { background:#f8f9fa; padding:30px }
    canvas { background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.05); }
    h2 { margin-bottom: 30px; }
  </style>
</head>
<body>
  <div class="mb-4 d-flex gap-2">
    <a class="btn btn-outline-dark" href="/painel">🏠 Home</a>
    <a class="btn btn-outline-primary" href="/dashboards">📊 Dashboards</a>
  </div>

  <h2>📊 Painel de Dashboards</h2>

  <form class="row g-2 mb-4" id="formFiltros">
    <div class="col-md-3">
      <label class="form-label">Data Início</label>
      <input type="date" id="filtroDataIni" class="form-control">
    </div>
    <div class="col-md-3">
      <label class="form-label">Data Fim</label>
      <input type="date" id="filtroDataFim" class="form-control">
    </div>
    <div class="col-md-3">
      <label class="form-label">Responsável</label>
      <select id="filtroResponsavel" class="form-select"></select>
    </div>
    <div class="col-md-3 d-flex align-items-end">
      <button type="submit" class="btn btn-primary w-100">🔄 Atualizar Dashboards</button>
    </div>
  </form>

  <div class="row g-4">
    <div class="col-md-6">
      <canvas id="chartStatus"></canvas>
    </div>
    <div class="col-md-6">
      <canvas id="chartResponsavel"></canvas>
    </div>
    <div class="col-md-6">
      <canvas id="chartTipo"></canvas>
    </div>
    <div class="col-md-6">
      <canvas id="chartSLACaptura"></canvas>
    </div>
    <div class="col-md-6">
      <canvas id="chartSLAEncerramento"></canvas>
    </div>
    <div class="col-md-6">
      <canvas id="chartMensal"></canvas>
    </div>
    <div class="col-md-6">
      <canvas id="chartVendedor"></canvas>
    </div>
  </div>

  <script>
    const chamadosOriginais = {{ dados | tojson | safe }};

    function agruparPor(lista, chave) {
      return lista.reduce((acc, item) => {
        const valor = item[chave] || '<não definido>';
        acc[valor] = (acc[valor] || 0) + 1;
        return acc;
      }, {});
    }

    function calcularSLAMedio(dados, inicioCampo, fimCampo) {
      let totalHoras = 0;
      let totalValidos = 0;
      dados.forEach(c => {
        const ini = new Date(c[inicioCampo]);
        const fim = new Date(c[fimCampo]);
        if (!isNaN(ini) && !isNaN(fim)) {
          const horas = (fim - ini) / 3600000;
          if (horas >= 0 && horas < 999) {
            totalHoras += horas;
            totalValidos++;
          }
        }
      });
      return totalValidos ? (totalHoras / totalValidos).toFixed(2) : "0.00";
    }

    function agruparPorMes(dados, campo) {
      return dados.reduce((acc, c) => {
        const dt = new Date(c[campo]);
        if (!isNaN(dt)) {
          const mes = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}`;
          acc[mes] = (acc[mes] || 0) + 1;
        }
        return acc;
      }, {});
    }

    function plotarBarChart(id, titulo, dados, cor = 'rgba(54, 162, 235, 0.7)') {
      const ctx = document.getElementById(id);
      const labels = Object.keys(dados);
      const values = Object.values(dados);
      new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ label: titulo, data: values, backgroundColor: cor, borderRadius: 5 }] },
        options: {
          responsive: true,
          plugins: { legend: { display: false }, title: { display: true, text: titulo } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
        }
      });
    }

    function plotarGaugeChart(id, titulo, valor) {
      const ctx = document.getElementById(id);
      new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: ['SLA Médio', 'Restante'],
          datasets: [{
            data: [valor, 24 - valor],
            backgroundColor: ['#198754', '#e9ecef'],
            cutout: '80%'
          }]
        },
        options: {
          plugins: {
            legend: { display: false },
            title: { display: true, text: `${titulo}: ${valor}h` }
          }
        }
      });
    }

    function atualizarDashboards() {
      const ini = document.getElementById('filtroDataIni').value;
      const fim = document.getElementById('filtroDataFim').value;
      const resp = document.getElementById('filtroResponsavel').value;

      let dados = [...chamadosOriginais];

      if (ini) dados = dados.filter(c => new Date(c.abertura_raw) >= new Date(ini));
      if (fim) dados = dados.filter(c => new Date(c.abertura_raw) <= new Date(fim));
      if (resp) dados = dados.filter(c => c.responsavel === resp);

      document.querySelectorAll('canvas').forEach(c => c.replaceWith(c.cloneNode(true)));

      plotarBarChart('chartStatus', 'Volume por Status', agruparPor(dados, 'status'));
      plotarBarChart('chartResponsavel', 'Volume por Responsável', agruparPor(dados, 'responsavel'));
      plotarBarChart('chartTipo', 'Volume por Tipo de Chamado', agruparPor(dados, 'tipo_ticket'));
      plotarGaugeChart('chartSLACaptura', 'SLA Médio para Captura', parseFloat(calcularSLAMedio(dados, 'abertura_raw', 'captura_raw')));
      plotarGaugeChart('chartSLAEncerramento', 'SLA Médio para Encerramento', parseFloat(calcularSLAMedio(dados, 'abertura_raw', 'fechamento_raw')));
      plotarBarChart('chartMensal', 'Volume de Chamados por Mês', agruparPorMes(dados, 'abertura_raw'));
      plotarBarChart('chartVendedor', 'Volume por Vendedor', agruparPor(dados, 'solicitante'));
    }

    document.getElementById('formFiltros').addEventListener('submit', e => {
      e.preventDefault();
      atualizarDashboards();
    });

    const selectResp = document.getElementById('filtroResponsavel');
    const responsaveis = [...new Set(chamadosOriginais.map(c => c.responsavel))].sort();
    responsaveis.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r;
      opt.textContent = r;
      selectResp.appendChild(opt);
    });

    atualizarDashboards();
  </script>
</body>
</html>
