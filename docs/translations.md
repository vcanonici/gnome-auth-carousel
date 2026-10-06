# Traduções

Os textos do carrossel usam o domínio gettext `gnome-auth-carousel`. Os msgids
(inglês) estão marcados com `N_()` em `state.js`; o Shell traduz cada um ao
exibir. O pacote `thinkpad-auth-policy` instala os catálogos em
`/usr/share/locale/<idioma>/LC_MESSAGES/gnome-auth-carousel.mo`.

Qual idioma aparece:

- tela de login (GDM): locale do sistema (`/etc/default/locale`);
- desbloqueio: locale da sessão do usuário;
- sem catálogo (ou msgstr vazio): o texto em inglês.

O gettext tenta `pt_BR`, depois `pt`; uma variante regional sem arquivo próprio
usa o catálogo do idioma base quando ele existe (por exemplo `es_MX` → `es`).

## Adicionar ou corrigir um idioma

Use o código de locale como nome do arquivo (`sv`, `pt_BR`, `zh_TW`, ...):

```bash
cp po/gnome-auth-carousel.pot po/sv.po
# preencha cada msgstr; ajuste "Language: sv" e "Plural-Forms" no cabeçalho
echo sv >> po/LINGUAS
msgfmt --check -o /dev/null po/sv.po
npm test                      # exige todos os msgids traduzidos
```

Abra a prévia (`prototype/`) e escolha o idioma para revisar o texto no layout.
"Trezor" é nome de produto e não é traduzido.

## Mudar textos de origem

Depois de alterar ou criar `N_('...')` em `state.js`, copie para
`scripts/state.js`, regenere o modelo e atualize os catálogos:

```bash
xgettext --language=JavaScript --keyword=N_ --from-code=UTF-8 \
  -o po/gnome-auth-carousel.pot -f po/POTFILES
for po in po/*.po; do msgmerge --update --no-fuzzy-matching "$po" po/gnome-auth-carousel.pot; done
```

`scripts/container_build.sh` falha se o `.pot` não corresponder ao código ou se
algum catálogo estiver incompleto.
