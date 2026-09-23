# Design system das prévias

A prévia é o argumento. O e-mail diz "olhei o seu site"; o link tem que provar que olhei a
empresa, não a categoria. Um dono de barbearia em Lisboa recebe, por semana, uma dezena de
propostas de agência com a mesma landing page: foto de banco escurecida, nome gigante em
caixa alta, três cartões numerados, depoimento que ninguém deu. Se a nossa prévia se parece
com isso, o e-mail vira spam com link. Se ele abre e reconhece a própria casa em cinco
segundos, a conversa começa.

Este documento diz o que a prévia é, o que ela nunca é, e como conferir antes de sair. Vale
para `backend/app/branding/templates/`, `config/site_copy.yaml`, `brand_kit.py` e
`site_renderer.py`. Mudança nesses arquivos que contrarie uma regra daqui muda a regra aqui
primeiro, com o motivo.

## 1. Princípios

1. **Fato antes de forma.** Cada bloco da página mostra algo que é verdade sobre aquela
   empresa: nome, rua, telefone, nota no Google, o texto "sobre" do próprio site, as cores
   do próprio site. Bloco sem fato não é preenchido com texto de categoria; é cortado.
   Página curta e verdadeira ganha de página longa e genérica.
2. **O ofício, não o SaaS.** Cada categoria tem um objeto físico que o cliente já conhece:
   a tabela de preços na parede da barbearia, a ardósia do restaurante, o cartão de
   marcação da clínica, o quadro de horários do ginásio, o livro de hóspedes da pousada. A
   página se organiza em torno desse objeto (seção 4), não em torno de "hero, features,
   testimonials, CTA".
3. **A casa manda na paleta.** Cores e logo vêm do site da empresa. A paleta de reserva
   só entra quando o site não deu nada, e mesmo assim sai dos materiais do ofício (couro,
   azulejo, madeira, ardósia), não de um gerador de gradiente.
4. **Rápida no telemóvel, porque foi isso que criticamos.** O e-mail aponta lentidão ou
   versão de computador no celular. A prévia que abre lenta ou quebrada no celular
   desmente o e-mail. Orçamento na seção 6.
5. **Local.** Idioma, formato de telefone e de endereço, registro formal ou informal: tudo
   do país do destinatário. Nada de inglês de enfeite ("Welcome", "Book now", "Our story").
6. **Honesta sobre o que é.** A faixa do topo diz que é uma prévia e quem fez. Foto de banco
   é rotulada. Nada de depoimento, prêmio, "desde 1987" ou número inventado.

## 2. Proibido (cara de IA e de template)

Cada item abaixo é um sinal que o dono já viu em outra proposta. Nenhum entra.

| Proibido | Por quê | No lugar |
|---|---|---|
| Hero de foto em tela cheia com gradiente escuro por cima e nome em caixa alta gigante | É a landing page padrão de todo gerador | Nome no tamanho de letreiro, sobre a cor da casa, com o objeto do ofício já visível na primeira tela |
| Rótulo em caixa alta e espaçado acima de cada título ("SOBRE", "SERVIÇOS") | Tique de template; repete o que o título já diz | Só o título. Um rótulo, se existir, é informação ("Aberto hoje até 19h") |
| Cartões numerados 01, 02, 03 | Numeração sem ordem real é decoração | Lista com preço ou duração, no formato do objeto do ofício |
| Três colunas de "features" com ícone | Ícone genérico não diz nada sobre a casa | Linhas de texto com o serviço e o dado dele |
| Bolhas, blobs, glassmorphism, sombras coloridas, gradiente de fundo | Estética de template de 2023 | Superfícies chapadas, uma cor da casa, fios finos |
| Emoji e ícone de biblioteca como ilustração | Genérico por definição | Tipografia, o logo da casa, foto real |
| Depoimentos, "clientes satisfeitos", contadores ("+500 cortes") | Inventado | A nota real do Google com o número real de avaliações, uma vez |
| Monograma com a primeira letra num círculo de gradiente quando falta foto | Placeholder com cara de placeholder | Sem foto, a página não reserva espaço para foto |
| Mapa do Google embutido | Pesa ~1 MB e trava o scroll no celular | Endereço como texto e link "abrir no mapa" |
| Frases de marketing no texto de categoria ("experiência única", "qualidade e excelência") | Ninguém fala assim de uma barbearia | O que se faz lá, em palavras de balcão: "corte, barba, navalha" |
| Tudo centralizado | Leitura cansa e parece slide | Alinhado à esquerda, grade assimétrica |
| Botão "Saiba mais" | Não diz o quê | O verbo da ação real: "Marcar", "Ligar", "Ver a carta" |

