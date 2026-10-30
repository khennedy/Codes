# TerraPorto — MVP da plataforma de corretagem rural

Aplicação web funcional da rede privada de corretores especializados em imóveis rurais descrita em:

- **Estratégia V2** — *A Nova Infraestrutura do Mercado de Terras* (out/2026);
- **Projeto de Parceria com Corretores** — projeto estratégico, Regulamento de Proteção Comercial, Regulamento de Avaliação e Regulamento de Qualidade;
- **Anexo 01** — Checklist Documental e Diligência Rural.

Os contratos da RE/MAX serviram só como **referência de estrutura** (associação de corretor e representação exclusiva). Nenhum texto deles foi copiado, e nenhum dado pessoal que aparece neles entrou no projeto. Todos os dados de demonstração são fictícios.

> Antes do lançamento, confirme a disponibilidade da marca **TerraPorto** no INPI, do domínio e das redes sociais. O nome exibido vem da variável `PLATAFORMA_NOME` (padrão: TerraPorto).

## Como rodar

Requisito: Python 3.10 ou superior.

```bash
cd terraporto
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py popular_demo      # dados fictícios do piloto Sul de Minas / Campo das Vertentes
python manage.py runserver
```

Abra http://127.0.0.1:8000. Todos os usuários de demonstração usam a senha `demo1234`:

| Usuário | Perfil |
|---|---|
| `central` | Central de qualidade e direção (também acessa `/admin/`) |
| `ana` | Corretora Partner — captadora da fazenda de café |
| `bruno` | Corretor Master — pecuária de leite e chácaras |
| `carla` | Corretora Sênior — tem uma venda concluída |
| `diego` | Corretor Pleno — investidor com proposta e data room liberado |
| `eduardo` | Corretor inscrito, aguardando credenciamento |

Para recriar a demonstração do zero: `python manage.py popular_demo --forcar`.
Para rodar os testes: `python manage.py test`.

## O que a plataforma faz

| Módulo | Base nos documentos |
|---|---|
| **Vitrine pública**: teaser com informações mínimas, formulários "tenho interesse" e "quero vender" | Estratégia V2 §09 (materiais em camadas) e §12 (cadastro progressivo) |
| **Credenciamento de corretores**: inscrição, verificação de CRECI, prova prática, níveis Pleno/Sênior/Master/Partner e nível sugerido pelo volume dos últimos 12 meses | Estratégia V2 §05, §06 e §19 |
| **Universidade Rural**: trilhas (as de ingresso são obrigatórias), conclusão validada pela central | Estratégia V2 §06 |
| **Mensalidades** por nível, com geração mensal e baixa | Estratégia V2 §13 e §19 |
| **Cadastro técnico rural**: fundiário, solo, água, culturas, pecuária, benfeitorias e fonte de cada bloco (declarado/observado/documentado/validado). Campo vazio aparece como "não informado" | Estratégia V2 §08 e Anexo I |
| **Checklist documental** (vendedor PF ou PJ) com semáforo e matriz de decisão: *apto*, *apto com ressalvas*, *pendente* ou *bloqueado* | Anexo 01 e Estratégia V2 §10 |
| **Avaliação e precificação**: três valores distintos e faixas de compatibilidade A/B/C/D. Recusa e pendência exigem parecer, e há data de revisão do preço | Regulamento de Avaliação, arts. 10 a 16 |
| **Autorização de venda**: representação exclusiva (180 dias) ou carteira compartilhada, com alerta de vencimento | Projeto §8 e Anexo IV |
| **Publicação controlada**: só publica imóvel aprovado, com documentação apta, preço autorizado e foto autorizada. Se o corretor alterar preço, área ou matrícula, o imóvel volta para validação | Regulamentos de Avaliação e de Qualidade |
| **Catálogo fechado** para corretores: o contato do proprietário fica só com o captador | Projeto §5 e §11 |
| **Data room**: o corretor pede acesso, a central libera por prazo definido, a página tem marca d'água e cada acesso fica registrado | Estratégia V2 §09 e §16 |
| **Compradores e proteção comercial**: prioridade de 30 dias, renovada por atividade efetiva, e detecção de duplicidade por telefone, e-mail ou documento | Regulamento de Proteção §4 e §5 |
| **Motor de compatibilidade** comprador × imóvel, com a explicação de cada critério | Estratégia V2 §12 |
| **Funil de negociações** (kanban), linha do tempo, visitas com relatório e próxima ação | Anexo II |
| **Comissões**: rateio "por nível" (Estratégia V2) ou "45/45/10" (Regulamento), situações A/B/C, ajuste manual que precisa fechar 100%, suspensão do rateio em caso de disputa | Estratégia V2 §13/§19; Regulamento §7 a §9 |
| **Conflitos**: procedimento em 7 etapas. Quem é parte da disputa não pode decidir; há medidas disciplinares com fundamentação | Regulamento de Proteção §5, §6, §12 e §13 |
| **Encaminhamento à Hábil**: com consentimento, envia só os dados mínimos e registra apenas o status (nenhum dado financeiro) | Estratégia V2 §02 e §12 |
| **Simulador econômico**: rateio de uma venda, cenários anuais e "a terra se paga?" (tabela Price em 3 cenários) | Estratégia V2 §11 e §19 |
| **Minutas orientativas** imprimíveis de associação do corretor e de representação do vendedor | Anexos III e IV |
| **Painel da central** com os indicadores essenciais e filas de trabalho; **auditoria** de alterações e acessos | Estratégia V2 §07 e §18 |

