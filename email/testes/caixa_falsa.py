# -*- coding: utf-8 -*-
"""
Caixa de entrada de mentira, em portugues, para os testes do Assistente de
E-mail: pessoal, promocao, newsletter com List-Unsubscribe, spam, cobranca com
boleto em PDF, charset latin-1, HTML sem texto, conversa com respostas,
convite de calendario, anexo grande e remetente sem assunto.
"""
import os
import sys
import random
import functools
import email.utils
from email.message import EmailMessage
from email.policy import SMTP
from email import message_from_bytes

from servidor_falso import Msg

_UTIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "utilidades")
sys.path.insert(0, _UTIL)
import leitura  # noqa: E402


def linha_digitavel(valor_centavos=123456, fator=9999):
    """Linha digitavel de 47 digitos do Itau (341) com os digitos verificadores certos."""
    c1, c2, c3 = "341910000", "0000000000", "1234567890"
    return (c1 + str(leitura._mod10(c1)) + c2 + str(leitura._mod10(c2)) + c3 + str(leitura._mod10(c3))
            + "1" + "%04d" % fator + "%010d" % valor_centavos)


def formata(l):
    return f"{l[0:5]}.{l[5:10]} {l[10:15]}.{l[15:21]} {l[21:26]}.{l[26:32]} {l[32]} {l[33:]}"


def pdf_com_texto(linhas):
    """PDF de uma pagina feito a mao (Helvetica), que o pypdf sabe ler."""
    conteudo = "BT /F1 12 Tf 50 750 Td 14 TL\n" + "".join(
        "(%s) Tj T*\n" % l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for l in linhas) + "ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo.encode("latin-1") + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def _base(de, para, assunto, data="Fri, 23 Oct 2026 09:00:00 -0300", mid=None, **extra):
    m = EmailMessage(policy=SMTP)
    m["From"] = de
    m["To"] = para
    if assunto is not None:
        m["Subject"] = assunto
    m["Date"] = data
    m["Message-ID"] = mid or email.utils.make_msgid(domain="falso.test")
    for k, v in extra.items():
        m[k.replace("_", "-")] = v
    return m


CRLF = b"\r\n"
DONO = "gui@falso.test"
LINHA = linha_digitavel()
GRANDE = 3 * 1024 * 1024


