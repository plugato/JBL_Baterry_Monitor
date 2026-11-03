# JBL Quantum910 Battery Tray (Linux)

[![CI](https://github.com/plugato/JBL_Baterry_Monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/plugato/JBL_Baterry_Monitor/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/plugato/JBL_Baterry_Monitor)](https://github.com/plugato/JBL_Baterry_Monitor/releases/latest)

Monitor de bateria **real** para o JBL Quantum910: mostra a **% da bateria no tray** e pode iniciar automaticamente no login via **`systemd --user`**.

O padrão de bateria confirmado para este headset é:

```
[Report ID, Battery%]
08 1e => 30%
```

## ✅ O que este projeto faz

- **Tray/AppIndicator**: mostra “30%” no tray e atualiza automaticamente.
- **Leitura confiável**: usa o mesmo método do `jbl_battery_simple.py` (PyUSB, interface 3), com fallback para hidraw (interface 3 detectada via sysfs).
- **Serviço no login**: instala como `systemd --user` (sem precisar de root rodando o app).
- **Ferramentas e docs**: scripts de análise e documentação foram organizados em pastas.

## 📁 Estrutura do projeto

- **`jbl_quantum910_tray.py`**: app do tray (principal)
- **`install.sh` / `uninstall.sh`**: instala/remove como serviço no login
- **`systemd/`**: unit file do `systemd --user`
- **`autostart/`**: alternativa via `.desktop`
- **`tools/`**: scripts auxiliares/experimentais de captura/análise
- **`docs/`**: documentação detalhada (permissões, troubleshooting, etc.)

## ✅ Padrão de Bateria (confirmado)

- **Byte 0**: Report ID = `0x08`
- **Byte 1**: bateria em % (0–100)

Detalhes: `docs/PADRAO_BATERIA.md`.

## 🚀 Início Rápido

### 1) Verificar permissões

```bash
./check_permissions.sh
```

### 2) Configurar permissões (recomendado)

```bash
sudo ./setup_udev_rules.sh
# Depois desconecte e reconecte o fone
```

### 3) Rodar o tray

```bash
python3 ./jbl_quantum910_tray.py
```

Se você quiser testar só a leitura (CLI), use:

```bash
sudo python3 ./jbl_battery_simple.py
```

## 🔧 Requisitos

### Dependências Python (CLI/leitura)

```bash
pip3 install pyusb --user
# ou
pip3 install hidapi --user
```

### Requisitos (Tray / AppIndicator)

Para o tray, a instalação é via pacotes do sistema (não via pip):

```bash
sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 python3-usb
# (em algumas distros pode ser: gir1.2-appindicator3-0.1)
```

O serviço roda com `/usr/bin/python3`, então o `pyusb` precisa estar no Python do sistema (`python3-usb`), não num venv/pyenv.

## 🖥️ Tray (AppIndicator) - Como usar

### Executar manualmente

```bash
python3 ./jbl_quantum910_tray.py
```

Opções úteis:

```bash
python3 ./jbl_quantum910_tray.py --refresh 1.0
python3 ./jbl_quantum910_tray.py --prefer-hidraw
```

## 📦 Instalação (recomendado) — inicia com o sistema (login)

Isso instala como **serviço `systemd --user`** (inicia quando você faz login no desktop).

```bash
chmod +x ./install.sh
./install.sh
```

Para remover:

```bash
chmod +x ./uninstall.sh
./uninstall.sh
```

### Instalar a partir de um Release

```bash
VERSION=1.2.0
curl -LO https://github.com/plugato/JBL_Baterry_Monitor/releases/download/v${VERSION}/jbl-quantum910-tray-${VERSION}.tar.gz
tar xzf jbl-quantum910-tray-${VERSION}.tar.gz
cd jbl-quantum910-tray-${VERSION} && ./install.sh
```

## 🚢 CI / Deploy automático

- **CI** (`.github/workflows/ci.yml`): a cada push/PR roda `ruff`, `pytest` (Python 3.9–3.13), `shellcheck` e um smoke test.
- **Release** (`.github/workflows/release.yml`): quando o CI passa na `main` e a versão em `__version__` (`jbl_quantum910_tray.py`) ainda não tem tag, cria a tag `vX.Y.Z` e publica um GitHub Release com o `.tar.gz` + `sha256`.

Para publicar uma nova versão: aumente `__version__`, faça commit e `git push` na `main`.

Rodar os testes localmente:

```bash
pip install pytest ruff
ruff check && pytest
```

## 🧰 Ferramentas (scripts auxiliares)

Os scripts abaixo ficam em `tools/` e são úteis para análise/debug:

- `tools/jbl_battery_hidraw.py`: dump/analise completa (tem `--log`)
- `tools/jbl_battery_monitor.py`: alternativa via pyusb
- `tools/jbl_battery_hidapi.py`: alternativa via hidapi
- `tools/jbl_battery_capture.py`: captura na conexão/desconexão
- `tools/jbl_battery_force.py`: força bruta/experimental
- `tools/find_hidraw.py`: encontra o `/dev/hidrawX`

## 📝 Notas

- **IDs**: VID `0x0ecb` / PID `0x2088`
- **HID**: interface 3, endpoint IN (usado pelo método `pyusb`)
- **Atualização**: o headset pode ficar “quieto” — use o fone (volume/botões) pra gerar tráfego
- **Permissões**: ideal é usar `setup_udev_rules.sh` para evitar `sudo`

## 🐛 Troubleshooting

Veja:

- `docs/TROUBLESHOOTING.md`
- `docs/INSTRUCOES.md`

## 📄 Licença

Scripts criados para uso pessoal/educacional.

