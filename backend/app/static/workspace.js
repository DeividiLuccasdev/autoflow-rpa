'use strict';
let csrf = '';
const $ = id => document.getElementById(id);
function message(text) { $('message').textContent = text; }
function signedOut() { csrf = ''; $('access').hidden = false; $('private').hidden = true; $('account-email').textContent = ''; for (const id of ['invoice-list','event-list','execution-list']) $(id).replaceChildren(); }
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (csrf && options.method && options.method !== 'GET') headers.set('X-CSRF-Token', csrf);
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin', cache: 'no-store' });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') signedOut();
    throw new Error(typeof body?.detail === 'string' ? body.detail : 'Confira os campos e tente novamente.');
  }
  return body;
}
function json(body) { return { method: 'POST', headers: {'Content-Type':'application/json'}, body:JSON.stringify(body) }; }
function listItem(text) { const item=document.createElement('li'); item.textContent=text; return item; }
async function load() {
  const invoices=await api('/api/v1/invoices?limit=100');
  $('invoice-list').replaceChildren();
  for (const invoice of invoices) {
    const row=document.createElement('tr');
    for (const text of [`${invoice.number} / ${invoice.series}`,invoice.issuer_cnpj,Number(invoice.amount).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})]) { const cell=document.createElement('td');cell.textContent=text;row.append(cell); }
    const cell=document.createElement('td'), button=document.createElement('button');button.type='button';button.className='secondary';button.textContent='Ver eventos';
    button.addEventListener('click',async()=>{try{const events=await api(`/api/v1/invoices/${encodeURIComponent(invoice.id)}/events`);$('event-list').replaceChildren(...events.map(event=>listItem(`${new Date(event.created_at).toLocaleString('pt-BR')} · ${event.event} · ${event.actor}`)));}catch(error){message(error.message);}});
    cell.append(button);row.append(cell);$('invoice-list').append(row);
  }
  if (!invoices.length) {const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=4;cell.textContent='Você ainda não possui notas. Envie um PDF fictício para começar.';row.append(cell);$('invoice-list').append(row);}
  const executions=await api('/api/v1/executions?limit=100');
  $('execution-list').replaceChildren(...(executions.length?executions.map(run=>listItem(`${run.status} · ${run.id}${run.error?' · '+run.error:''}`)):[listItem('Nenhuma execução na fila.') ]));
}
async function enter(account) { csrf=account.csrf_token;$('account-email').textContent=account.email;$('access').hidden=true;$('private').hidden=false;await load(); }
function bindForm(id, action) { $(id).addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('button[type=submit]');button.disabled=true;message('');try{await action(new FormData(form),form);}catch(error){message(error.message);}finally{button.disabled=false;}}); }
for (const mode of ['login','register']) $('tab-'+mode).addEventListener('click',()=>{for(const name of ['login','register']){$(name+'-form').hidden=name!==mode;$('tab-'+name).classList.toggle('selected',name===mode);}message('');});
bindForm('login-form',async(data,form)=>{const account=await api('/auth/login',json(Object.fromEntries(data)));form.reset();await enter(account);message('Sessão iniciada.');});
bindForm('register-form',async(data,form)=>{await api('/auth/register',json(Object.fromEntries(data)));form.reset();$('tab-login').click();message('Conta ativada. Entre com seu e-mail e senha.');});
bindForm('invite-form',async(data,form)=>{try{const invitation=await api('/auth/invitations',{...json({email:data.get('email')}),headers:{'Content-Type':'application/json','X-API-Key':data.get('key')}});$('invitation-result').hidden=false;$('invitation-result').querySelector('input').value=invitation.invitation;message('Convite gerado. Compartilhe o código em um canal privado com o destinatário. Expira em 24 horas.');}finally{form.elements.key.value='';}});
bindForm('upload-form',async(data,form)=>{await api('/api/v1/invoices/upload',{method:'POST',body:data});form.reset();await load();message('Documento validado e salvo na sua conta.');});
$('refresh').addEventListener('click',()=>load().catch(error=>message(error.message)));
$('logout').addEventListener('click',async()=>{try{await api('/auth/logout',{method:'POST'});signedOut();message('Sessão encerrada.');}catch(error){message(error.message);}});
api('/auth/me').then(enter).catch(error=>{signedOut();if(!['Sessão inválida ou expirada','Credencial inválida'].includes(error.message))message(error.message);});