## 3. Fundamentos

### Tipografia

- Duas famílias no máximo: uma de display para o nome e os títulos, uma de texto. Ambas do
  Google Fonts, com `display=swap` e só os pesos usados (dois por família no máximo).
- O par sai do ofício e do país, não do "mood" genérico. Referências:
  - barbearia: grotesca condensada, de letreiro (Oswald, Big Shoulders Display) + grotesca
    de texto;
  - restaurante e pousada: serifada de livro (Fraunces, Libre Caslon) + humanista;
  - clínica e salão: humanista clara (Karla, Figtree) sem display pesado;
  - ginásio: grotesca larga, números tabulares.
- Proibido: Inter, Roboto, Poppins e Montserrat como display. São a assinatura de
  "gerado".
- Escala em quatro degraus, não mais: nome (clamp 2.6 a 5.5rem), título de seção (1.6 a
  2.4rem), texto (1rem, 1.6 de entrelinha), miúdo (0.85rem). Números em `tabular-nums`.
- Caixa alta só em rótulo curto de até três palavras, nunca no nome inteiro de forma
  automática: se o logo da casa é em caixa baixa, a página respeita.

### Cor

- Tokens: `--casa` (cor principal do site da empresa), `--casa-2` (segunda cor, se
  houver), `--papel` (fundo), `--tinta` (texto), `--fio` (linhas, 15% da tinta).
- Contraste AA (4.5:1 texto, 3:1 texto grande) conferido por `contrast_ratio` antes de
  renderizar; cor que não passa vira fio ou fundo de faixa, nunca texto.
- Uma cor forte por tela. `--casa` pinta uma superfície grande (faixa, bloco da tabela) ou
  detalhes, não os dois.
- Paleta de reserva por ofício, não por mood: couro e latão (barbearia), azulejo e cal
  (restaurante em PT), ardósia e giz (restaurante FR), linho e terracota (pousada), branco
  clínico com um verde ou azul discreto (clínica).

### Espaço e grade

- Base de 8px. Seções separadas por 64px no celular e 96px no desktop.
- Largura de leitura de 60 a 70 caracteres. Texto nunca atravessa a tela toda.
- Grade assimétrica no desktop (5/7 ou 4/8). No celular, uma coluna, na ordem da
  importância para quem está na rua: o que é, onde fica, como marcar.

### Forma

- Raio 0 ou 2px no ofício "de letreiro" (barbearia, ginásio); 6px no máximo nos outros.
  Nada de pílula.
- Fios de 1px no lugar de sombras e cartões. A tabela de preços com pontilhado entre nome e
  preço é o exemplo.

### Imagem

- Ordem: foto do próprio site (og:image, galeria) > nenhuma foto > foto de banco rotulada.
  Foto de banco é a última opção e nunca mostra rosto em primeiro plano: rosto de estranho
  na página da casa dele é mentira visual.
- Foto sempre com o mesmo recorte na página (4:5 ou 3:2), `loading="lazy"` fora da
  primeira tela, largura máxima servida de 1200px.
- Logo da casa no tamanho em que foi desenhado para caber; nunca esticado, nunca recolorido.

## 4. O objeto do ofício

A primeira tela mostra o nome e o objeto. O resto da página é o objeto desdobrado e o
caminho até a porta.