@functools.lru_cache(maxsize=4)
def mensagens(dono=DONO):
    """[(chave, bytes_da_mensagem, flags)] na ordem de chegada (a ultima e' a mais nova)."""
    out = []

    m = _base("Maria Souza <maria@familia.com.br>", dono, "Jantar de sábado?", mid="<jantar@falso.test>")
    m.set_content("Oi, Gui!\n\nVamos jantar lá em casa no sábado às 20h? A vovó faz o pão de queijo.\n\nBeijos,\nMaria\n")
    out.append(("pessoal", m, ["\\Seen"]))

    m = _base("Loja Mega <ofertas@lojamega.com.br>", dono, "Só hoje: 70% de desconto em TUDO!",
              Precedence="bulk")
    m.set_content("Aproveite as ofertas imperdíveis!\nCompre agora.")
    m.add_alternative("<html><body><h1>Aproveite!</h1><p>Compre agora com <b>70%</b> de desconto.</p></body></html>",
                      subtype="html")
    out.append(("promocao", m, []))

    for i in (1, 2, 3):
        m = _base("Boletim Tech <news@boletim.com.br>", dono, f"Boletim Tech #{40 + i}: novidades da semana",
                  List_Unsubscribe="<mailto:sair@boletim.com.br?subject=sair&body=quero%20sair>, <https://boletim.com.br/sair?id=42>",
                  List_Id="<boletim.boletim.com.br>")
        m.set_content("Esta semana: notícias de tecnologia.\nPara sair da lista use o link abaixo.")
        out.append((f"news{i}", m, []))

    m = _base("Ganhe Dinheiro Fácil <ganhe@dinheiro-rapido.biz>", dono, "URGENTE!!! Você ganhou R$ 1.000.000")
    m.set_content("Clique aqui para receber seu prêmio agora mesmo.")
    out.append(("spam", m, []))

    m = _base("Financeiro Energia SA <cobranca@energiasa.com.br>", dono, "Fatura de outubro - vence em 30/10",
              mid="<fatura@falso.test>")
    m.set_content(f"Prezado cliente,\n\nSegue em anexo o boleto da fatura de outubro.\nLinha digitável: {formata(LINHA)}\n")
    m.add_attachment(pdf_com_texto(["Boleto - Energia SA", "Valor: R$ 1.234,56", "Linha digitavel:", formata(LINHA)]),
                     maintype="application", subtype="pdf", filename="boleto-outubro.pdf")
    out.append(("cobranca", m, []))

    # charset latin-1 de verdade, em 8 bits, com nome codificado
    cru = (b"From: =?ISO-8859-1?Q?Jos=E9_Concei=E7=E3o?= <jose@antigo.com.br>\r\n"
           b"To: " + dono.encode() + b"\r\n"
           b"Subject: =?ISO-8859-1?Q?Aten=E7=E3o:_reuni=E3o_=E0s_14h?=\r\n"
           b"Date: Thu, 22 Oct 2026 18:00:00 -0300\r\nMessage-ID: <latin1@falso.test>\r\n"
           b"MIME-Version: 1.0\r\nContent-Type: text/plain; charset=iso-8859-1\r\n"
           b"Content-Transfer-Encoding: 8bit\r\n\r\n" +
           "Atenção: a reunião é às 14h na sala dos coração e ação.\r\n".encode("latin-1"))
    out.append(("latin1", message_from_bytes(cru, policy=SMTP), []))

    # charset que nenhum Python conhece (comum em spam): nao pode virar corpo vazio
    cru = (b"From: Fornecedor <vendas@fornecedor.com.br>" + CRLF + b"To: " + dono.encode() + CRLF
           + b"Subject: Proposta comercial" + CRLF + b"Date: Wed, 21 Oct 2026 15:00:00 -0300" + CRLF
           + b"Message-ID: <estranho@falso.test>" + CRLF + b"MIME-Version: 1.0" + CRLF
           + b"Content-Type: text/plain; charset=x-unknown" + CRLF + b"Content-Transfer-Encoding: 8bit" + CRLF + CRLF
           + "Segue a proposta com o valor de cotação.".encode("utf-8") + CRLF)
    out.append(("estranho", message_from_bytes(cru, policy=SMTP), []))

    m = _base("Banco Digital <avisos@bancodigital.com.br>", dono, "Seu extrato chegou")
    m.set_content("<html><head><style>p{color:red}</style><script>alert('x')</script></head>"
                  "<body><p>Olá! O extrato de outubro está disponível no app.</p></body></html>", subtype="html")
    out.append(("html", m, []))

    m = _base("Carlos Lima <carlos@empresa.com.br>", dono, "Orçamento do site", mid="<orc1@falso.test>",
              data="Mon, 19 Oct 2026 10:00:00 -0300")
    m.set_content("Gui, qual o orçamento para o site novo?")
    out.append(("thread1", m, ["\\Seen"]))
    m = _base(dono, "Carlos Lima <carlos@empresa.com.br>", "Re: Orçamento do site", mid="<orc2@falso.test>",
              data="Mon, 19 Oct 2026 11:00:00 -0300", In_Reply_To="<orc1@falso.test>", References="<orc1@falso.test>")
    m.set_content("Carlos, fica em R$ 8.000.")
    out.append(("thread2", m, ["\\Seen"]))
    m = _base("Carlos Lima <carlos@empresa.com.br>", dono, "Re: Orçamento do site", mid="<orc3@falso.test>",
              data="Tue, 20 Oct 2026 09:30:00 -0300", In_Reply_To="<orc2@falso.test>",
              References="<orc1@falso.test> <orc2@falso.test>")
    m.set_content("Fechado! Pode mandar o contrato até sexta.\n\n> Carlos, fica em R$ 8.000.")
    out.append(("thread3", m, []))

    m = _base("Ana Reis <ana@parceiro.com.br>", dono, "Reunião de alinhamento")
    m.set_content("Convite para a reunião de alinhamento na terça-feira.")
    m.add_attachment("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:reuniao-1@falso.test\r\n"
                     "DTSTART:20261027T170000Z\r\nDTEND:20261027T180000Z\r\nSUMMARY:Reuniao de alinhamento\r\n"
                     "END:VEVENT\r\nEND:VCALENDAR\r\n", subtype="calendar", filename="convite.ics")
    out.append(("convite", m, []))

    m = _base("Estúdio Foto <foto@estudio.com.br>", dono, "Fotos do casamento (arquivo grande)")
    m.set_content("Segue o arquivo com todas as fotos.")
    m.add_attachment(random.Random(7).randbytes(GRANDE), maintype="application",
                     subtype="octet-stream", filename="fotos-casamento.bin")
    out.append(("grande", m, []))

    m = _base("sem.assunto@qualquer.com", dono, None)
    m.set_content("Mensagem sem assunto nenhum.")
    out.append(("sem_assunto", m, []))

    return [(k, m.as_bytes(policy=SMTP) if hasattr(m, "as_bytes") else m, f) for k, m, f in out]


def monta(dono=DONO, senha="senha-do-gui"):
    """Conta pronta para o ImapFalso/SmtpFalso: {"senha", "msgs", "uids": {chave: uid}}."""
    msgs, uids = [], {}
    for i, (chave, raw, flags) in enumerate(mensagens(dono), 101):
        msgs.append(Msg(i, raw, flags))
        uids[chave] = i
    return {"senha": senha, "msgs": msgs, "uids": uids}
