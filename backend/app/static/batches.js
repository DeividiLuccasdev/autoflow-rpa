/* Conciliação em lote: cada documento avança no backend e tem auditoria própria. */
let activeBatch = null, batchBusy = false, batchReviewItem = null;
let pendingExampleRequest = null, pendingUploadRequest = null;
const batchLabels = {queued:'Na fila do lote',registered:'Conciliada e confirmada',needs_review:'Revisão necessária',duplicate:'Duplicidade bloqueada',invalid:'Documento inválido',rejected:'Rejeitada'};

async function batchRequest(path, options={}) {
  const response = await fetch('/demo/batches' + path, {...options, headers:{'X-Demo-Session':operationSession, ...(options.headers || {})}, signal:AbortSignal.timeout(90000)});
  if (!response.ok) {
    const data = await response.json();
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Confira os arquivos e campos enviados.');
  }
  return response;
}

async function refreshBatches() {
  try {
    const data = await (await batchRequest('/summary')).json();
    $('batch-budget').textContent = `${data.remaining_batches} de 2 lotes disponíveis nesta sessão temporária`;
    $('batch-history').innerHTML = data.batches.map(batch => `<button type="button" class="batch-history-entry" data-batch-id="${batch.id}"><strong>Lote ${batch.id.slice(0,8)}</strong><span>${batch.version}/${batch.total} documentos · ${batch.metrics.registered} confirmados · ${batch.metrics.needs_review} pendências</span><span>${batch.status === 'processing' ? 'Retomar processamento' : 'Abrir resultados'} ↗</span></button>`).join('');
    document.querySelectorAll('[data-batch-id]').forEach(button => button.onclick = async () => {
      if (batchBusy) return;
      try { activeBatch = await (await batchRequest('/'+button.dataset.batchId)).json(); renderBatch(); openDialog('batch-dialog'); }
      catch(error) { $('batch-launch-error').textContent = error.message; }
    });
  } catch(error) { $('batch-launch-error').textContent = 'Não foi possível atualizar os lotes. ' + error.message; }
}

function renderBatch() {
  if (!activeBatch) return;
  const batch = activeBatch, m = batch.metrics;
  $('batch-progress').value = batch.version; $('batch-progress').max = batch.total;
  $('batch-progress-text').textContent = `${batch.version} de ${batch.total} documentos processados`;
  $('batch-result-title').textContent = batch.status === 'processing' ? 'Conciliação em andamento' : batch.status === 'needs_review' ? 'Processamento concluído com pendências' : 'Lote finalizado';
  $('batch-run-id').textContent = 'LOTE ' + batch.id.slice(0,8).toUpperCase();
  $('batch-metrics').innerHTML = [[m.registered,'Confirmadas'],[m.needs_review,'Para revisão'],[m.duplicate,'Duplicidades'],[m.invalid+m.rejected,'Recusadas']].map(([value,label])=>`<div><strong>${value}</strong><span>${label}</span></div>`).join('');
  $('batch-amount').textContent = currency(Number(m.registered_amount));
  $('batch-items').innerHTML = batch.items.map(item=>`<article class="batch-item"><div><strong>${escapeHTML(item.filename)}</strong><small>${item.invoice ? 'Nota '+escapeHTML(item.invoice.number)+' · '+currency(Number(item.invoice.amount)) : 'Aguardando extração ou documento recusado'}</small></div><span class="operation-status ${item.status === 'registered' ? 'completed' : item.status}">${batchLabels[item.status]}</span><button type="button" class="text-button" data-batch-item="${item.id}" ${item.status === 'queued' ? 'disabled' : ''}>${item.status === 'needs_review' && batch.status !== 'processing' ? 'Revisar' : 'Ver evidências'} ↗</button></article>`).join('');
  document.querySelectorAll('[data-batch-item]').forEach(button=>button.onclick=()=>openBatchItem(button.dataset.batchItem));
  $('batch-orphans').textContent = batch.status === 'processing' ? 'A conferência das linhas do extrato será concluída ao final.' : `${batch.unmatched_statement.length} linha(s) do extrato sem documento correspondente${batch.unmatched_statement.length ? ': '+batch.unmatched_statement.map(row=>'nota '+row.identity.split(':')[1]+' — '+currency(Number(row.amount))).join('; ') : '.'}`;
  $('batch-resume').hidden = batch.status !== 'processing';
  $('batch-resume').disabled = batchBusy;
  $('batch-resume').textContent = batchBusy ? 'Processando documentos…' : 'Retomar processamento →';
  $('batch-report-json').disabled = batch.status === 'processing';
  $('batch-report-csv').disabled = batch.status === 'processing';
}

async function advanceBatch() {
  while (activeBatch.status === 'processing') {
    activeBatch = await (await batchRequest(`/${activeBatch.id}/advance?expected_version=${activeBatch.version}`, {method:'POST'})).json();
    renderBatch();
    await new Promise(resolve=>setTimeout(resolve,220));
  }
}