| Categoria | Objeto | Primeira tela | Desdobramento |
|---|---|---|---|
| barbearia | Tabela de preços na parede | Nome em letreiro + a tabela (serviço, pontilhado, "desde") | Endereço, telefone, "Marcar" |
| salão de beleza | Cartão de serviços do balcão | Nome + lista curta de serviços com duração | Sobre (texto do site), contato |
| clínica estética | Cartão de marcação | Nome + "Marcar consulta" + telefone visível | Tratamentos em lista sóbria, contato |
| restaurante | Ardósia / carta | Nome + carta curta por secção (entradas, pratos) em serifada | Morada, telefone, "Reservar" |
| ginásio | Quadro de horários | Nome + modalidades em grade de horário | Contato, inscrição |
| pousada | Livro de hóspedes | Nome + a frase "sobre" do site + foto real, se houver | Quartos (se o site listar), como chegar |

Serviço e preço só aparecem como estão no site da empresa. Sem preço coletado, a tabela
mostra os serviços sem valor, e o texto fixo não inventa "a partir de". Sem serviço
coletado, vale a lista de categoria do `site_copy.yaml`, marcada internamente como texto de
categoria e escrita em palavras de balcão.

## 5. Texto na página

- Idioma e registro do e-mail (FR "vous", NL "u", PT de Portugal). A prévia nunca muda de
  idioma no meio.
- Frases curtas, concretas, sem adjetivo de marketing. Teste: o dono diria essa frase ao
  telefone? Se não, sai.
- O texto "sobre" do próprio site, quando existe, entra como está, entre aspas, atribuído à
  casa. É a coisa mais "deles" que temos.
- Verbos de ação reais nos botões: "Marcar", "Ligar", "Reservar mesa", "Como chegar".

## 6. Orçamento técnico

- Sem JavaScript. HTML e CSS num arquivo só.
- Até 60 KB de HTML+CSS; até 2 fontes e 4 pesos no total; imagens fora da primeira tela
  com `loading="lazy"`.
- Nota Lighthouse mobile de 90 ou mais em desempenho e acessibilidade: é o número que
  justifica o e-mail.
- Funciona sem as fontes (pilha de fallback do sistema com métrica parecida) e sem as
  imagens (texto alternativo com o nome da casa).

## 7. Conferência antes de publicar

Toda mudança de template passa por esta lista, olhando as três línguas no celular:

1. **Teste do vizinho.** Alguém que conhece a casa reconhece a página em cinco segundos,
   sem ler a faixa do topo?
2. **Teste do "copiar e colar".** Trocando só o nome por outro da mesma categoria, a página
   continua fazendo sentido? Se sim, está genérica demais: falta fato da casa.
3. Nenhum item da tabela da seção 2 aparece.
4. Contraste AA em todo texto.
5. Primeira tela no celular (390px) mostra nome, o objeto do ofício e um jeito de contato.
6. Nada inventado: todo número e toda frase de fato vem do BrandKit.
7. Orçamento da seção 6 cumprido.

## 8. De onde vem cada dado

| Dado | Fonte | Se faltar |
|---|---|---|
| Nome, morada, telefone, e-mail | `Company` (Google Maps) | Bloco some; o nome nunca falta |
| Cores | `Audit.dominant_colors` (site) | Paleta de reserva do ofício |
| Logo | `Audit.logo_url` | Nome em tipografia de display, sem monograma |
| Foto principal | `Audit.og_image_url` | Sem foto; banco só se `PEXELS_API_KEY` e com rótulo |
| Texto "sobre" | `Audit.about_snippet` | Frase de categoria do `site_copy.yaml` |
| Nota e avaliações | `Company.google_rating`, `google_review_count` | Linha some |
| Serviços e preços | ainda não coletados do site | Lista de categoria, sem preço |
| Horário | ainda não coletado | Linha some; nunca "aberto agora" sem dado |

Os dois "ainda não coletados" são a próxima fronteira: cada fato novo que o auditor
extrai do site da empresa é uma linha a menos de texto de categoria na prévia.
