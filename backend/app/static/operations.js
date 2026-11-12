/* Sessão de demonstração: dados fictícios, transições validadas pelo backend. */
const operationLabels = ['Extrair documento','Consultar ERP de origem','Conferir valores','Registrar no ERP de destino','Confirmar o lançamento','Concluir auditoria'];
const scenarioLabels = {success:'Sucesso',divergence:'Divergência',duplicate:'Duplicidade'};
const statusLabels = {running:'Em execução',completed:'Concluída',needs_review:'Em revisão',duplicate:'Duplicidade bloqueada',rejected:'Rejeitada'};
let operationSession;
try {
  operationSession = sessionStorage.getItem('autoflow-automation-session');
  if (!/^[0-9a-f-]{36}$/i.test(operationSession || '')) operationSession = crypto.randomUUID();
  sessionStorage.setItem('autoflow-automation-session', operationSession);
} catch { operationSession = crypto.randomUUID(); }
let operationBusy = false, selectedScenario = 'success', currentRun = null, sessionSummary = null;

async function operationRequest(path, method='GET', body) {
  const response = await fetch('/demo/automation' + path, {
    method, headers: {'X-Demo-Session':operationSession, ...(body ? {'Content-Type':'application/json'} : {})},
    ...(body ? {body:JSON.stringify(body)} : {}), signal:AbortSignal.timeout(90000)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Confira os campos informados e tente novamente.');
  return data;
}

function renderSession(data) {
  sessionSummary = data;
  const m = data.metrics;
  $('session-completed').textContent = m.completed;
  $('session-review').textContent = m.needs_review;
  $('session-duplicates').textContent = m.duplicate;
  $('session-duration').textContent = m.average_completed_seconds === null ? '—' : m.average_completed_seconds.toLocaleString('pt-BR', {maximumFractionDigits:1}) + ' s';
  $('session-volume').textContent = currency(Number(m.registered_amount));
  $('session-budget').textContent = `${data.remaining_runs} de 5 execuções disponíveis · sessão temporária de até 15 minutos`;
  $('session-total').textContent = `${m.total} ${m.total === 1 ? 'execução' : 'execuções'} · ${m.rejected} ${m.rejected === 1 ? 'rejeitada' : 'rejeitadas'}`;
  $('session-error').textContent = '';
  $('session-runs').innerHTML = data.runs.length ? data.runs.map(run => `<article class="session-run"><div><strong>Nota ${escapeHTML(run.invoice?.number || (run.scenario === 'divergence' ? '43' : '42'))} · ${scenarioLabels[run.scenario]}</strong><small>${escapeHTML(run.id.slice(0,8))} · ${run.step}/6 etapas</small></div><span class="operation-status ${run.status}">${statusLabels[run.status]}</span><button type="button" class="text-button" data-operation-id="${escapeHTML(run.id)}">${run.status === 'needs_review' ? 'Revisar e decidir' : run.status === 'running' ? 'Retomar execução' : 'Ver evidências'} ↗</button></article>`).join('') : '<div class="session-empty">Sua sessão ainda não tem execuções. Escolha um cenário abaixo e acompanhe cada etapa.</div>';
  document.querySelectorAll('[data-operation-id]').forEach(button => button.onclick = () => {
    if (operationBusy) return;
    currentRun = data.runs.find(run => run.id === button.dataset.operationId);
    selectedScenario = currentRun.scenario;
    renderOperation(currentRun); openDialog('automation-dialog');
  });
}

async function refreshSession() {
  try { renderSession(await operationRequest('/summary')); }
  catch (error) { $('session-error').textContent = 'Não foi possível atualizar os dados da sessão. ' + error.message; }
}

function renderOperation(run) {
  const events = run?.events || [];
  $('automation-steps').innerHTML = operationLabels.map((label,index) => {
    const item = events.find(event => event.step === index && event.kind !== 'review');
    const waiting = (index === 2 && run?.status === 'needs_review') || (index === 3 && run?.status === 'duplicate');
    return `<div class="automation-step ${waiting ? 'waiting' : item ? 'done' : run?.step === index && run.status === 'running' ? 'active' : ''}"><span>${waiting ? '!' : item ? '✓' : String(index+1).padStart(2,'0')}</span><div>${label}${item ? `<small>${escapeHTML(item.message)}</small>` : ''}</div></div>`;
  }).join('');
  const divergence = (run?.scenario || selectedScenario) === 'divergence';
  $('source-order').textContent = divergence ? 'Conta a pagar CP-2026-0043' : 'Conta a pagar CP-2026-0042';
  $('source-amount').textContent = currency(Number(run?.source.amount || (divergence ? 150 : 123.45)));
  $('source-state').textContent = run?.status === 'needs_review' ? 'Divergência encontrada · aguardando revisão' : run?.step >= 2 ? 'Conta consultada no sistema de origem' : 'Aguardando consulta';
  $('target-count').textContent = `${run?.destination.entries || 0} registro${run?.destination.entries === 1 ? '' : 's'}`;
  $('target-state').textContent = run?.destination.protocol ? `Protocolo ${run.destination.protocol}` : 'Aguardando automação';
  $('selected-scenario').textContent = scenarioLabels[run?.scenario || selectedScenario];
  $('review-form').hidden = run?.status !== 'needs_review' || run?.step !== 3;
  if (run?.status === 'needs_review') {
    $('review-comparison').textContent = `Nota: ${currency(Number(run.invoice.amount))} · Origem: ${currency(Number(run.source.amount))}. Nenhum lançamento foi criado por esta execução.`;
    $('review-amount').value = run.invoice.amount;
  }
  $('review-audit').innerHTML = events.filter(event => event.kind === 'review').map(event => `<div class="review-event"><strong>${escapeHTML(event.title)}</strong><p>${escapeHTML(event.message)}</p></div>`).join('');
  const button = $('automation-start');
  $('download-evidence').hidden = !run;
  button.hidden = !!run && run.status !== 'running';
  button.disabled = operationBusy;
  button.textContent = operationBusy ? 'Automação em andamento…' : run ? 'Retomar execução →' : 'Iniciar cenário →';
  const messages = {completed:['Automação concluída','Documento conferido, registrado e confirmado no destino simulado.'], duplicate:['Duplicidade bloqueada','A tentativa foi interrompida antes de criar outro lançamento. O protocolo original foi preservado.'], needs_review:['Revisão humana necessária','O valor da origem difere da nota. Corrija e aprove ou rejeite com uma justificativa.'], rejected:['Documento rejeitado','A decisão foi registrada na auditoria. Esta execução não criou um lançamento.']};
  const message = run && messages[run.status];
  $('automation-summary').innerHTML = message ? `<div class="result-card ${run.status === 'needs_review' ? 'review-result' : ''}"><strong>${message[0]}</strong><p>${message[1]}</p>${run.destination.protocol ? `<p>Protocolo: ${escapeHTML(run.destination.protocol)}</p>` : ''}</div>` : '';
}

function selectScenario(scenario) {
  if (operationBusy) return;
  selectedScenario = scenario; currentRun = null;
  $('review-reason').value = '';
  renderOperation();
  if (scenario === 'duplicate' && !sessionSummary?.runs.some(run => run.scenario === 'success' && run.status === 'completed')) {
    $('automation-summary').innerHTML = '<div class="scope-note"><strong>Primeiro, conclua o cenário de sucesso.</strong><p>A duplicidade usa o lançamento e o protocolo dessa execução para comprovar que um segundo registro é bloqueado.</p></div>';
    $('automation-start').disabled = true;
  }
  openDialog('automation-dialog');
}

async function continueOperation() {
  while (currentRun.status === 'running') {
    currentRun = await operationRequest(`/runs/${currentRun.id}/advance?expected_step=${currentRun.step}`, 'POST');
    renderOperation(currentRun);
    await new Promise(resolve => setTimeout(resolve,250));
  }
  await refreshSession();
  toast(statusLabels[currentRun.status]);
}

async function executeOperation() {
  if (operationBusy) return;
  operationBusy = true;
  try {
    renderOperation(currentRun);
    if (!currentRun) currentRun = await operationRequest('/runs?scenario=' + selectedScenario,'POST');
    await continueOperation();
  } catch(error) {
    $('automation-summary').innerHTML = `<div class="result-card error"><strong>Execução interrompida</strong><p>${escapeHTML(error.message)}</p><p>Se houve falha de conexão, retome esta execução para consultar o estado confirmado pelo servidor.</p></div>`;
    await refreshSession();
  } finally {
    operationBusy = false;
    $('automation-start').disabled = false;
    $('automation-start').textContent = currentRun ? 'Retomar execução →' : 'Tentar iniciar cenário →';
  }
}

async function submitReview(action) {
  if (operationBusy || !currentRun || !$('review-form').reportValidity()) return;
  operationBusy = true;
  document.querySelectorAll('#review-form button').forEach(button => button.disabled = true);
  $('review-error').textContent = '';
  try {
    currentRun = await operationRequest(`/runs/${currentRun.id}/review`,'POST', {action, expected_step:currentRun.step, reason:$('review-reason').value.trim(), ...(action === 'approve' ? {corrected_source_amount:$('review-amount').value} : {})});
    renderOperation(currentRun);
    if (currentRun.status === 'running') await continueOperation();
    else await refreshSession();
  } catch(error) {
    if (currentRun?.status === 'needs_review') $('review-error').textContent = error.message;
    else $('automation-summary').innerHTML = `<div class="result-card error"><strong>Não foi possível continuar</strong><p>${escapeHTML(error.message)}</p><p>Retome a execução para consultar o estado confirmado pelo servidor.</p></div>`;
    await refreshSession();
  }
  finally {
    operationBusy = false;
    document.querySelectorAll('#review-form button').forEach(button => button.disabled = false);
    if (currentRun?.status === 'running') { $('automation-start').hidden = false; $('automation-start').disabled = false; $('automation-start').textContent = 'Retomar execução →'; }
  }
}

$('automation-start').onclick = executeOperation;
['new-execution','hero-start'].forEach(id => $(id).onclick = () => selectScenario('success'));
document.querySelectorAll('[data-scenario]').forEach(button => button.onclick = () => selectScenario(button.dataset.scenario));
$('review-form').onsubmit = event => { event.preventDefault(); submitReview('approve'); };
$('review-reject').onclick = () => submitReview('reject');
$('refresh-session').onclick = refreshSession;
$('download-evidence').onclick = () => {
  if (!currentRun) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify({scope:'Demonstração com dados fictícios e sistemas simulados', ...currentRun},null,2)],{type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = `autoflow-${currentRun.id}.json`;
  document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
};
refreshSession();