async function executeBatch(create) {
  if (batchBusy) return;
  batchBusy = true;
  $('batch-launch-error').textContent = ''; $('batch-error').textContent = '';
  $('batch-example').disabled = true; $('batch-upload-submit').disabled = true;
  try {
    if (create) activeBatch = await create();
    renderBatch();
    if (!$('batch-dialog').open) openDialog('batch-dialog');
    await advanceBatch();
    toast(activeBatch.status === 'needs_review' ? 'Lote processado: confira as pendências' : 'Lote finalizado');
  } catch(error) {
    const message = error.message + ' Se a conexão foi interrompida, consulte o lote na lista para retomar sem repetir os documentos já processados.';
    if (activeBatch && $('batch-dialog').open) $('batch-error').textContent = message;
    else { $('batch-launch-error').textContent = message; $('batch-upload-error').textContent = error.message; }
  } finally {
    batchBusy = false; $('batch-example').disabled = false; $('batch-upload-submit').disabled = false;
    if (activeBatch) renderBatch();
    await refreshBatches();
  }
}

function openBatchItem(id) {
  const item = activeBatch?.items.find(item=>item.id===id);
  if (!item || item.status === 'queued') return;
  batchReviewItem = item;
  $('batch-item-title').textContent = item.filename;
  $('batch-item-facts').textContent = item.invoice ? `Nota ${item.invoice.number} · Documento: ${currency(Number(item.invoice.amount))} · Extrato original: ${item.source_amount === null ? 'sem correspondência' : currency(Number(item.source_amount))}` : item.reason;
  $('batch-item-events').innerHTML = item.events.map(event=>`<article class="review-event"><strong>${escapeHTML(event.title)}</strong><p>${escapeHTML(event.message)}</p><small>${new Date(event.time).toLocaleTimeString('pt-BR')}</small></article>`).join('');
  $('batch-review-form').hidden = item.status !== 'needs_review' || activeBatch.status === 'processing';
  const canApprove = item.reason === 'amount_mismatch';
  $('batch-review-amount-label').hidden = !canApprove;
  $('batch-review-amount').hidden = !canApprove; $('batch-review-amount').disabled = !canApprove;
  $('batch-review-amount').required = canApprove;
  $('batch-review-amount').value = item.invoice?.amount || '';
  $('batch-review-approve').hidden = !canApprove;
  $('batch-review-note').textContent = canApprove ? 'Confira o documento e registre a correção na origem simulada antes de confirmar o lançamento.' : 'Sem correspondência no extrato, o lançamento fica bloqueado. Rejeite este documento ou envie outro lote com um extrato corrigido.';
  $('batch-review-reason').value = ''; $('batch-review-error').textContent = '';
  openDialog('batch-item-dialog');
}

async function decideBatchItem(action) {
  if (batchBusy || !batchReviewItem || !$('batch-review-form').reportValidity()) return;
  batchBusy = true;
  document.querySelectorAll('#batch-review-form button').forEach(button=>button.disabled=true);
  $('batch-review-error').textContent='';
  try {
    activeBatch = await (await batchRequest(`/${activeBatch.id}/items/${batchReviewItem.id}/review`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,reason:$('batch-review-reason').value.trim(),...(action==='approve'?{corrected_source_amount:$('batch-review-amount').value}:{})})})).json();
    renderBatch(); $('batch-item-dialog').close(); await refreshBatches(); toast('Decisão registrada na auditoria do lote');
  } catch(error) { $('batch-review-error').textContent=error.message; }
  finally { batchBusy=false; document.querySelectorAll('#batch-review-form button').forEach(button=>button.disabled=false); }
}

async function downloadBatchReport(format) {
  if (!activeBatch) return;
  try {
    const response=await batchRequest(`/${activeBatch.id}/report?format=${format}`);
    const url=URL.createObjectURL(await response.blob()); const link=document.createElement('a');
    link.href=url; link.download=`autoflow-lote-${activeBatch.id}.${format}`; document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  } catch(error) { $('batch-error').textContent=error.message; }
}

$('batch-example').onclick=()=>executeBatch(async()=>{
  activeBatch=null; pendingExampleRequest ||= crypto.randomUUID();
  const data=await (await batchRequest('/example?request_id='+pendingExampleRequest,{method:'POST'})).json();
  pendingExampleRequest=null; return data;
});
$('batch-open-upload').onclick=()=>{ if(!batchBusy)openDialog('batch-upload-dialog'); };
$('batch-upload-form').onchange=()=>{pendingUploadRequest=null;};
$('batch-upload-form').onsubmit=event=>{
  event.preventDefault(); if(batchBusy)return;
  const files=Array.from($('batch-files').files), statement=$('batch-statement').files[0];
  if(!files.length||files.length>6||!statement||files.reduce((sum,file)=>sum+file.size,statement.size)>100000){$('batch-upload-error').textContent='Selecione de um a seis PDFs e um CSV, até 100 KB no total.';return;}
  pendingUploadRequest ||= crypto.randomUUID();
  executeBatch(async()=>{
    activeBatch=null; const data=new FormData(); data.append('request_id',pendingUploadRequest);
    files.forEach(file=>data.append('files',file)); data.append('statement',statement);
    const batch=await (await batchRequest('',{method:'POST',body:data})).json();
    pendingUploadRequest=null; $('batch-upload-dialog').close(); return batch;
  });
};
$('batch-resume').onclick=()=>executeBatch();
$('batch-refresh').onclick=refreshBatches;
$('batch-review-form').onsubmit=event=>{event.preventDefault();decideBatchItem('approve');};
$('batch-review-reject').onclick=()=>decideBatchItem('reject');
$('batch-report-json').onclick=()=>downloadBatchReport('json');
$('batch-report-csv').onclick=()=>downloadBatchReport('csv');
refreshBatches();