Percentuais, prazos e faixas são premissas ilustrativas dos documentos e podem ser alterados em **Configurações**.

## Estrutura

```
terraporto/
├── config/        configurações do Django
├── core/          regras de negócio puras (regras.py), painel, vitrine, simulador, auditoria, minutas
├── contas/        usuários, corretores, Universidade Rural, mensalidades
├── imoveis/       proprietários, imóveis, checklist, fotos, autorizações, catálogo, dossiê
├── negocios/      compradores, perfis de busca, negociações, visitas, comissões, conflitos, crédito
├── templates/     telas (HTML renderizado no servidor, sem etapa de build)
└── static/css/    interface clean: fundo claro, uma cor de destaque (verde TerraPorto)
```

As regras de cálculo (rateio, faixas de preço, matriz documental, compatibilidade, proteção e viabilidade) ficam em `core/regras.py`. Esse módulo não depende do banco de dados e é coberto pelos testes de `core/tests.py`. O fluxo ponta a ponta (captação → validação → catálogo → data room → venda → comissão) é testado em `negocios/tests.py`.

## Segurança e LGPD já contempladas

- Arquivos enviados (documentos e fotos) não têm URL pública: passam sempre por uma view que verifica permissão.
- O contato do comprador fica só com o corretor que o registrou e com a central.
- Fotos aceitas: JPG, PNG e WebP. Uma foto só vai para a vitrine se o proprietário autorizou o uso.
- Consentimento registrado para proprietário, comprador, lead e encaminhamento de crédito.

## Próximos passos sugeridos (fora deste MVP)

- Banco PostgreSQL, deploy com HTTPS, `DJANGO_SECRET_KEY` e `DJANGO_DEBUG=0` (as variáveis já são lidas em `config/settings.py`).
- MFA, política de retenção e backup.
- Assinatura eletrônica das autorizações e contratos.
- Aplicativo offline do corretor (vistoria com geolocalização e fotos por item).
- Integrações licenciadas (SICAR, SIGEF/INCRA, Receita Federal), cada uma com base legal e autorização próprias.
- Cobrança automática das mensalidades e emissão de NFS-e.
- IA supervisionada para apontar inconsistências no cadastro.

> **Aviso:** as minutas e regras são arquitetura de negócio para discussão entre os sócios e **não substituem parecer jurídico, regulatório, fiscal ou técnico**. Pontos que exigem validação antes de uso externo: Lei 6.530/1978, Código Civil arts. 722 a 729, normas COFECI/CRECI, LGPD, PLD e regime tributário.
