#!/bin/bash
# Script para verificar permissões e configuração do dispositivo JBL Quantum910

echo "=== Verificação de Permissões JBL Quantum910 ==="
echo

# Verifica se o dispositivo está conectado
echo "1. Verificando se o dispositivo está conectado..."
if lsusb | grep -q "0ecb:2088"; then
    echo "   ✓ Dispositivo encontrado"
    lsusb | grep "0ecb:2088"
else
    echo "   ✗ Dispositivo não encontrado"
    echo "   Conecte o fone JBL Quantum910 via USB"
    exit 1
fi

echo

# Verifica permissões do dispositivo USB
echo "2. Verificando permissões do dispositivo USB..."
DEVICE_PATH=$(lsusb | grep "0ecb:2088" | head -1 | sed 's/.*Bus \([0-9]*\) Device \([0-9]*\).*/\/dev\/bus\/usb\/\1\/\2/')
if [ -e "$DEVICE_PATH" ]; then
    PERMS=$(stat -c "%a" "$DEVICE_PATH" 2>/dev/null)
    OWNER=$(stat -c "%U" "$DEVICE_PATH" 2>/dev/null)
    echo "   Caminho: $DEVICE_PATH"
    echo "   Permissões: $PERMS"
    echo "   Proprietário: $OWNER"
    
    # Considera ACL do uaccess e grupo plugdev, não só o modo numérico.
    if [ -r "$DEVICE_PATH" ] && [ -w "$DEVICE_PATH" ]; then
        echo "   ✓ Permissões adequadas"
    else
        echo "   ⚠ Permissões podem ser insuficientes"
        echo "   Execute: sudo ./setup_udev_rules.sh"
    fi
else
    echo "   ⚠ Caminho do dispositivo não encontrado"
fi

echo

# Verifica se o usuário está no grupo plugdev
echo "3. Verificando grupo do usuário..."
if groups | grep -q plugdev; then
    echo "   ✓ Usuário está no grupo plugdev"
else
    echo "   ⚠ Usuário não está no grupo plugdev"
    echo "   Execute: sudo usermod -a -G plugdev $USER"
    echo "   (depois faça logout e login)"
fi

echo

# Verifica regras udev
echo "4. Verificando regras udev..."
if [ -f "/etc/udev/rules.d/70-jbl-quantum910.rules" ]; then
    echo "   ✓ Regra udev encontrada"
    cat /etc/udev/rules.d/70-jbl-quantum910.rules
elif [ -f "/etc/udev/rules.d/99-jbl-quantum910.rules" ]; then
    echo "   ⚠ Regra udev antiga encontrada (MODE=0666)"
    echo "   Atualize com: sudo ./setup_udev_rules.sh"
else
    echo "   ⚠ Regra udev não encontrada"
    echo "   Execute: sudo ./setup_udev_rules.sh"
fi

echo

# Verifica bibliotecas Python
echo "5. Verificando bibliotecas Python..."
# O serviço roda com /usr/bin/python3, então as libs precisam estar no Python do sistema.
if /usr/bin/python3 -c "import usb.core" 2>/dev/null; then
    echo "   ✓ pyusb instalado"
else
    echo "   ⚠ pyusb não instalado no Python do sistema"
    echo "   Execute: sudo apt install -y python3-usb"
fi

if /usr/bin/python3 -c "import gi" 2>/dev/null; then
    echo "   ✓ PyGObject instalado"
else
    echo "   ⚠ PyGObject não instalado"
    echo "   Execute: sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1"
fi

if python3 -c "import hid" 2>/dev/null; then
    echo "   ✓ hidapi instalado"
else
    echo "   ⚠ hidapi não instalado"
    echo "   Execute: pip3 install hidapi --user"
fi

echo
echo "=== Fim da Verificação ==="

