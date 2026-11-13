from time import monotonic
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.voice_assistant import sessions, lock, TTL
from test_invoices import client


def login(http,re="05"):
    response=http.post('/assistant/login',json={'re':re,'password':'AutoflowDemo2026!'})
    assert response.status_code==200,response.text
    return {'X-Voice-CSRF':response.json()['csrf_token']}


def test_login_requires_re_password_and_cookie(client):
    http,_=client
    assert http.get('/assistant/me').status_code==401
    assert http.post('/assistant/login',json={'re':'05','password':'wrong'}).status_code==401
    assert http.post('/assistant/login',json={'re':'99','password':'AutoflowDemo2026!'}).status_code==401
    assert http.post('/assistant/login',json={'re':'05','password':'AutoflowDemo2026!','role':'Supervisor'}).status_code==422
    secret='sensitive-test-'*20
    rejected=http.post('/assistant/login',json={'re':'05','password':secret})
    assert rejected.status_code==422 and secret not in rejected.text
    headers=login(http)
    assert http.get('/assistant/me').json()['profile']['role']=='Funcionário'
    assert http.post('/assistant/query',json={'text':'listar minhas notas'}).status_code==403
    result=http.post('/assistant/query',headers=headers,json={'text':'listar minhas notas'})
    assert result.status_code==200 and result.json()['count']==4
    assert http.post('/assistant/login',json={'re':'5','password':'AutoflowDemo2026!'}).status_code==422
    assert http.post('/assistant/login',json={'re':'1001','password':'AutoflowDemo2026!'}).status_code==422


@pytest.mark.parametrize('re,expected',[('05',2),('10',2)])
def test_same_query_respects_profile(client,re,expected):
    http,_=client; headers=login(http,re)
    response=http.post('/assistant/query',headers=headers,json={'text':'Busque as notas do CPF 00000000001'})
    assert response.status_code==200 and response.json()['count']==expected
    exclusive={'address','phone','total_debt','remaining_installments'}
    for document in response.json()['documents']:
        assert document['debtor_name'] and document['outstanding_amount']
        assert exclusive.issubset(document) if re=='10' else exclusive.isdisjoint(document)


@pytest.mark.parametrize('re',['05','10'])
def test_detail_and_pdf_apply_field_permissions(client,re):
    import pymupdf
    http,_=client; login(http,re)
    response=http.get('/assistant/documents/nf-101',headers={'X-RE':'10'})
    assert response.status_code==200
    data=response.json()
    assert data['debtor_name']=='Aurora Horizonte Serviços Demonstrativos Ltda.'
    assert data['outstanding_amount']=='123.45'
    pdf=http.get('/assistant/documents/nf-101/pdf')
    assert pdf.status_code==200 and 'no-store' in pdf.headers['cache-control']
    with pymupdf.open(stream=pdf.content,filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
    for key,value in [('address','Endereco ficticio:'),('phone','Telefone ficticio:'),('total_debt','Divida total:'),('remaining_installments','Parcelas restantes:')]:
        assert (key in data)==(re=='10')
        assert (value in text)==(re=='10')
    assert 'Valor devedor da nota: R$ 123.45' in text
    assert http.get('/assistant/documents/unknown').status_code==404


def test_voice_transcript_digit_words_and_punctuation(client):
    http,_=client; headers=login(http,'10')
    phrases=['Notas do C P F zero zero zero zero zero zero zero zero zero zero um','Busque CPF 000.000.000-01']
    for text in phrases:
        result=http.post('/assistant/query',headers=headers,json={'text':text})
        assert result.status_code==200 and result.json()['count']==2
    assert http.post('/assistant/query',headers=headers,json={'text':'nota um zero quatro'}).json()['documents'][0]['number']=='104'
    assert http.post('/assistant/query',headers=headers,json={'text':'busque a nota zero zero um zero um'}).json()['documents'][0]['number']=='101'
    assert http.post('/assistant/query',headers=headers,json={'text':'última nota do CPF 00000000001'}).json()['documents'][0]['number']=='102'
    assert http.post('/assistant/query',headers=headers,json={'text':'notas do CNPJ 12.345.678/0001-95'}).json()['count']==2


@pytest.mark.parametrize('text',['CPF 2223457899','CNPJ 123','qualquer coisa','CPF 00000000001 e 00000000002'])
def test_unclear_identifiers_not_guessed(client,text):
    http,_=client; headers=login(http)
    assert http.post('/assistant/query',headers=headers,json={'text':text}).status_code==422


def test_document_and_pdf_require_authentication(client):
    http,_=client
    assert http.get('/assistant/documents/nf-101').status_code==401
    assert http.get('/assistant/documents/nf-101/pdf').status_code==401
    assert http.get('/assistant/history').status_code==401


def test_logout_revokes_session_and_history_is_scoped(client):
    http,_=client; headers=login(http)
    http.post('/assistant/query',headers=headers,json={'text':'nota 101'})
    events=http.get('/assistant/history').json()['events']
    assert any(event['action']=='query' for event in events)
    assert all(event['re']=='05' for event in events)
    assert '00000000001' not in str(events)
    assert http.post('/assistant/logout',headers=headers).status_code==204
    assert http.get('/assistant/documents/nf-101').status_code==401
    login(http,'10')
    assert all(event['re']=='10' for event in http.get('/assistant/history').json()['events'])


def test_expiry_and_microphone_policy(client):
    http,_=client; login(http)
    with lock:
        for session in sessions.values(): session['started']=monotonic()-TTL-1
    assert http.get('/assistant/me').status_code==401
    page=http.get('/assistente')
    assert page.status_code==200 and 'microphone=(self)' in page.headers['permissions-policy']
    assert 'microphone=()' in http.get('/').headers['permissions-policy']
    assert http.get('/assets/assistant.js').status_code==200


def test_voice_cookie_does_not_unlock_private_api(client):
    http,_=client; login(http,'10'); http.headers.pop('X-API-Key')
    assert http.get('/api/v1/invoices').status_code==401
