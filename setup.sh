#!/bin/bash
set -euo pipefail

echo "🚀 ドアロックくん セットアップを開始します..."

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "📝 .env が見つからないため、.env.example から作成します..."
  cp .env.example .env
  echo "⚠ .env を開き、APIキーとIDを入力してください。"
else
  echo "✅ .env ファイルは既に存在します。"
fi

SERVICE_NAME="switchbot.service"
CURRENT_DIR="$(pwd)"
CURRENT_USER="$(whoami)"

echo "⚙ systemd サービス (${SERVICE_NAME}) を設定しています..."
sudo tee "/etc/systemd/system/${SERVICE_NAME}" > /dev/null << EOF
[Unit]
Description=Door Locker SwitchBot LINE Bot
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
Environment=PATH=${CURRENT_DIR}/venv/bin
ExecStart=${CURRENT_DIR}/venv/bin/python3 ${CURRENT_DIR}/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 systemd をリロードし、サービスを起動しています..."
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "✨ セットアップが完了しました。"
echo "📊 状態確認: sudo systemctl status ${SERVICE_NAME}"
echo "📝 次に .env を編集し、sudo systemctl restart ${SERVICE_NAME} を実行してください。"
