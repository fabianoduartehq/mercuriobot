# 🪐 Mercuriobot

Bot automatizado para o Bluesky (AT Protocol) que monitora os trânsitos de Mercúrio através dos dados ephemeris da NASA (JPL DE421) e posta atualizações diárias com contagens regressivas e humor astrólogico em Português (PT-BR).

Powered by **Skyfield** + **GitHub Actions** (100% gratuito e sem necessidade de servidor).

## Google Apps Script (clasp)

O projeto Apps Script fica na raiz do repositório, junto do bot em Python. O arquivo `.claspignore` garante que o `clasp push` envie ao Google apenas `appsscript.json`, `*.gs`, `*.js` e `*.html` (nada de `bot.py`, `messages.json`, `.github/` etc.).

Primeira vez (no seu computador, com Node.js instalado):

```bash
npm install -g @google/clasp
clasp login                      # abre o navegador para autorizar
clasp clone <SCRIPT_ID>          # na raiz do repositório
git add . && git commit -m "Adiciona projeto Apps Script" && git push
```

O `SCRIPT_ID` está em Apps Script → Configurações do projeto → IDs. A Apps Script API precisa estar ativada em https://script.google.com/home/usersettings.

Rotina:

- Editou no editor do Google: `clasp pull`, depois `git commit` e `git push`.
- Editou no computador ou no GitHub: `git pull`, depois `clasp push`.

Nunca commite o `~/.clasprc.json` (credenciais) nem chaves/tokens dentro dos `.gs`; use `PropertiesService` para segredos.
